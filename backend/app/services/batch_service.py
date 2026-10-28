"""Phase 4: batch experiments — parameter grid search with repeats, seed
strategies, bounded concurrency, cooperative cancellation, and on-demand
statistics (per-combo summarize + Pearson sensitivity).

Design notes (docs/DECISIONS.md D20):
- Items run on a dedicated bounded ThreadPoolExecutor (max_workers =
  settings.max_workers); the orchestrator keeps at most
  min(concurrency, max_workers) items outstanding per batch, submitting the
  next item only when one finishes.
- The grid combo count is checked against MAX_BATCH_ITEMS before any combo
  is materialized.
- Each item re-validates its spec and runs an unbounded engine.run() under
  per-item Limits (D19 semantics: the absolute step cap applies to unbounded
  runs, while wall-clock bounds every run).
- Only exceptions are retried; terminal statuses (completed / step_limit /
  wall_timeout) are valid results, not failures.
"""
from __future__ import annotations

import itertools
import json
import secrets
import threading
import time
from concurrent.futures import (
    FIRST_COMPLETED,
    CancelledError,
    Future,
    ThreadPoolExecutor,
    wait,
)
from typing import Any

from pydantic import ValidationError

from ..config import Settings
from ..core.engine.engines import Limits, SimulationEngine
from ..core.registry import ModelRegistry
from ..core.schema.errors import SpecValidationError
from ..core.schema.spec import validate_spec
from ..core.stats import pearson, summarize
from ..db.connection import connect
from ..db.migrations import apply_migrations
from .experiment_service import ConflictError, NotFoundError, canonical_metrics_json, metrics_sha256

MAX_BATCH_ITEMS = 2000
SEED_STRATEGIES = ("fixed", "per_repeat_increment", "unique")
_ITEM_TERMINAL = {"completed", "failed", "cancelled", "step_limit", "wall_timeout"}


