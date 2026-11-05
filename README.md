# WorldLab — 通用复杂系统模拟与实验平台

定义模型 → 运行真实模拟 → 观察状态 → 管理实验 → 比较结果。

**阶段 0–6 完成，产品化改进推进中**：版本化模型 Schema（迁移 + 校验）、统一模拟引擎（时间步进 + 离散事件、检查点/恢复/取消、资源上限）、八个内置模型、可视化模拟工作台、实验管理、批量实验与统计（含 95% 置信区间与自动发现）、插件式模型库、报告导出（md/JSON/CSV）、性能基准、异常恢复与端到端测试、Docker 部署验证，界面全中文。

逐轮改进记录（R1–R31，含每轮发现并修掉的真问题）见 `docs/CHANGELOG.md`；设计取舍见 `docs/DECISIONS.md`，验证口径见 `docs/TESTING.md`。

## 内置模型

| 模型 | 类型 | 要点 |
| --- | --- | --- |
| `queueing` 排队系统 | discrete_event | 到达/服务过程（Poisson/指数等）、服务器数、容量、FIFO/SJF/SPT 调度；等待时间、吞吐、利用率、丢弃率 |
| `cpu_scheduling` CPU 调度 | discrete_event | FCFS / SJF / 优先级 / Round Robin（时间片可配）；等待/周转/响应时间、CPU 利用率 |
| `cache_sim` 缓存 | time_stepped | LRU / FIFO / LFU / random 替换、显式或 Zipf 访问序列；命中率、缺失率、访问成本 |
| `cellular_automaton` 元胞自动机 | time_stepped | 二维网格、生命游戏类规则配置、状态历史与演化可视化 |
| `schelling` 谢林隔离模型 | time_stepped | 同步步智能体（冻结快照统一评估、搬入快照空格不连锁）；容忍阈值、两组占比、显式初始布局；隔离指数、不满率、搬家数——轻微偏好涌现强隔离的经典结论 |
| `sir` SIR 传染病 | time_stepped | 确定性仓室 Euler（50 子步/时间单位，S+I+R 守恒）；传播率 β、康复率 γ、人口与初始感染；累计感染率、峰值感染与时刻——β/γ>1 的疫情阈值相变，扫 β 即见断崖 |
| `predator_prey` 捕食者-猎物 | time_stepped | Lotka-Volterra 确定性 RK4（8 子步/时间单位，经典版守恒首次积分 δx−γ·ln x+βy−α·ln y）；增长/捕食/转化/死亡率与初始两群；可选猎物容纳量 K 使轨道收敛到内平衡（x*=γ/(δβ) 与 K 无关）；兴衰周期数、周期长度、平衡点距离——相平面闭合轨道可视化 |
| `traffic_network` 交通路网 | time_stepped | 有向图路网（节点/边/信号灯进 spec，工作台提供预设+JSON 编辑+预览）、元胞跟驰（NS 规则）、显式相位信号灯、最短路发车；吞吐/行程时间/等待/均速，路段占用着色实时渲染 |

每个模型有参数校验、确定性测试、边界测试与示例 spec（`GET /api/models/{id}` 返回
`example_spec`），并内置 2–3 个中文「一键场景」——在工作台点卡片即自动建会话、
连续运行并展示结果（`GET /api/models` 返回 `scenarios`；插件模型同样可声明场景）。
全部模型名称、参数标签与场景描述均为中文。

## 本地开发

### 后端（Python 3.11+，uv）

```bash
cd backend
uv sync                 # 安装依赖（fastapi/pydantic/numpy/uvicorn + pytest/httpx）
uv run pytest           # 全部测试：引擎/事件队列/八模型/Schema/迁移/会话/批量/插件/报告/性能/恢复/端到端
uv run python scripts/benchmark.py   # 性能基准（数字写入 docs/BENCHMARKS.md 的口径）
uv run uvicorn app.main:app --port 8000
# API: http://localhost:8000/api/health  文档: http://localhost:8000/docs
```

可选环境变量（读源于 `app/config.py:Settings.from_env()`，括号内为默认值）：
`WORLDLAB_DB`（SQLite 路径，默认 `backend/data/worldlab.db`）、
`WORLDLAB_MAX_WORKERS`（并发运行上限，2）、
`WORLDLAB_MAX_WALL_SECONDS`（单次运行墙钟秒上限，120）、
`WORLDLAB_DEFAULT_MAX_STEPS`（步数上限，1000000）、
`WORLDLAB_CANCEL_POLL_INTERVAL`（协作式取消检查粒度，256 步）、
`WORLDLAB_ZERO_DELAY_CHAIN_LIMIT`（同刻零延迟事件链上限，10000）、
`WORLDLAB_EVENT_LOG_SIZE`（会话事件环形缓冲，500）、
`WORLDLAB_PLUGIN_MODULES`（插件模块名，逗号/分号分隔，默认为空，见 `docs/PLUGINS.md`）。
运行时上限的可查询口径由 `GET /api/limits` 统一导出（R29）。

