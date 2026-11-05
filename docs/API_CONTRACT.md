# REST API 契约（全量：阶段 1–6 + R1–R25，逐条实测对齐）

Base URL: `http://localhost:8000`，前缀 `/api`。错误统一：
`{"detail": {"code": "...", "message": "..."}}`，校验错误 422，业务错误 400/404/409。
422 的 `detail` 额外带 `errors: [{code: "params.servers", message: "…"}]`（字段路径 +
pydantic 原文，前端横幅逐条显示；实测 `spec_invalid` 即此形状）。

## 系统
- `GET /api/health` → `{status:"ok", app_version, engine_version}`

## 模型
- `GET /api/models` → `{models: [ModelInfo]}`，ModelInfo：
  `{model_id, display_name, description, model_type, version, params_schema(JSON Schema), example_spec, scenarios[]}`
  （scenarios 为「一键场景」：`{id, title, description, params}` 必填非空，
  `seed`/`stop_condition` **可选**（R24：工作台点卡片时省略即沿用当前表单值）；
  R3 起，插件模型同样可声明，详见 PLUGINS.md）
- `GET /api/models/{model_id}` → ModelInfo
- `POST /api/models/{model_id}/validate` body=spec（**裸 spec，不包 `{"spec":…}`**）→
  `{valid, errors[], normalized_spec}`；normalized_spec 另含
  `model_version/display_name/notes`（迁移补齐后的形态）

## 实验
- `POST /api/experiments` body=`{name, spec}` → Experiment（status=created）
  - spec 经 schema 迁移+校验+参数双层校验，非法 422
- `GET /api/experiments?limit&offset&model_id&tag` → `{total, experiments:[Experiment]}`
- `GET /api/experiments/{id}` → Experiment（含 runs 概要）
- `DELETE /api/experiments/{id}` → 204
- `POST /api/experiments/{id}/clone` body=`{name?, spec_overrides?}` → 新 Experiment
- `PUT /api/experiments/{id}/tags` body=`{tags:[string]}` → Experiment
- `POST /api/experiments/{id}/run` body=`{wait?:bool}` → 202 `{experiment_id, runs:[run_id]}`
  或 wait=true 时同步返回终态（阶段 1 前端先用 wait）
- `GET /api/experiments/{id}/result` → `{experiment, runs:[RunDetail], aggregate?}`；
  run 条目键为 **`id`**（不是 `run_id`——`run_id` 只出现在 POST run 的 202 响应里），
  完整形态 `{id, experiment_id, repeat_index, seed, status, steps, sim_time, metrics,
  summary, result_sha256, duration_ms, started_at, finished_at, error}`
- `POST /api/experiments/{id}/cancel` → Experiment
- `POST /api/experiments/{id}/rerun` → 202（重置为 pending 并重新排队）
- `GET /api/experiments/{id}/report?format=markdown|json`（阶段 5）→
  markdown 时 `text/markdown` 附件下载；json 时返回报告结构
  （含 `comparability_note` 跨版本可比性说明）

## 运行
- `GET /api/runs/{run_id}` → RunDetail（status、steps、sim_time、metrics、summary、events 最近 N 条、error、result_sha256）
- `GET /api/runs/{run_id}/events?limit=100&offset=0` → `{run_id, total, limit, offset, events}`
  （R25 实现契约承诺的分页端点；limit 钳到 1..1000，越界 offset 返回空数组，
  未知 run 404。事件来自落库快照 `events_json`——每个 run 只持久化**最近 100 条**
  事件，故 `total ≤ 100`；交互会话的内存态另有 500 条环形日志，两者口径不同）

## 批量实验（阶段 4 起，后台执行，落库）
- `POST /api/batches` body=`{name, spec, grid, repeats, seed_strategy?, max_retries?, concurrency?, per_run_wall_seconds?}`
  → 201 Batch（status=pending）。grid 为「参数名 → 取值列表」的笛卡尔积扫描，
  与 repeats 相乘后超 `MAX_BATCH_ITEMS` 直接 400（限量前移，不物化，R1）
- `GET /api/batches?limit&offset` → `{total, batches:[Batch 概要]}`
- `GET /api/batches/{id}` → Batch（含 spec/grid/counts{状态→数}；
  终态含 summary：每组合的聚合指标 `{n, mean, std, p50, p90, ci95_low, ci95_high}`）
- `GET /api/batches/{id}/items?limit&offset` → `{total, items:[{item_index, combo, repeat_index, seed, status, attempts, steps, sim_time, metrics, result_sha256, error, duration_ms}]}`
- `POST /api/batches/{id}/cancel` → Batch（协作式取消；在途上限 = min(concurrency, max_workers)，R1）
- `GET /api/batches/{id}/export.csv` → 逐 item 明细 CSV 附件
- `GET /api/batches/{id}/findings`（R6）→ `{findings[], note}`：
  两层描述性自动发现——①jump：1-D 扫描相邻点因子 ≥3（触及精确零记
  `ratio: null`，0→0 不算；R23 起附 `ci_overlap` 三态——false=两段 95% CI
  不相交（跳变显著）、true=相交（可能落在重复间噪声内）、null=无法判定，
  含任一侧 n<2 或 fixed 种子导致的零宽退化区间），②dispersion：n≥3 且 CV ≥0.5；每类截 5 条；
  note 固定声明「只描述不因果」

## 交互会话（阶段 2，进程内，不入库）
- `GET /api/sessions` → `{sessions: [SessionState 概要]}`
- `POST /api/sessions` body=`{spec}` → 201 SessionState（spec 校验同实验；会话内 spec 固定，改 spec 需重建）
- `GET /api/sessions/{id}` → SessionState：
  `{session_id, status, stop_reason, error, model_id, model_version, model_type, display_name, visualizer, spec, snapshot, events[], chunk_steps}`；
  snapshot 为 `{step, time, status, state, metrics}`（**模拟时间键名是 `time`**，非 sim_time）
- `DELETE /api/sessions/{id}` → 204
- `POST /api/sessions/{id}/step` body=`{n?:int=1}` → SessionState（同步步进）
- `POST /api/sessions/{id}/run` → SessionState（后台线程启动连续运行；status=running）
- `POST /api/sessions/{id}/pause` → SessionState（协作式暂停，生效粒度 ≤ 一个分片）
- `POST /api/sessions/{id}/resume` → SessionState
- `POST /api/sessions/{id}/reset` → SessionState（回到 step=0，同种子同参数 ⇒ 重放结果一致）
- `POST /api/sessions/{id}/checkpoint` → `{checkpoint}`（JSON，含 RNG state）
- `POST /api/sessions/{id}/restore` body=`{checkpoint}` → SessionState
- 会话语义：进程内存储（重启即失），服务重启后 id 404；后台运行按 256 步分片推进
  （`session_service.CHUNK_STEPS = 256`）；**running 期间的 GET 直接返回 worker 在
  分片边界写入的缓存快照**（粒度 = 一个分片，非实时锁内重建），前端每 300 ms 轮询一次；
  status ∈ idle/running/paused/completed/step_limit/wall_timeout/cancelled/error。

## 术语
- Experiment = 一次模型+参数+种子的配置记录；Run = Experiment 的一次实际执行
  （阶段 1 repeats=1；阶段 4 批量会生成多 Run）。
- 所有数值结果均来自真实运行，禁止伪造；`result_sha256` 供校验。
- 可复现性（R1）：Batch item 的 seed 由种子策略从 batch 种子派生并逐 item 落库，
  summary 聚合口径与逐 item 指标同源；检查点绑定 model_version + params_digest。
