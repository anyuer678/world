# REST API 契约（全量：阶段 1–6 + R1–R30，逐条实测对齐）

Base URL: `http://localhost:8000`，前缀 `/api`。校验错误 422，业务错误 400/404/409。

**`detail` 有两种形状，消费方必须都处理（R30 实测固化）**：

1. **对象形状**——应用层抛出的错误与 spec 校验：
   `{"detail": {"code": "spec_invalid", "message": "spec validation failed", "errors": [{code, message}]}}`。
   `errors[]` 仅 spec 类 422 携带（字段路径 + pydantic 原文，如 `params.servers`）；
   400/404/409 同形状但无 `errors`（实测 404 = `{"code":"not_found","message":"run 9 not found"}`）。
2. **数组形状**——FastAPI 自己的请求体规则校验（`CreateBatchBody` 的 `repeats`/`max_retries`/
   `concurrency`/`name` 长度等约束越界）：
   `{"detail": [{"type": "less_than_equal", "loc": ["body", "repeats"], "msg": "…", "input": 150, "ctx": {…}}]}`，
   **没有** `code`/`message` 键。

两种形状都有测试绑定（`test_api.py::test_422_has_two_distinct_detail_shapes`）。
前端 `api.ts:errorDetailMessage()` 把两者统一还原成可读文案——只读对象形状时，
数组形状会退化成裸「422」，用户看不到失败原因（R30 修复的缺陷）。

## 系统
- `GET /api/health` → `{status:"ok", app_version, engine_version}`
- `GET /api/limits`（R29）→ `{batch:{max_items, name_max_length, repeats_min/max,
  max_retries_min/max, concurrency_min/max}, engine:{max_wall_seconds, max_workers,
  default_max_steps}}`——值由服务端 pydantic 校验规则与模块常量**现场导出**，
  前端批量面板据此校验，不再各存一份硬编码上限（有测试绑定两端）。

## 模型
- `GET /api/models` → `{models: [ModelInfo]}`，**每个 model_id 恰好一条**（列最新版本；
  R32 前同 id 多版本会出多条，前端下拉重复、且详情命中最旧版本）。ModelInfo：
  `{model_id, display_name, description, model_type, version, versions: string[],
  params_schema(JSON Schema), example_spec, scenarios[]}`
  （`versions` 按版本号数字组分升序，如 `["1.0.0","2.0.0","10.0.0"]`；
  `example_spec.model_version` 与所列 `version` 一致。
  scenarios 为「一键场景」：`{id, title, description, params}` 必填非空，
  `seed`/`stop_condition` **可选**（R24：工作台点卡片时省略即沿用当前表单值）；
  R3 起，插件模型同样可声明，详见 PLUGINS.md）
- `GET /api/models/{model_id}` → ModelInfo；**默认返回最新版本**，
  `?version=` 可取指定版本；未知 model_id 或未知版本一律 404 `not_found`，
  后者 message 里带 `available: [...]`（R32 实测）
- `POST /api/models/{model_id}/validate` body=spec（**裸 spec，不包 `{"spec":…}`**）→
  `{valid, errors[], normalized_spec}`；**normalized_spec 是「补齐后的有效形态」（R33 起名副其实，
  此前只回吐入参）**：`model_version`= 注册表解析出的实际版本（未钉则数值最新）、
  `display_name`= 模型显示名、`params`= 套用默认值后的完整参数、`notes`= 迁移说明。
  该端点对非法输入返回 **200 + `valid:false`**（不是 422），未知版本时
  `errors[0].code == "unknown_model"`
