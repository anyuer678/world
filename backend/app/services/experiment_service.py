"""Experiment management + background run worker.

A Run executes in a bounded ThreadPoolExecutor; the simulation loop
cooperatively checks a cancel flag every N events so the API event loop is
never blocked and runs can be cancelled. Results carry a SHA-256 of the
canonical metrics JSON as integrity checksum.
"""
from __future__ import annotations

import hashlib
import json
import platform
import secrets
import threading
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

# 实验名称长度上限：创建与克隆都必须遵守（R60 前只有路由的 pydantic 拦，
# clone 走服务层时能存进 10000 字符的名称）。
EXPERIMENT_NAME_MAX = 200

from .. import APP_VERSION
from ..config import Settings
from ..core.engine.engines import Limits, SimulationEngine
from ..core.engine.base import ENGINE_VERSION, SimulationError
from ..core.registry import ModelRegistry, RegistryError
from ..core.schema.spec import SpecValidationError, validate_spec
from ..db.connection import connect
from ..db.migrations import apply_migrations

_TERMINAL = {"completed", "failed", "cancelled", "step_limit", "wall_timeout"}

# 预期内的失败族：spec 校验、注册表（模型/版本查无）、引擎主动抛出的模拟错误。
_EXPECTED_RUN_FAILURES = (SpecValidationError, RegistryError, SimulationError)


def describe_run_failure(exc: BaseException) -> str:
    """写进 run.error 的一句话诊断。

    预期内的失败只保留 `类型: 原因`——栈里全是本机绝对路径，会跟着报告/CSV 外流，
    对读者也只是噪声（批量单项与交互会话本来就走同样的紧凑口径）。
    真正的意外才保留 3 层栈用于定位。"""
    err = f"{type(exc).__name__}: {exc}"
    if isinstance(exc, _EXPECTED_RUN_FAILURES):
        return err[:2000]
    tail = traceback.format_exc(limit=3)[-800:]
    return (err[:2000] + "\n..." + tail) if len(err) > 2000 else (err + "\n" + tail)


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


def canonical_metrics_json(metrics: dict[str, float]) -> str:
    return json.dumps(metrics, sort_keys=True, ensure_ascii=False)


def metrics_sha256(metrics: dict[str, float]) -> str:
    return hashlib.sha256(canonical_metrics_json(metrics).encode("utf-8")).hexdigest()


