# WorldLab 架构设计

起始于阶段 0/1 的设计文档，已随 R1–R36 的改动持续修订。本文的「文件清单 /
`Limits` 字段 / 数据表名 / REST 路径」四类声称由 `backend/tests/test_docs_consistency.py`
与磁盘、OpenAPI、迁移文件**双向对账**——写错或漏写会直接红。

## 总体分层

```
┌──────────────────────────────────────────────┐
│ frontend (React+TS+Vite)  实验工作台/可视化     │  只依赖 REST 契约（进度轮询，无 WebSocket）
├──────────────────────────────────────────────┤
│ api (FastAPI)  REST + 异常映射 + 后台任务编排   │
├──────────────────────────────────────────────┤
│ services  实验/会话/批量/分析/报告/基准          │
├──────────────────────────────────────────────┤
│ core/engine  统一模拟接口（时间步进/离散事件）    │  不依赖 API、DB、前端
│ core/schema  版本化模型描述格式 + 校验 + 迁移     │
│ core/registry + plugins + stats                │
│ db  SQLite + 顺序 .sql 迁移                     │
├──────────────────────────────────────────────┤
│ models/*  模型插件包（内置八个）                 │  只依赖 core 抽象
└──────────────────────────────────────────────┘
```

依赖方向单向向下：`models → core`，`services → core + db`，`api → services`。
`core` 与 `models` 不 import `fastapi`/`sqlite3`。可视化与模拟逻辑通过
「模型状态快照 + 事件记录」两种统一格式解耦。

## 文件清单（与磁盘对账）

```
# 根
  docker-compose.yml
  LICENSE
  README.md
  .gitignore

# 后端
  backend/pyproject.toml
  backend/uv.lock
  backend/Dockerfile
  backend/.dockerignore
  backend/scripts/benchmark.py   — 基准脚本入口；模型清单来自 registry.builtin_ids()
  backend/migrations/0001_initial.sql
  backend/migrations/0002_batch_runs.sql
  backend/app/api/routes.py   — 全部 REST 路由（含 /api/limits；会话与批量进度由前端轮询）
  backend/app/config.py   — Settings.from_env()：DB 路径、max_workers、default_max_steps、墙钟、事件环、取消粒度、插件模块
  backend/app/core/engine/base.py
  backend/app/core/engine/engines.py   — SimulationEngine + 时间步进/离散事件两种实现 + Limits
  backend/app/core/engine/event_queue.py   — 按 (time, priority, seq) 排序的事件堆
  backend/app/core/engine/models_base.py   — WorldLabParams 基类 + TimeSteppedModel/DiscreteEventModel
  backend/app/core/engine/rng.py
  backend/app/core/plugins.py   — WORLDLAB_PLUGIN_MODULES 加载外部插件（register(registry) 钩子）
  backend/app/core/registry.py   — 模型注册表；builtin_ids() 是内置模型清单的唯一事实源
  backend/app/core/schema/errors.py   — SpecValidationError（映射 422 detail.errors[]）
  backend/app/core/schema/evolution.py   — register_migration / upgrade_spec（v0→v1 升级链）
  backend/app/core/schema/spec.py   — ModelSpec 与 validate_spec（pydantic v2，extra=forbid）
  backend/app/core/stats.py   — 均值/样本标准差/分位数/正态近似 95% CI/pearson（零方差返回 None）
  backend/app/db/connection.py   — connect()：WAL、foreign_keys=ON、busy_timeout
  backend/app/db/migrations.py   — 按文件序号在事务内应用 .sql，可重入
  backend/app/main.py   — create_app()：异常处理器（spec→422、not_found→404、conflict→409）与 lifespan
  backend/app/models/cache_sim/model.py
  backend/app/models/cache_sim/params.py
  backend/app/models/cellular_automaton/model.py
  backend/app/models/cellular_automaton/params.py
  backend/app/models/cpu_scheduling/model.py
  backend/app/models/cpu_scheduling/params.py
  backend/app/models/predator_prey/model.py
  backend/app/models/predator_prey/params.py
  backend/app/models/queueing/model.py
  backend/app/models/queueing/params.py
  backend/app/models/schelling/model.py
  backend/app/models/schelling/params.py
  backend/app/models/sir/model.py
  backend/app/models/sir/params.py
  backend/app/models/traffic_network/model.py
  backend/app/models/traffic_network/params.py
  backend/app/services/analysis_service.py   — 汇总、敏感性、扫描跳变与离散发现（CI 重叠三态）
  backend/app/services/batch_service.py   — 批量：网格展开、种子策略、并发上限、协作式取消、重试
  backend/app/services/benchmarks.py   — 基准原语（bench_engine 等，真实运行计时）
  backend/app/services/experiment_service.py   — 实验/运行编排、检查点绑定、describe_run_failure()
  backend/app/services/reporting.py   — 报告 markdown/JSON 与批量 CSV 导出（只用库中已记录数据）
  backend/app/services/session_service.py   — 交互会话（分片运行、事件环、暂停/恢复/重置/检查点）

# 前端
  frontend/package.json
  frontend/package-lock.json
  frontend/index.html
  frontend/vite.config.ts
  frontend/Dockerfile
  frontend/nginx.conf
  frontend/src/App.tsx
  frontend/src/BatchPanel.tsx
  frontend/src/ComparePanel.tsx
  frontend/src/ParamForm.tsx
  frontend/src/SimView.tsx
  frontend/src/TrafficPanel.tsx
  frontend/src/api.ts
  frontend/src/chartRender.ts
  frontend/src/findings.ts
  frontend/src/labels.ts
  frontend/src/logic.test.ts
  frontend/src/main.tsx
  frontend/src/schema.ts
  frontend/src/summary.ts
  frontend/src/sweepChart.ts
  frontend/src/trafficRender.ts
  frontend/src/types.ts
  frontend/src/vite-env.d.ts

# 后端测试（tests/test_*.py 若干；文件数由 README 的计数行与 pytest 汇总给出，不在此写死）
```