- **`spec.model_version` 有实际效力**（R33 探针 + 测试绑定）：它决定校验用哪一版参数 Schema、
  以及运行用哪一版模型实现；不钉则取数值最新版本。钉了注册表里没有的版本时，
  `POST /api/experiments` 是 **422 `spec_invalid`**（`errors[].code="unknown_model"`），不是 500。
  这是「不同模型版本的实验不默认可比」的执行层依据

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
  markdown 时 `text/markdown` 附件下载（含 spec JSON 块、逐运行指标、聚合均值、
  result_sha256 说明）；json 时返回报告结构，键为
  `{report_version: 1, generated_at, software{app_version, engine_version,
  python_version}, experiment, runs, aggregate, run_list_note, comparability_note}`
  （`report_version` 是面向未来的结构版本标签，当前只有 1，服务端不做版本协商；
  报告内容全部来自库中已记录数据，不做二次派生）

## 运行
- `GET /api/runs/{run_id}` → RunDetail（status、steps、sim_time、metrics、summary、events 最近 N 条、error、result_sha256）
- `GET /api/runs/{run_id}/events?limit=100&offset=0` → `{run_id, total, limit, offset, events}`
  （R25 实现契约承诺的分页端点；limit 钳到 1..1000，越界 offset 返回空数组，
  未知 run 404。事件来自落库快照 `events_json`——每个 run 只持久化**最近 100 条**
  事件，故 `total ≤ 100`；交互会话的内存态另有 500 条环形日志，两者口径不同）

## 批量实验（阶段 4 起，后台执行，落库）
- `POST /api/batches` body=`{name, spec, grid, repeats, seed_strategy?, max_retries?, concurrency?, per_run_wall_seconds?}`
  → 201 Batch（status=pending）。grid 为「参数名 → 取值列表」的笛卡尔积扫描，
  **参数名必须是该模型的顶层字段：不支持点号嵌套路径**（如 `params.delay_mean`），
  也不接受空列表——两者都在建批时 422 `spec_invalid` 并指明 `code:"grid"` 与具体键名
  （静默接受会让「所有组合结果相同」被误读成真的无敏感性，R34 有测试绑定）。
  与 repeats 相乘后超 `MAX_BATCH_ITEMS` 直接 400（限量前移，不物化，R1）
- `GET /api/batches?limit&offset` → `{total, batches:[概要]}`，概要 =
  `{id, name, model_id, model_version, status, total_items, repeats, seed_strategy,
  seed_base, created_at, duration_ms, done_items}`（无 started_at/finished_at）。
  **进度计数在两个端点形状不同**（R30 实测）：列表用扁平 `done_items`
  （已到终态项数，含 `step_limit`/`wall_timeout` 这类非成功终态），
  详情不给 `done_items` 而给 `counts`（状态→数量分桶，进度 = 终态桶求和）
- `GET /api/batches/{id}` → Batch（含 spec/grid/counts{状态→数}；
  终态含 summary：每组合的聚合指标 `{n, mean, std, p50, p90, ci95_low, ci95_high}`）
- `GET /api/batches/{id}/items?limit&offset` → `{total, items:[{item_index, combo, repeat_index, seed, status, attempts, steps, sim_time, metrics, result_sha256, error, duration_ms}]}`，按 `item_index` 升序、分页稳定（续读不重不漏）。
  **`total` 是全量条数**：批量面板一次只取一页（50），因此表头必须写「显示前 N / 共 M 项」并指向
  CSV 导出（R34，导出走 500/页循环，始终含全部项）
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
- `POST /api/sessions/{id}/checkpoint` → `{checkpoint}`；checkpoint 是 JSON 字典，键为
  `{engine_version, model_id, model_version, model_type, params_digest, step, clock,
  status, rng, model_state, engine}`（R27 实测列出，防手写形状失真）
- `POST /api/sessions/{id}/restore` body=`{checkpoint}` → SessionState。
  **指纹不符一律 409 `conflict`**（绝不 500）：`model_id` / `engine_version` /
  `model_version` / `params_digest` 四项任一不匹配即拒绝，message 指明具体哪项；
  有效恢复后 status 取检查点内快照当时的 status（实测单步后检查点恢复 → `paused`）
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
