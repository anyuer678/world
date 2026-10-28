# WorldLab 架构设计（v0.1，阶段 0/1）

## 总体分层

```
┌──────────────────────────────────────────────┐
│ frontend (React+TS+Vite)  实验工作台/可视化     │  只依赖 REST 契约（进度轮询）
├──────────────────────────────────────────────┤
│ api (FastAPI)  REST, 后台任务编排               │
├──────────────────────────────────────────────┤
│ services  实验管理 / 运行器 / 批量任务(阶段4)    │
├──────────────────────────────────────────────┤
│ core/engine  统一模拟接口（时间步进/离散事件）    │  不依赖 API、DB、前端
│ core/schema  版本化模型描述格式 + 校验 + 迁移     │
│ db  SQLite + 版本化迁移                         │
├──────────────────────────────────────────────┤
│ models/*  插件式模型包（排队/CPU调度/缓存/CA…）   │  只依赖 core 抽象
└──────────────────────────────────────────────┘
```

依赖方向单向向下：`models → core`，`services → core + db`，`api → services`。
`core` 与 `models` 不 import `fastapi`/`sqlite3`；可视化适配器（前端）与模拟逻辑通过
「模型状态快照 + 事件记录」两种统一格式解耦。

## 目录结构

```
backend/
  pyproject.toml uv.lock
  scripts/benchmark.py   性能基准（数字见 docs/BENCHMARKS.md）
  migrations/            NNNN_*.sql 顺序迁移文件
  app/
    main.py config.py
    db/ (connection.py migrations.py)
    core/
      engine/ (base.py event_queue.py engines.py models_base.py rng.py)
      engine/engines.py  SimulationEngine + 时间步进/离散事件两种实现
      schema/ (spec.py migrations.py)   模型描述格式 v1 + 版本迁移
      registry.py plugins.py stats.py
    models/                每个子目录 = 一个模型插件（__init__.py 加一行 import 即接入）
      queueing/ cpu_scheduling/ cache_sim/ cellular_automaton/
      schelling/ traffic_network/ sir/
    api/routes.py          全部 REST 路由（会话/批量进度由前端轮询）
    services/ (experiment_service.py session_service.py batch_service.py
               analysis_service.py reporting.py benchmarks.py)
  tests/
frontend/
  src/ (App.tsx SimView.tsx BatchPanel.tsx ComparePanel.tsx ParamForm.tsx
        TrafficPanel.tsx api.ts chartRender.ts trafficRender.ts
        findings.ts sweepChart.ts summary.ts schema.ts types.ts logic.test.ts)
docker-compose.yml
```

## 统一模拟接口（core/engine/base.py）

所有模型实现两种引擎语义之一，不得混合：

- **时间步进 (time_stepped)**：`step()` 以固定 Δt 推进，时间严格单调 +Δt。
  适合元胞自动机、差分方程。
- **离散事件 (discrete_event)**：模型向引擎事件队列投递 `(time, priority)` 事件，
  引擎按 `(time, priority, seq)` 弹出；`seq` 为投递顺序，保证同刻事件确定性。
  零延迟事件（delay=0）在同刻按投递顺序继续处理，引擎设单刻事件链上限防死循环。

统一能力由 `SimulationEngine` 提供：`run(n)` / `step()` / `reset()` /
`checkpoint()` / `restore()` / 取消回调 / 指标收集 / 资源上限
（max_steps、max_events、max_sim_time、max_wall_seconds）。

**检查点 = JSON 可序列化字典**：`{step, clock, model_state, event_queue, rng_state}`。
模型约定状态必须 JSON 安全（快照本来就要经 API 传输）。RNG 用 `random.Random`，
其 state 元组为纯 int，可 JSON 往返；恢复后与不中断运行逐比特一致（有测试保证）。

**快照与事件记录**：
- `StateSnapshot{step, time, status, state, metrics}` —— 状态视图（可增量/采样传输）。
- `EventRecord{seq, time, kind, message, data}` —— 事件日志环形缓冲（默认保留最近 500 条）。

## 模型描述格式（ModelSpec）

版本化 JSON：`{schema_version: 1, model_id, model_version, display_name,
model_type, params, stop_condition, seed, notes}`。
`core/schema` 提供 pydantic v1 校验 + `MIGRATIONS` 升级链（v0→v1 等迁移函数），
`load_spec(raw)` 自动迁移到当前版本再校验。参数约束（区间/枚举/整数性）由模型插件
声明的 pydantic 参数模型校验，双层校验均通过才允许建实验。

停止条件（判别联合）：`steps`(事件/步数上限)、`sim_time`(模拟时间上限)、
`until_empty`(事件队列排空，仅 DES)。默认 max_steps 兜底防无界运行。

## 数据库（SQLite + 迁移）

- `schema_migrations(version, name, applied_at)` —— 迁移按文件序号在事务内应用，可重入。
- `model_registrations(model_id, version, spec_json, …)` —— 已注册模型版本快照。
- `experiments` —— 名称、model_id+model_version、完整 spec_json、seed、
  status(created/running/completed/failed/cancelled)、engine/software 版本、
  起止时间、duration_ms、error、tags、parent_experiment_id（复制来源）。
- `experiment_runs` —— repeat_index、seed、status、steps、sim_time、metrics_json、
  summary_json、events_json、error、duration_ms、result_sha256（指标规范 JSON 的
  SHA-256，作为结果校验信息）。
- `result_artifacts` —— run 的明细产物（timeseries 等），带 sha256。
- 不同 model_version 的实验**不默认可比**：比较 API 要求同 model_version，否则
  显式返回 `cross_version=true` 警告字段（阶段 4 实现比较时遵守）。

WAL 模式；每个请求/工作线程使用独立连接；写事务短小。

## 后台执行模型

`services/run_worker.py`：`ThreadPoolExecutor(max_workers=可配置, 默认 2)`。
模拟循环每处理 N 个事件检查一次取消标志（DB 状态）与墙钟/步数上限，
超限置 `cancelled/failed` 并落库。API 永不在事件循环内直接跑模拟。

## 可视化（阶段 2 完整实现）

工作台由真实 `/api/.../steps`、快照、事件日志驱动；播放控制 = 引擎单步/连续调用，
无任何预录动画。每个模型插件提供 `visualizer` 声明（kind: grid/queue/timeline…），
前端按 kind 分发渲染组件；渲染组件只消费快照数据。

## 插件式模型库

`registry.register(cls)` 注册模型类；模型包自包含（params、model、示例 spec、
tests）。`app/models/__init__.py` 显式 import 内置插件。新增模型不改 core/api/services。