## 统一模拟接口（backend/app/core/engine/base.py）

所有模型实现两种引擎语义之一，不得混合（注册时校验基类与 `model_type` 一致）：

- **时间步进 (`time_stepped`)**：`step()` 以固定 Δt 推进，时间严格单调 +Δt。
- **离散事件 (`discrete_event`)**：模型向事件队列投递 `(time, priority)` 事件，
  引擎按 `(time, priority, seq)` 弹出，`seq` 为投递顺序，保证同刻事件确定性；
  零延迟事件在同刻按投递顺序继续处理，`Limits.zero_delay_chain_limit` 设单刻事件链上限防死循环。

统一能力由 `SimulationEngine` 提供：`step()` / `run()` / `reset()` /
`checkpoint()` / `restore()` / 取消回调 / 事件环形日志 / 指标收集。

**资源上限就是 `Limits` 这四个字段**（没有别的）：
`max_steps`、`max_wall_seconds`、`zero_delay_chain_limit`、`cancel_poll_interval`。
模拟时间上限不在 `Limits` 里，而是停止条件 `stop_condition` 的一种：
`steps`（步/事件数上限）、`sim_time`（模拟时间上限）、`until_empty`（事件队列排空，仅 DES）。
运行结果 `RunResult.status` ∈ `completed | step_limit | wall_timeout | cancelled | chunk_done`。

**检查点 = JSON 可序列化字典**（R1 起绑定版本与参数指纹，防跨版本误恢复）：
`{engine_version, model_id, model_version, model_type, params_digest, step, clock,
status, rng, model_state, engine}`——`engine` 子字典按引擎类型分派：离散事件为
`{queue, seq}`，时间步进为 `{}`。序列化走 `json.loads(json.dumps(cp))`：一次往返同时
完成深拷贝与可序列化校验。四项指纹任一不符时 `restore()` 抛 `SimulationError`，
API 层一律映射为 **409 conflict**（不是 500）。RNG 用 `random.Random`，其 state 为纯 int 元组，
恢复后与不中断运行逐比特一致（有测试保证）。

**快照与事件记录**：
- 快照 `{step, time, status, state, metrics}`（注意时间键是 `time`，不是 `sim_time`）。
- `EventRecord{seq, time, kind, message, data}` —— 事件环形日志，容量取
  `Settings.event_log_size`（默认 500）；落库时只保留 run 的最后 100 条
  （`GET /api/runs/{run_id}/events` 分页读取，`total ≤ 100`）。

## 模型描述格式（ModelSpec）

`schema_version: 1` 的 JSON：字段为
`{schema_version, model_id, model_version?, display_name?, params, stop_condition, seed?, notes}`
——**没有 `model_type` 字段**，引擎类型由注册表里的模型类决定。
校验与迁移：`core/schema/spec.py:validate_spec()`（pydantic **v2**，`extra="forbid"`）
+ `core/schema/evolution.py` 的 `register_migration()` / `upgrade_spec()` 升级链
（当前只有一条 v0→v1：旧原型 `{model, params, horizon, seed}` 迁成 `model_id` + `stop_condition:{type: "steps", value: horizon}`）。
参数约束由模型插件声明的 pydantic 参数模型校验；spec 形状与参数**双层**都通过才允许建实验。

`model_version` 有实际效力（R33）：它决定校验用哪版参数 Schema、执行用哪版模型实现，
未指定则解析为数值最新版本（版本号按数字组分比较，`10.0.0 > 2.0.0`）。

## 数据库（SQLite + 顺序迁移）

由 `migrations/*.sql` 创建，实际表为：

