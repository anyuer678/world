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
  default_max_steps}, session:{max_step_batch}, pagination:{max_limit, max_events, max_offset},
  experiment:{name_max_length}}`——值由服务端 pydantic 校验规则与模块常量**现场导出**，前端批量面板与会话单步输入据此校验，不再各存一份
  硬编码上限（有测试绑定两端）。
  `session.max_step_batch` = 单次 `POST /api/sessions/{id}/step` 的 `n` 上限（R47，默认 1000000），
  与后端校验共用同一常量；前端据此设置 `input max` 并在越界时禁用提交，使该 422 在界面里不可达。
  **实验名称 ≤200 字符，创建与克隆共用服务层校验**（R60）：上限常量 `EXPERIMENT_NAME_MAX`
  同时供 `CreateExperimentBody` 与 `create_experiment()` 使用；此前 `clone` 走服务层可写入
  10000 字符的名称（实测 200 OK），而直接创建同样名称是 422。
  **分页参数有边界**（R59）：所有列表端点（`/experiments`、`/batches`、`/batches/{id}/items`、
  `/runs/{id}/events`）的 `limit` 必须 `1..1000`、`offset` 必须 `≥0`，越界一律 422；
  事件数量 `events_limit` 取 `0..500`，`0` 表示**不返回事件**；`offset ≤ 1,000,000,000`。
  **路径 id 限定在 1..2^63-1**（R64）：超出返回 422——此前 `offset=999999999999999999999`
  或同样大的 id 会让 Python 大整数进入 SQLite，抛 `OverflowError` 变成 500。此前未校验时 `limit=-1`
  在 SQLite 里等于无上限（实测返回全部 52 条），`events_limit=0` 的切片 `[-0:]` 反而返回全部事件。

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
- `POST /api/experiments/{id}/run` body=`{wait?:bool}` → **200** `{experiment_id, run_id, status:"queued"}`
  （R35 实测纠正：既不是 202，也不返回 `runs:[…]` 数组）；`wait=true` 时阻塞到跑完再返回同一形态
  - **提交时即校验库中 spec**：模型或版本不在注册表（插件模块没配好、版本被撤下）→ 422
    `spec_invalid` + `errors[].code="unknown_model"`，与 create/clone/建批同口径；
    校验发生在状态改写**之前**，失败不会把实验留在 `running`
- `GET /api/experiments/{id}/result` → `{experiment, runs:[RunDetail], aggregate?}`；
  run 条目键为 **`id`**（不是 `run_id`——`run_id` 只出现在 POST run/rerun 的响应里），
  完整形态 `{id, experiment_id, repeat_index, seed, status, steps, sim_time, metrics,
  summary, result_sha256, duration_ms, started_at, finished_at, error}`
- `POST /api/experiments/{id}/cancel` → Experiment
- `POST /api/experiments/{id}/rerun` → 200 `{experiment_id, run_id, status}`（重新排队；同样在提交时校验）
- `GET /api/experiments/{id}/report?format=markdown|json`（阶段 5）→
  markdown 时 `text/markdown` 附件下载（含 spec JSON 块、逐运行指标、聚合均值、
  result_sha256 说明）；json 时返回报告结构，键为
  `{report_version: 1, generated_at, software{app_version, engine_version,
  python_version}, experiment, runs, aggregate, run_list_note, comparability_note}`
  （`report_version` 是面向未来的结构版本标签，当前只有 1，服务端不做版本协商；
  报告内容全部来自库中已记录数据，不做二次派生）

## 运行
- `GET /api/runs/{run_id}` → RunDetail（status、steps、sim_time、metrics、summary、events 最近 N 条、error、result_sha256）
  - **`error` 字段口径（R35）**：预期内的失败——spec 校验、注册表查无（`SpecValidationError`/
    `RegistryError`）、引擎主动抛出的 `SimulationError`——只写一行 `类型: 原因`，**不带栈、
    不含本机绝对路径**（它会随报告 markdown/JSON 外流，栈对读者只是噪声；批量单项与交互会话
    本来就是同样的紧凑口径）。其它意外异常仍保留 3 层栈用于定位。绑定测试：
    `test_run_failure_reporting.py::test_describe_run_failure_keeps_expected_errors_one_line`
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
  **并发与单项墙钟先被服务端上限钳制，再落库并回显**（R43 成文）：
  `concurrency → min(concurrency, engine.max_workers)`、
  `per_run_wall_seconds → min(值, engine.max_wall_seconds)`；Batch 里返回的是**生效值**
  而非请求值（例：请求 `concurrency=8`、服务端 `max_workers=2` → 批量记录 `2`）。
  两个上限都可从 `GET /api/limits` 读到，调用方据此决定请求值即可。
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
  - **会话是内存态、按空闲时长回收**：距最后一次访问超过 `Settings.session_ttl_seconds`
    （环境变量 `WORLDLAB_SESSION_TTL_SECONDS`，默认 3600 秒）后，会话在下次任意会话操作时被清除
    并停止其后台线程，之后 `GET`/`POST` 一律 **404 `not_found`**（R39 成文；要长期保存结果请
    「存配置为新实验」落库，而非依赖会话常驻）
- `GET /api/sessions/{id}` → SessionState：
  `{session_id, status, stop_reason, error, model_id, model_version, model_type, display_name, visualizer, spec, snapshot, events[], chunk_steps}`；
  snapshot 为 `{step, time, status, state, metrics}`（**模拟时间键名是 `time`**，非 sim_time）
- `DELETE /api/sessions/{id}` → 204（立即返回；若该会话正在运行，后台线程跑完当前分片自行结束，
  不再同步等待——R40）
- `POST /api/sessions/{id}/step` body=`{n?:int=1}` → SessionState（同步步进）
- `POST /api/sessions/{id}/run` → SessionState（后台线程启动连续运行；status=running）
- `POST /api/sessions/{id}/pause` → SessionState（协作式暂停，生效粒度 ≤ 一个分片）。
  **立即返回**（R40）：响应体是请求前的状态（通常仍是 `running`），`paused` 在 ≤1 个分片内
  由后台线程落定，客户端按 `GET /api/sessions/{id}` 轮询即可——前端本就 300 ms 轮询。
  旧实现（R39）会阻塞到线程退出：256×256 元胞自动机实测一片 4.3 s，暂停请求随之挂住数秒。
  暂停**落 `paused`**（可 `resume`、可 `step`），不是 `cancelled`（R39 修：此前 `_stop_thread`
  同时置 cancel/pause 两个标志，运行循环先查 cancel，于是暂停实为取消——`resume`/`step`
  一律 409「session already finished」，只能重置丢进度）。`cancelled` 只在丢弃路径出现
  （`DELETE`、空闲回收、进程关停）
  - 后台线程尚未离开当前分片时（`stopping` 窗口），`step`/`run`/`checkpoint`/`restore`
    一律 **409 `conflict`**（message 含 "session is stopping…" / "pause the session before…"），
    可重试、粒度 ≤ 一个分片；不返回 500，也不在半路改动引擎（R39）。`reset` 自 R40 起
    不再报错而是排队（见下），`pause` 自 R40 起不再阻塞（见上）
- `POST /api/sessions/{id}/resume` → SessionState
- `POST /api/sessions/{id}/reset` → SessionState（回到 step=0，同种子同参数 ⇒ 重放结果一致）。
  运行中调用时**立即返回、在分片边界由后台线程执行**（R40）：响应仍是交接前的状态，
  `idle`/step 0 在 ≤1 个分片内出现；期间引擎不被并发触碰。终态（completed 等）下同步完成。
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