### 前端（Node 18+）

```bash
cd frontend
npm install
npm run dev             # http://localhost:5173 （/api 代理到 8000）
npm run test            # 前端单元测试（vitest，60 项纯逻辑用例）
npm run build           # 类型检查 + 生产构建（tsc -b && vite build）
```

界面：模型选择 → 参数配置面板（结构化编辑器，基于 params_schema 生成）→
运行/暂停/单步/重置/检查点 → 实时模拟视图（按模型适配：队列、甘特、网格、指标曲线）→
事件日志 → 实验历史与比较 → 批量实验面板。视图全部由真实模拟状态驱动，
模拟逻辑与渲染逻辑分离（每个模型一个 visualizer 声明 + 前端适配器）。

## Docker 部署（已验证）

```bash
docker compose up --build -d
# 前端 http://localhost:5173  API http://localhost:8000/api/health
```

compose 栈：`api`（FastAPI + uvicorn，healthcheck 探活，数据落在命名卷
`worldlab-data`）+ `web`（nginx 托管构建产物并反代 `/api`）。依赖用锁文件钉版
（后端 `uv sync --frozen` + uv.lock，前端 `npm ci` + package-lock.json），
构建上下文经 .dockerignore 裁剪。R30 复验的生产形态链路（全部经 nginx 反代 5173 实测）：
health、八模型目录、`GET /api/limits`、实验创建→运行→指标+`result_sha256`、
`/api/runs/{id}/events` 分页（含未知 run 的 404）、报告 markdown/JSON、批量创建→终态→
自动发现→`export.csv`（12 列 + BOM）、请求体规则越界 422。历史轮次：R7 首验六模型目录 +
场景一键运行（跨环境确定性一致：谢林轻微偏好 382 次搬家/0 不满）与批量发现，
R15 复验停止条件两型，CSV/报告导出为阶段 6 已验链路。

## 测试与质量保障

- **后端 pytest**（24 个测试文件）：引擎时间语义（同刻事件顺序、零延迟链上限）、
  八模型正确性（排队论对照、调度指标手算对照、缓存命中数、CA 规则、谢林同步步
  不变式、SIR 仓室守恒与 R₀ 阈值、捕食者-猎物首次积分守恒与内平衡收敛、交通路网信号相位与守恒）、确定性
  （同种子逐位一致，含检查点恢复后续跑）、Schema 迁移、批量（网格/种子策略/取消/重试/并发上限）、
  统计汇总、自动发现（扫描跳变/离散异常/CI 重叠三态）、插件注册、报告、性能回归阈值、异常恢复
  （进程重启后续跑、崩溃不丢数据）、端到端全生命周期（HTTP 层走真实 API 契约，八个模型逐个跑通）。
- **前端**：vitest 单元测试（spec 编辑、状态映射、速读文案、扫描曲线与 CI 带、批量面板与
  `/api/limits` 校验、两种 422 形状的文案还原）。
- **性能基准**：`docs/BENCHMARKS.md` —— 引擎吞吐、API 延迟、批量吞吐与回归阈值，
  全部来自 `scripts/benchmark.py` 实测。

## 关键语义

- **时间语义分离**：`time_stepped` 固定 Δt 步进；`discrete_event` 事件队列按
  `(time, priority, seq)` 排序，同刻事件 FIFO，零延迟链有上限防死循环。
- **可复现**：同模型 + 同参数 + 同种子 ⇒ 指标逐位一致（含检查点恢复后续跑，有测试保证）；
  结果附 `result_sha256` 校验和。
- **实验可比性**：每次运行记录模型版本、完整参数、种子、软件版本、时长、指标、异常、
  校验和；不同模型版本的实验不默认可比（报告中的 `comparability_note` 显式说明）。
- **资源有界**：max_steps / max_sim_time / 墙钟 / 零延迟链 / 并发 worker 全部可配置且默认开启；
  批量条目受 `default_max_steps` 与 `per_run_wall_seconds` 双重上限。
- **后台任务**：批量与实验运行可查询状态、协作式取消、失败重试；API 事件循环不被模拟计算阻塞。

## 已知限制

见 `docs/BENCHMARKS.md` 的「已知限制」章节（测试稳定性说明、性能口径、单机数据规模等）。

详细设计：`docs/ARCHITECTURE.md`（架构）、`docs/API_CONTRACT.md`（API 契约）、
`docs/DECISIONS.md`（决策记录）、`docs/PLUGINS.md`（插件接口）、`docs/TESTING.md`（测试策略）、
`docs/CHANGELOG.md`（R 轮次改进日志）。