| 表 | 用途 |
| --- | --- |
| `schema_migrations` | 迁移按文件序号在事务内应用，可重入 |
| `model_registrations` | 已注册模型版本快照（`experiment_service` 在建实验时 `INSERT OR IGNORE`） |
| `experiments` | 名称、model_id+model_version、完整 spec_json、seed、status、engine/software 版本、起止时间、duration_ms、error、tags、parent_experiment_id |
| `experiment_runs` | repeat_index、seed、status、steps、sim_time、metrics_json、summary_json、events_json、error、duration_ms、result_sha256 |
| `batch_runs` | 批量：spec/grid/repeats/seed_strategy/concurrency/per_run_wall_seconds/total_items/status/counts 来源 |
| `batch_items` | 逐组合逐重复的项：combo_json、seed、status、attempts、steps、sim_time、metrics_json、result_sha256、error、duration_ms |
| `result_artifacts` | **已建表但当前没有写入方**——明细产物（timeseries 等）路径尚未实现，保留给后续；不要把它当可用能力 |

`error` 字段口径（R35）：预期内失败只存一行 `类型: 原因`（**不含栈与本机绝对路径**，
它会随导出报告外流）；非预期异常才保留 3 层栈。
WAL 模式、`foreign_keys=ON`、`busy_timeout=30000`；每个请求与工作线程各用独立连接，写事务短小。

**跨版本不可比的落点在前端，不在 API**：`GET /api/experiments/{id}/result` 与比较视图都只如实
带上各自的 `model_id`/`model_version`，由 `frontend/src/ComparePanel.tsx` 判断所选实验是否
跨模型或跨版本并显示「默认不可直接比较」的提示；报告里则由
`comparability_note` 文案声明。**没有 `cross_version` 这类服务端警告字段**（旧文档把它写成
已完成能力，实为阶段 4 的设计意图，R36 更正）。

## 后台执行模型

没有独立的 worker 模块：**三个服务各自持有自己的 `ThreadPoolExecutor`**
（`ExperimentService`、`BatchService`、`SessionService`），并发规模取 `Settings.max_workers`
（默认 2）；批量的在途项数上限是 `min(concurrency, max_workers)`，建批时算好落库。
会话的停止有两个互斥意图（R39 前只有一个）：**暂停**（`pause_event`，worker 在分片边界落
`paused`，可继续可单步）与**取消**（`cancel_event`，落 `cancelled` 终态，只用于
`DELETE`/空闲回收/进程关停这类丢弃路径）。线程未离开当前分片时 `stopping` 标志为真，`step`/`run`/`checkpoint`/`restore` 返回可重试的 409，
所有权交接（落状态 + 清标志 + 执行排队动作）在一次加锁内完成。**控制端点不等待分片**（R40）：
`pause` 只置标志立即返回，`reset` 在运行中排队到边界由 worker 执行，`DELETE` 摘除即返回；
否则一个 4.3 s 的大网格分片会把 HTTP 请求和无关会话的 TTL 回收一起拖住。
取消是**进程内的 `threading.Event` 标志**：引擎每 `cancel_poll_interval`（默认 256）步
检查一次，同时对照 `max_wall_seconds` / `max_steps` 上限，超限即落
`cancelled/step_limit/wall_timeout` 终态。`Limits` 的四个字段在**三条路径上都取自同一份
`Settings`**（R37：会话侧曾漏传后两项，使两个环境变量对交互会话静默无效，现由测试锁定）。
API 事件循环内从不直接跑模拟。**服务必须以单进程运行**（R66）：会话对象与取消标志都只存在于
当前进程，`--workers > 1` 会让请求落到不持有它们的 worker 上（实测会话 GET 12 次里 9 次 404、
单次取消返回 200 却仍然运行）。
交互会话是**内存态**资源：`SessionService` 在每次会话操作前回收空闲超过
`Settings.session_ttl_seconds`（`WORLDLAB_SESSION_TTL_SECONDS`，默认 3600 秒）的会话并停其线程，
被回收的会话后续访问返回 404（R39 成文）。

## 可视化

前端按模型声明的 `visualizer.kind` 分发（`backend/app/models/*/model.py` 提供 kind，
`frontend/src/SimView.tsx` 实现对应视图）。当前有专用视图的 kind 与文档口径见
`docs/PLUGINS.md`；**未识别的 kind 自动落到通用状态表 `StateTable`**，
所以插件先声明一个新 kind 也能看到数据，只是没有定制图形。
工作台数据全部来自真实接口（`POST /api/sessions/{session_id}/step`、
`GET /api/sessions/{session_id}`、事件分页端点），播放控制 = 引擎单步/分片连续运行，无预录动画。

## 插件式模型库

`registry.register(cls)` 注册模型类；模型包自包含（params、model、示例 spec、tests）。
内置模型由 `backend/app/models/__init__.py` 逐包 import（每加一个模型加一行），
外部插件由 `WORLDLAB_PLUGIN_MODULES` 载入。新增模型不改 core/api/services 代码；
`registry.builtin_ids()` 是内置模型清单的唯一事实源，基准脚本、端到端测试与
文档一致性测试都由它派生（不要再抄写名单）。契约细节见 `docs/PLUGINS.md`。
