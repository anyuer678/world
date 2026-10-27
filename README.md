# WorldLab — 通用复杂系统模拟与实验平台

定义模型 → 运行真实模拟 → 观察状态 → 管理实验 → 比较结果。当前进度：**阶段 0/1 完成**
（工程骨架、版本化模型 Schema、统一模拟引擎（时间步进 + 离散事件）、排队模型、实验管理 REST API、前端骨架、Docker 部署）。

## 本地开发

### 后端（Python 3.11+，uv）

```bash
cd backend
uv sync                 # 安装依赖（fastapi/pydantic/numpy/uvicorn + pytest/httpx）
uv run pytest           # 运行全部测试（引擎/排队理论对照/Schema/DB迁移/API 全链路）
uv run uvicorn app.main:app --port 8000
# API: http://localhost:8000/api/health  文档: http://localhost:8000/docs
```

可选环境变量：`WORLDLAB_DB`（SQLite 路径，默认 `backend/data/worldlab.db`）、
`WORLDLAB_MAX_WORKERS`（并发运行上限，默认 2）、`WORLDLAB_MAX_WALL_SECONDS`（单次运行墙钟上限，默认 120）、
`WORLDLAB_DEFAULT_MAX_STEPS`、`WORLDLAB_ZERO_DELAY_CHAIN_LIMIT`。

### 前端（Node 18+）

```bash
cd frontend
npm install
npm run dev             # http://localhost:5173 （/api 代理到 8000）
```

界面流程：选模型 → 编辑 spec JSON（参数/停止条件/种子）→ 运行 → 查看真实指标与事件日志。

## Docker 部署

```bash
docker compose up --build
# 前端 http://localhost:5173  API http://localhost:8000
```

## 目录

```
docs/          架构 / API 契约 / 决策记录 / 测试策略
backend/
  app/core/engine/   统一模拟接口（时间步进 + 离散事件 + 检查点/恢复/取消/资源上限）
  app/core/schema/   版本化 ModelSpec + 迁移链 + 双层校验
  app/core/registry  插件注册表（新增模型不改核心）
  app/models/        内置模型（queueing；阶段 3 增加 CPU调度/缓存/元胞自动机）
  app/services/      实验管理 + 后台运行（线程池、协作式取消、结果 SHA-256）
  app/db/            SQLite + 顺序迁移
  migrations/        SQL 迁移文件
  tests/             pytest
frontend/      React+TS+Vite 工作台骨架
```

## 关键语义

- **时间语义分离**：`time_stepped` 固定 Δt 步进；`discrete_event` 事件队列按
  `(time, priority, seq)` 排序，同刻事件 FIFO，零延迟链有上限防死循环。
- **可复现**：同模型 + 同参数 + 同种子 ⇒ 指标逐位一致（含检查点恢复后续跑，有测试保证）。
- **结果可信**：所有指标来自真实运行，附 `result_sha256` 校验和；无任何预置/伪造数据。
- **资源有界**：max_steps / max_sim_time / 墙钟 / 零延迟链 / 并发 worker 全部可配置且默认开启。

详细设计见 `docs/ARCHITECTURE.md`，已知限制与基准见 `docs/benchmarks.md`（阶段 6）。