class BatchService:
    def __init__(self, settings: Settings, registry: ModelRegistry):
        self.settings = settings
        self.registry = registry
        self._executor = ThreadPoolExecutor(
            max_workers=settings.max_workers, thread_name_prefix="batchrun"
        )
        self._cancel_flags: dict[int, threading.Event] = {}
        self._lock = threading.Lock()
        apply_migrations(settings.db_path)
        self._recover_interrupted()

    def _recover_interrupted(self) -> None:
        # Orchestrator threads live in the process that created the batch, so
        # 'queued'/'running' rows from a previous process can never advance.
        msg = "interrupted: service restarted while batch was in progress"
        conn = self._conn()
        try:
            with conn:
                conn.execute(
                    "UPDATE batch_items SET status='cancelled', error=?, finished_at=datetime('now')"
                    " WHERE status IN ('pending','running')",
                    (msg,),
                )
                conn.execute(
                    "UPDATE batch_runs SET status='cancelled', error=?, finished_at=datetime('now')"
                    " WHERE status IN ('queued','running')",
                    (msg,),
                )
        finally:
            conn.close()

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _conn(self):
        return connect(self.settings.db_path)

    @staticmethod
    def _get_batch_row(conn, batch_id: int):
        row = conn.execute("SELECT * FROM batch_runs WHERE id=?", (batch_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"batch {batch_id} not found")
        return row

    # ------------------------------------------------------------------ create
    def create(
        self,
        name: str,
        spec_raw: dict[str, Any],
        grid: dict[str, list[Any]],
        repeats: int = 1,
        seed_strategy: str = "fixed",
        max_retries: int = 0,
        concurrency: int = 2,
        per_run_wall_seconds: float = 60.0,
    ) -> dict[str, Any]:
        if not name or not name.strip():
            raise SpecValidationError.single("name", "batch name must not be empty")
        if not isinstance(grid, dict):
            raise SpecValidationError.single("grid", "grid must be an object of parameter -> value lists")
        for key, values in grid.items():
            if not isinstance(values, list) or not values:
                raise SpecValidationError.single(f"grid.{key}", "each grid entry must be a non-empty list")
        if seed_strategy not in SEED_STRATEGIES:
            raise SpecValidationError.single("seed_strategy", f"must be one of {list(SEED_STRATEGIES)}")
        spec, model_cls = validate_spec(spec_raw, self.registry)
        unknown = [k for k in grid if k not in model_cls.param_model.model_fields]
        if unknown:
            raise SpecValidationError.single(
                "grid", f"unknown parameters for model {spec.model_id}: {unknown}"
            )
        # Count the cartesian product before materializing anything: a huge
        # grid must be rejected, not expanded (D25).
        combo_count = 1
        for values in grid.values():
            combo_count *= len(values)
        total = combo_count * repeats
        if total > MAX_BATCH_ITEMS:
            raise SpecValidationError.single(
                "grid",
                f"total items {total} exceeds cap {MAX_BATCH_ITEMS} (combos {combo_count} x repeats {repeats})",
            )
        combos = [dict(zip(grid, values)) for values in itertools.product(*grid.values())]
        for combo in combos:
            try:
                model_cls.param_model(**{**spec.params, **combo})
            except ValidationError as exc:
                raise SpecValidationError.single(
                    "grid", f"invalid parameter combination {combo}: {exc.errors()[0]['msg']}"
                ) from None
        seed_base = spec.seed if spec.seed is not None else secrets.randbelow(2**31)
        effective_concurrency = max(1, min(concurrency, self.settings.max_workers))
        per_wall = min(float(per_run_wall_seconds), self.settings.max_wall_seconds)

        conn = self._conn()
        try:
            with conn:
                cur = conn.execute(
                    """INSERT INTO batch_runs(name, model_id, model_version, spec_json, grid_json,
                       repeats, seed_strategy, seed_base, max_retries, concurrency,
                       per_run_wall_seconds, status, total_items)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        name.strip(),
                        spec.model_id,
                        model_cls.version,
                        json.dumps(spec.model_dump(), ensure_ascii=False),
                        json.dumps(grid, sort_keys=True, ensure_ascii=False),
                        repeats,
                        seed_strategy,
                        seed_base,
                        max_retries,
                        effective_concurrency,
                        per_wall,
                        "queued",
                        total,
                    ),
                )
                batch_id = int(cur.lastrowid)
                rows = []
                for i, combo in enumerate(combos):
                    for j in range(repeats):
                        item_index = i * repeats + j
                        if seed_strategy == "fixed":
                            seed = seed_base
                        elif seed_strategy == "per_repeat_increment":
                            seed = seed_base + j
                        else:  # unique
                            seed = seed_base + item_index
                        rows.append(
                            (
                                batch_id,
                                item_index,
                                json.dumps(combo, sort_keys=True, ensure_ascii=False),
                                j,
                                seed,
                            )
                        )
                conn.executemany(
                    "INSERT INTO batch_items(batch_id, item_index, combo_json, repeat_index, seed)"
                    " VALUES (?,?,?,?,?)",
                    rows,
                )
        finally:
            conn.close()
        flag = threading.Event()
        with self._lock:
            self._cancel_flags[batch_id] = flag
        threading.Thread(
            target=self._orchestrate, args=(batch_id, flag), daemon=True, name=f"batch-{batch_id}"
        ).start()
        return self.get_batch(batch_id, include_summary=False)

    # ------------------------------------------------------------- orchestration
    def _orchestrate(self, batch_id: int, flag: threading.Event) -> None:
        t0 = time.monotonic()
        conn = self._conn()
        try:
            row = self._get_batch_row(conn, batch_id)
            spec_raw = json.loads(row["spec_json"])
            conn.execute(
                "UPDATE batch_runs SET status='running', started_at=COALESCE(started_at, datetime('now')) WHERE id=?",
                (batch_id,),
            )
            conn.commit()
            items = conn.execute(
                "SELECT id, combo_json, seed FROM batch_items WHERE batch_id=? ORDER BY item_index",
                (batch_id,),
            ).fetchall()
            max_inflight = max(1, int(row["concurrency"]))
            item_iter = iter(items)
            outstanding: set[Future] = set()

            def submit_next() -> bool:
                item = next(item_iter, None)
                if item is None or flag.is_set():
                    return False
                combo = json.loads(item["combo_json"])
                item_spec = {
                    **spec_raw,
                    "params": {**spec_raw.get("params", {}), **combo},
                    "seed": item["seed"],
                }
                limits = Limits(
                    max_steps=self.settings.default_max_steps,
                    max_wall_seconds=float(row["per_run_wall_seconds"]),
                    zero_delay_chain_limit=self.settings.zero_delay_chain_limit,
                    cancel_poll_interval=self.settings.cancel_poll_interval,
                )
                outstanding.add(
                    self._executor.submit(
                        self._execute_item, item["id"], item_spec, limits, flag, int(row["max_retries"])
                    )
                )
                return True

            while len(outstanding) < max_inflight and submit_next():
                pass
            while outstanding:
                done, _ = wait(outstanding, return_when=FIRST_COMPLETED)
                for f in done:
                    outstanding.discard(f)
                    try:
                        f.result()
                    except CancelledError:
                        pass
                while len(outstanding) < max_inflight and submit_next():
                    pass
            self._finalize(batch_id, flag, t0)
        except Exception as exc:  # noqa: BLE001 - orchestrator boundary
            try:
                with conn:
                    conn.execute(
                        "UPDATE batch_runs SET status='failed', error=?, finished_at=datetime('now'),"
                        " duration_ms=? WHERE id=?",
                        (f"{type(exc).__name__}: {exc}"[:2000], int((time.monotonic() - t0) * 1000), batch_id),
                    )
            except Exception:
                pass
        finally:
            conn.close()
            with self._lock:
                self._cancel_flags.pop(batch_id, None)

    def _execute_item(
        self,
        item_id: int,
        spec_raw: dict[str, Any],
        limits: Limits,
        flag: threading.Event,
        max_retries: int,
    ) -> None:
        conn = self._conn()
        t0 = time.monotonic()
        last_err: str | None = None
        try:
            for attempt in range(max_retries + 1):
                if flag.is_set():
                    break
                try:
                    conn.execute(
                        "UPDATE batch_items SET status='running', attempts=attempts+1,"
                        " started_at=COALESCE(started_at, datetime('now')) WHERE id=?",
                        (item_id,),
                    )
                    conn.commit()
                    spec, model_cls = validate_spec(spec_raw, self.registry)
                    model = model_cls(spec.params, spec.seed)
                    engine = SimulationEngine(
                        model, spec.stop_condition.model_dump(), limits=limits, cancel_check=flag.is_set
                    )
                    result = engine.run()
                    metrics = result.metrics
                    conn.execute(
                        """UPDATE batch_items SET status=?, steps=?, sim_time=?, metrics_json=?,
                           result_sha256=?, duration_ms=?, finished_at=datetime('now') WHERE id=?""",
                        (
                            result.status,
                            result.steps,
                            result.sim_time,
                            canonical_metrics_json(metrics),
                            metrics_sha256(metrics),
                            int((time.monotonic() - t0) * 1000),
                            item_id,
                        ),
                    )
                    conn.commit()
                    return
                except Exception as exc:  # noqa: BLE001 - worker boundary
                    conn.rollback()
                    last_err = f"{type(exc).__name__}: {exc}"
                    if flag.is_set() or attempt == max_retries:
                        break
            status = "cancelled" if flag.is_set() else "failed"
            with conn:
                conn.execute(
                    "UPDATE batch_items SET status=?, error=?, duration_ms=?, finished_at=datetime('now')"
                    " WHERE id=?",
                    (status, (last_err or "cancelled before start")[:2000], int((time.monotonic() - t0) * 1000), item_id),
                )
        finally:
            conn.close()

    def _finalize(self, batch_id: int, flag: threading.Event, t0: float) -> None:
        conn = self._conn()
        try:
            with conn:
                conn.execute(
                    "UPDATE batch_items SET status='cancelled',"
                    " finished_at=COALESCE(finished_at, datetime('now'))"
                    " WHERE batch_id=? AND status='pending'",
                    (batch_id,),
                )
                counts = dict(
                    conn.execute(
                        "SELECT status, COUNT(*) FROM batch_items WHERE batch_id=? GROUP BY status",
                        (batch_id,),
                    ).fetchall()
                )
                cancelled = counts.get("cancelled", 0)
                failed = counts.get("failed", 0)
                if flag.is_set() and (cancelled or counts.get("pending", 0) or counts.get("running", 0)):
                    status = "cancelled"
                elif failed and failed == sum(v for k, v in counts.items() if k in _ITEM_TERMINAL) - cancelled:
                    status = "failed"
                else:
                    status = "completed"
                conn.execute(
                    "UPDATE batch_runs SET status=?, finished_at=datetime('now'), duration_ms=? WHERE id=?",
                    (status, int((time.monotonic() - t0) * 1000), batch_id),
                )
        finally:
            conn.close()

    # ------------------------------------------------------------------ cancel
    def cancel(self, batch_id: int) -> dict[str, Any]:
        conn = self._conn()
        try:
            row = self._get_batch_row(conn, batch_id)
            if row["status"] in ("completed", "failed", "cancelled"):
                raise ConflictError(f"batch {batch_id} already finished")
        finally:
            conn.close()
        with self._lock:
            flag = self._cancel_flags.get(batch_id)
        if flag is not None:
            flag.set()
        return self.get_batch(batch_id, include_summary=False)

    # ------------------------------------------------------------------ queries
    def list_batches(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        conn = self._conn()
        try:
            total = conn.execute("SELECT COUNT(*) FROM batch_runs").fetchone()[0]
            rows = conn.execute(
                """SELECT b.id, b.name, b.model_id, b.model_version, b.status, b.total_items,
                   b.repeats, b.seed_strategy, b.seed_base, b.created_at, b.duration_ms,
                   COALESCE(SUM(CASE WHEN i.status IN ('completed','failed','cancelled','step_limit','wall_timeout')
                   THEN 1 ELSE 0 END), 0) AS done_items
                   FROM batch_runs b LEFT JOIN batch_items i ON i.batch_id = b.id
                   GROUP BY b.id ORDER BY b.id DESC LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
            return {"total": int(total), "batches": [dict(r) for r in rows]}
        finally:
            conn.close()

    def get_batch(self, batch_id: int, include_summary: bool = True) -> dict[str, Any]:
        conn = self._conn()
        try:
            row = self._get_batch_row(conn, batch_id)
            batch = dict(row)
            grid = json.loads(batch.pop("grid_json"))
            batch["spec"] = json.loads(batch.pop("spec_json"))
            batch["grid"] = grid
            batch["counts"] = dict(
                conn.execute(
                    "SELECT status, COUNT(*) FROM batch_items WHERE batch_id=? GROUP BY status",
                    (batch_id,),
                ).fetchall()
            )
            if include_summary:
                batch["summary"] = self._summary(conn, batch_id, grid)
            return batch
        finally:
            conn.close()

    def list_items(self, batch_id: int, limit: int = 200, offset: int = 0) -> dict[str, Any]:
        conn = self._conn()
        try:
            self._get_batch_row(conn, batch_id)
            total = conn.execute(
                "SELECT COUNT(*) FROM batch_items WHERE batch_id=?", (batch_id,)
            ).fetchone()[0]
            rows = conn.execute(
                """SELECT id, item_index, combo_json, repeat_index, seed, status, attempts, steps,
                   sim_time, metrics_json, result_sha256, error, duration_ms
                   FROM batch_items WHERE batch_id=? ORDER BY item_index LIMIT ? OFFSET ?""",
                (batch_id, limit, offset),
            ).fetchall()
            items = []
            for r in rows:
                d = dict(r)
                d["params"] = json.loads(d.pop("combo_json"))
                d["metrics"] = json.loads(d.pop("metrics_json")) if d["metrics_json"] else None
                items.append(d)
            return {"total": int(total), "items": items}
        finally:
            conn.close()

    # ----------------------------------------------------------------- summary
    def _summary(self, conn, batch_id: int, grid: dict[str, list[Any]]) -> dict[str, Any]:
        notes = {
            "sensitivity_note": (
                "皮尔逊相关系数只刻画观察到的线性关联，不构成因果结论；"
                "单次批量实验不足以断言某种参数取值普遍最优。"
            ),
            "ci_note": "ci95 为正态近似 95% 置信区间，样本量小或方差大时仅供参考。",
        }
        rows = conn.execute(
            "SELECT combo_json, metrics_json FROM batch_items"
            " WHERE batch_id=? AND status='completed' AND metrics_json IS NOT NULL",
            (batch_id,),
        ).fetchall()
        if not rows:
            return {"combos": [], "sensitivity": [], **notes}
        groups: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            groups.setdefault(r["combo_json"], []).append(json.loads(r["metrics_json"]))
        metric_names = sorted(
            {
                k
                for metric_list in groups.values()
                for m in metric_list
                for k, v in m.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)
            }
        )
        combos = []
        for combo_json in sorted(groups):
            metric_list = groups[combo_json]
            metrics = {}
            for m in metric_names:
                values = [
                    ms[m]
                    for ms in metric_list
                    if isinstance(ms.get(m), (int, float)) and not isinstance(ms.get(m), bool)
                ]
                metrics[m] = summarize(values)
            combos.append({"params": json.loads(combo_json), "n": len(metric_list), "metrics": metrics})
        sensitivity = []
        numeric_params = [
            k
            for k, vals in grid.items()
            if vals and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals)
        ]
        for param in numeric_params:
            for m in metric_names:
                pairs = [
                    (c["params"].get(param), c["metrics"][m]["mean"])
                    for c in combos
                    if isinstance(c["params"].get(param), (int, float))
                ]
                r = pearson([p[0] for p in pairs], [p[1] for p in pairs])
                if r is not None:
                    sensitivity.append(
                        {"param": param, "metric": m, "pearson_r": round(r, 6), "n_combos": len(pairs)}
                    )
        return {"combos": combos, "sensitivity": sensitivity, **notes}