class ExperimentService:
    def __init__(self, settings: Settings, registry: ModelRegistry):
        self.settings = settings
        self.registry = registry
        self._executor = ThreadPoolExecutor(
            max_workers=settings.max_workers, thread_name_prefix="simrun"
        )
        self._futures: dict[int, Future] = {}
        self._cancel_flags: dict[int, threading.Event] = {}
        self._lock = threading.Lock()
        apply_migrations(settings.db_path)
        self._recover_interrupted()

    def _recover_interrupted(self) -> None:
        # Run rows are only inserted when a run starts, so any 'pending'/
        # 'running' row left in the DB belongs to a run whose worker thread
        # died with a previous process. Mark it failed instead of leaving a
        # phantom 'running' forever.
        msg = "interrupted: service restarted while run was in progress"
        conn = self._conn()
        try:
            with conn:
                conn.execute(
                    "UPDATE experiment_runs SET status='failed', error=?, finished_at=datetime('now')"
                    " WHERE status IN ('pending','running')",
                    (msg,),
                )
                conn.execute(
                    "UPDATE experiments SET status='failed', error=?, finished_at=datetime('now')"
                    " WHERE status='running'",
                    (msg,),
                )
        finally:
            conn.close()

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------ util
    def _conn(self):
        return connect(self.settings.db_path)

    @staticmethod
    def _row_to_dict(row) -> dict[str, Any]:
        return dict(row)

    def _get_experiment_row(self, conn, exp_id: int):
        row = conn.execute("SELECT * FROM experiments WHERE id=?", (exp_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"experiment {exp_id} not found")
        return row

    def _experiment_status(self, conn, exp_id: int) -> str:
        rows = conn.execute(
            "SELECT status FROM experiment_runs WHERE experiment_id=?", (exp_id,)
        ).fetchall()
        statuses = [r[0] for r in rows]
        if not statuses:
            return "created"
        if any(s == "failed" for s in statuses):
            return "failed"
        if all(s in _TERMINAL for s in statuses):
            if all(s == "completed" for s in statuses):
                return "completed"
            if any(s == "cancelled" for s in statuses):
                return "cancelled"
            return statuses[0]
        return "running"

    def _sync_experiment_status(self, conn, exp_id: int) -> str:
        status = self._experiment_status(conn, exp_id)
        finished = status in _TERMINAL
        conn.execute(
            """UPDATE experiments SET status=?, finished_at=CASE WHEN ? THEN datetime('now') ELSE finished_at END,
               duration_ms=CASE WHEN ? THEN CAST((julianday('now') - julianday(started_at)) * 86400000 AS INTEGER) ELSE duration_ms END
               WHERE id=?""",
            (status, finished, finished, exp_id),
        )
        return status

    def _register_model(self, conn, model_cls) -> None:
        meta = {
            "model_id": model_cls.model_id,
            "display_name": model_cls.display_name,
            "description": model_cls.description,
            "model_type": model_cls.model_type,
            "params_schema": model_cls.param_model.model_json_schema(),
            "visualizer": model_cls.visualizer,
        }
        conn.execute(
            """INSERT OR IGNORE INTO model_registrations(model_id, version, display_name, model_type, spec_json)
               VALUES (?,?,?,?,?)""",
            (
                model_cls.model_id,
                model_cls.version,
                model_cls.display_name,
                model_cls.model_type,
                json.dumps(meta, ensure_ascii=False),
            ),
        )

    # ------------------------------------------------------------ experiments
    def create_experiment(
        self,
        name: str,
        spec_raw: dict[str, Any],
        parent_experiment_id: int | None = None,
    ) -> dict[str, Any]:
        if not name or not name.strip():
            raise SpecValidationError.single("name", "experiment name must not be empty")
        if len(name) > EXPERIMENT_NAME_MAX:
            raise SpecValidationError.single(
                "name", f"experiment name must be at most {EXPERIMENT_NAME_MAX} characters"
            )
        spec, model_cls = validate_spec(spec_raw, self.registry)
        software = (
            f"worldlab-{APP_VERSION}; engine-{ENGINE_VERSION}; "
            f"python-{platform.python_version()}"
        )
        conn = self._conn()
        try:
            with conn:
                self._register_model(conn, model_cls)
                cur = conn.execute(
                    """INSERT INTO experiments(name, model_id, model_version, spec_json, seed,
                       engine_version, software_version, tags, parent_experiment_id)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        name.strip(),
                        spec.model_id,
                        model_cls.version,
                        json.dumps(spec.model_dump(), ensure_ascii=False),
                        spec.seed,
                        ENGINE_VERSION,
                        software,
                        "[]",
                        parent_experiment_id,
                    ),
                )
                exp_id = int(cur.lastrowid)
            return self.get_experiment(exp_id)
        finally:
            conn.close()

    def get_experiment(self, exp_id: int) -> dict[str, Any]:
        conn = self._conn()
        try:
            row = self._get_experiment_row(conn, exp_id)
            exp = self._row_to_dict(row)
            exp["spec"] = json.loads(exp.pop("spec_json"))
            exp["tags"] = json.loads(exp.get("tags") or "[]")
            runs = conn.execute(
                "SELECT id, repeat_index, seed, status, steps, sim_time, duration_ms, result_sha256, error"
                " FROM experiment_runs WHERE experiment_id=? ORDER BY repeat_index, id",
                (exp_id,),
            ).fetchall()
            exp["runs"] = [self._row_to_dict(r) for r in runs]
            return exp
        finally:
            conn.close()

    def list_experiments(
        self, limit: int = 50, offset: int = 0, model_id: str | None = None, tag: str | None = None
    ) -> dict[str, Any]:
        conn = self._conn()
        try:
            where, args = [], []
            if model_id:
                where.append("model_id=?")
                args.append(model_id)
            if tag:
                where.append("tags LIKE ?")
                args.append(f'%"{tag}"%')
            clause = f"WHERE {' AND '.join(where)}" if where else ""
            total = conn.execute(f"SELECT COUNT(*) FROM experiments {clause}", args).fetchone()[0]
            rows = conn.execute(
                f"SELECT id, name, model_id, model_version, status, seed, tags, created_at, duration_ms, error"
                f" FROM experiments {clause} ORDER BY id DESC LIMIT ? OFFSET ?",
                [*args, limit, offset],
            ).fetchall()
            items = []
            for r in rows:
                d = self._row_to_dict(r)
                d["tags"] = json.loads(d.get("tags") or "[]")
                items.append(d)
            return {"total": int(total), "experiments": items}
        finally:
            conn.close()

    def delete_experiment(self, exp_id: int) -> None:
        self._assert_not_running(exp_id)
        conn = self._conn()
        try:
            with conn:
                # R63：检查与删除必须原子。此前 `_assert_not_running` 读完后无条件 DELETE，
                # 若这期间有并发 run 抢到占位，级联会删掉 run 行而 worker 仍在执行。
                cur = conn.execute(
                    "DELETE FROM experiments WHERE id=? AND status!='running'", (exp_id,)
                )
                if cur.rowcount == 0:
                    row = conn.execute("SELECT status FROM experiments WHERE id=?", (exp_id,)).fetchone()
                    if row is None:
                        raise NotFoundError(f"experiment {exp_id} not found")
                    raise ConflictError(f"experiment {exp_id} is running; cancel it first")
        finally:
            conn.close()

    def clone_experiment(
        self, exp_id: int, name: str | None = None, spec_overrides: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        src = self.get_experiment(exp_id)
        spec = dict(src["spec"])
        if spec_overrides:
            for key, value in spec_overrides.items():
                if key == "params" and isinstance(value, dict):
                    spec["params"] = {**spec.get("params", {}), **value}
                else:
                    spec[key] = value
        new_name = name or f"{src['name']} (clone)"
        return self.create_experiment(new_name, spec, parent_experiment_id=exp_id)

    def set_tags(self, exp_id: int, tags: list[str]) -> dict[str, Any]:
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise SpecValidationError.single("tags", "tags must be a list of strings")
        conn = self._conn()
        try:
            with conn:
                self._get_experiment_row(conn, exp_id)
                conn.execute(
                    "UPDATE experiments SET tags=? WHERE id=?",
                    (json.dumps(sorted(set(tags)), ensure_ascii=False), exp_id),
                )
            return self.get_experiment(exp_id)
        finally:
            conn.close()

    # ------------------------------------------------------------------- runs
    def run_experiment(self, exp_id: int, wait: bool = False) -> dict[str, Any]:
        conn = self._conn()
        try:
            row = self._get_experiment_row(conn, exp_id)
            exp = self._row_to_dict(row)
            if exp["status"] == "running":
                raise ConflictError(f"experiment {exp_id} is already running")
            spec = json.loads(exp["spec_json"])
            # 提交时就校验，与 create/clone/建批同口径：模型被卸载（插件模块没配好）或
            # 版本撤下时立刻 422 unknown_model，而不是先答 202 queued 再在工作线程里
            # 把 run 静默标成 failed（R35 实测的不对称）。
            validate_spec(spec, self.registry)
            with conn:
                # R62：检查与占位必须是一条语句。此前「先读 status、再无条件 UPDATE」是
                # TOCTOU——实测 8 个并发 POST /run 有 2 个成功、插入了 2 条 run，
                # 同一实验被并发执行两次。条件 UPDATE 让 SQLite 的单写者串行化成为判据。
                claimed = conn.execute(
                    "UPDATE experiments SET status='running', started_at=datetime('now'),"
                    " finished_at=NULL, error=NULL WHERE id=? AND status!='running'",
                    (exp_id,),
                )
                if claimed.rowcount != 1:
                    raise ConflictError(f"experiment {exp_id} is already running")
                cur = conn.execute(
                    "INSERT INTO experiment_runs(experiment_id, repeat_index, seed, status) VALUES (?,?,?,'pending')",
                    (exp_id, 0, spec.get("seed") if spec.get("seed") is not None else secrets.randbelow(2**31)),
                )
                run_id = int(cur.lastrowid)
        finally:
            conn.close()
        future = self._executor.submit(self._execute_run, run_id, exp_id)
        with self._lock:
            self._futures[run_id] = future
        if wait:
            future.result(timeout=self.settings.max_wall_seconds + 30)
        return {"experiment_id": exp_id, "run_id": run_id, "status": "queued"}

    def rerun_experiment(self, exp_id: int) -> dict[str, Any]:
        return self.run_experiment(exp_id, wait=False)

    def cancel_experiment(self, exp_id: int) -> dict[str, Any]:
        conn = self._conn()
        try:
            self._get_experiment_row(conn, exp_id)
            rows = conn.execute(
                "SELECT id, status FROM experiment_runs WHERE experiment_id=?", (exp_id,)
            ).fetchall()
            with conn:
                for r in rows:
                    if r["status"] in ("pending", "running"):
                        conn.execute(
                            "UPDATE experiment_runs SET status='cancelled', finished_at=datetime('now') WHERE id=?",
                            (r["id"],),
                        )
                        flag = self._cancel_flags.get(r["id"])
                        if flag is not None:
                            flag.set()
                conn.execute(
                    "UPDATE experiments SET status='cancelled', finished_at=datetime('now') WHERE id=?",
                    (exp_id,),
                )
        finally:
            conn.close()
        return self.get_experiment(exp_id)

    def _assert_not_running(self, exp_id: int) -> None:
        exp = self.get_experiment(exp_id)
        if exp["status"] == "running":
            raise ConflictError(f"experiment {exp_id} is running; cancel it first")

    def _execute_run(self, run_id: int, exp_id: int) -> None:
        flag = threading.Event()
        with self._lock:
            self._cancel_flags[run_id] = flag
        conn = self._conn()
        t0 = time.monotonic()
        try:
            try:
                exp_row = self._get_experiment_row(conn, exp_id)
            except NotFoundError:
                # R63：实验在 claim 之后被删除（级联也删掉了 run 行）——没有可写回的目标，
                # 安静退出，而不是在 Future 里留下一个没人观察的异常。
                return
            spec_raw = json.loads(exp_row["spec_json"])
            # Execute with the seed recorded on the run row (not spec.seed),
            # so a run with seed=None is reproducible from the stored seed.
            run_row = conn.execute("SELECT seed FROM experiment_runs WHERE id=?", (run_id,)).fetchone()
            if run_row is None:
                return
            run_seed = run_row["seed"]
            try:
                conn.execute(
                    "UPDATE experiment_runs SET status='running', started_at=datetime('now') WHERE id=?",
                    (run_id,),
                )
                conn.commit()
                spec, model_cls = validate_spec(spec_raw, self.registry)
                model = model_cls(spec.params, run_seed)
                limits = Limits(
                    max_steps=self.settings.default_max_steps,
                    max_wall_seconds=self.settings.max_wall_seconds,
                    zero_delay_chain_limit=self.settings.zero_delay_chain_limit,
                    cancel_poll_interval=self.settings.cancel_poll_interval,
                )
                engine = SimulationEngine(
                    model,
                    spec.stop_condition.model_dump(),
                    limits=limits,
                    cancel_check=flag.is_set,
                )
                result = engine.run()
                metrics = result.metrics
                events = [e.to_json() for e in engine.event_log[-100:]]
                conn.execute(
                    """UPDATE experiment_runs SET status=?, steps=?, sim_time=?, metrics_json=?,
                       summary_json=?, events_json=?, result_sha256=?, finished_at=datetime('now'),
                       duration_ms=?
                       WHERE id=?""",
                    (
                        result.status,
                        result.steps,
                        result.sim_time,
                        canonical_metrics_json(metrics),
                        json.dumps(result.snapshot.get("state", {}), ensure_ascii=False),
                        json.dumps(events, ensure_ascii=False),
                        metrics_sha256(metrics),
                        int((time.monotonic() - t0) * 1000),
                        run_id,
                    ),
                )
                conn.commit()
            except Exception as exc:  # noqa: BLE001 - worker boundary
                conn.rollback()
                detail = describe_run_failure(exc)
                conn.execute(
                    """UPDATE experiment_runs SET status='failed', error=?, finished_at=datetime('now'), duration_ms=? WHERE id=?""",
                    (detail, int((time.monotonic() - t0) * 1000), run_id),
                )
                conn.commit()
            with conn:
                self._sync_experiment_status(conn, exp_id)
        finally:
            conn.close()
            with self._lock:
                self._cancel_flags.pop(run_id, None)
                self._futures.pop(run_id, None)

    # --------------------------------------------------------------- results
    def get_result(self, exp_id: int) -> dict[str, Any]:
        exp = self.get_experiment(exp_id)
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM experiment_runs WHERE experiment_id=? ORDER BY repeat_index, id",
                (exp_id,),
            ).fetchall()
            runs = []
            for r in rows:
                d = self._row_to_dict(r)
                d["metrics"] = json.loads(d.pop("metrics_json")) if d.get("metrics_json") else None
                d["summary"] = json.loads(d.pop("summary_json")) if d.get("summary_json") else None
                d.pop("events_json", None)
                runs.append(d)
            # Truncated/failed/cancelled runs may still carry metrics; only
            # completed runs are comparable, so the aggregate excludes the rest.
            completed = [r for r in runs if r["status"] == "completed" and r["metrics"]]
            aggregate = None
            if completed:
                keys = completed[0]["metrics"].keys()
                aggregate = {
                    k: sum(r["metrics"][k] for r in completed) / len(completed)
                    for k in keys
                    if isinstance(completed[0]["metrics"][k], (int, float))
                }
            return {"experiment": exp, "runs": runs, "aggregate": aggregate}
        finally:
            conn.close()

    def get_run(self, run_id: int, events_limit: int = 50) -> dict[str, Any]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM experiment_runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"run {run_id} not found")
            d = self._row_to_dict(row)
            d["metrics"] = json.loads(d.pop("metrics_json")) if d.get("metrics_json") else None
            d["summary"] = json.loads(d.pop("summary_json")) if d.get("summary_json") else None
            events = json.loads(d.pop("events_json")) if d.get("events_json") else []
            d["events"] = events[-events_limit:]
            return d
        finally:
            conn.close()

    def get_run_events(self, run_id: int, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT events_json FROM experiment_runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"run {run_id} not found")
            events = json.loads(row["events_json"]) if row["events_json"] else []
            limit = max(1, min(limit, 1000))
            offset = max(0, offset)
            return {
                "run_id": run_id,
                "total": len(events),
                "limit": limit,
                "offset": offset,
                "events": events[offset:offset + limit],
            }
        finally:
            conn.close()

    # ---------------------------------------------------------------- models
    def _decorate(self, info: dict[str, Any]) -> dict[str, Any]:
        info["example_spec"] = {
            "schema_version": 1,
            "model_id": info["model_id"],
            "model_version": info["version"],
            "params": self.registry.get(info["model_id"], info["version"]).param_model().model_dump(),
            "stop_condition": {"type": "steps", "value": 10000},
            "seed": 42,
        }
        info["versions"] = self.registry.versions_of(info["model_id"])
        return info

    def model_versions(self, model_id: str) -> list[dict[str, Any]]:
        """某个模型 id 的全部版本目录条目，按版本号升序（末位即最新）。"""
        return [self._decorate(info) for info in self.registry.list() if info["model_id"] == model_id]

    def list_models(self) -> list[dict[str, Any]]:
        """模型目录：每个 model_id 一条（最新版本）+ `versions` 列出全部可用版本。

        同一 id 在目录里出多条会让前端下拉重复，也让按 id 取详情时命中到最旧版本
        （R32 实测：注册 1.0.0/2.0.0/10.0.0 时 `/api/models` 给出 3 条、
        `/api/models/sir` 返回 1.0.0，而真正跑起来用的是另一个版本）。"""
        latest: dict[str, dict[str, Any]] = {}
        for info in self.registry.list():  # registry.list() 版本升序 → 覆盖即留最新
            latest[info["model_id"]] = self._decorate(info)
        return list(latest.values())

    def validate_spec_only(self, spec_raw: dict[str, Any]) -> dict[str, Any]:
        spec, model_cls = validate_spec(spec_raw, self.registry)
        normalized = spec.model_dump()
        # 契约承诺 normalized_spec 是「补齐后的形态」（API_CONTRACT R25），但此前它只是
        # 把入参原样吐回来：model_version/display_name 为 None、params 不含默认值。
        normalized["model_version"] = model_cls.version
        normalized["display_name"] = model_cls.display_name
        normalized["params"] = model_cls.param_model(**spec.params).model_dump()
        return {"valid": True, "errors": [], "normalized_spec": normalized}
