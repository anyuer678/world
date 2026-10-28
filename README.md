# WorldLab — 通用复杂系统模拟与实验平台

定义模型 → 运行真实模拟 → 观察状态 → 管理实验 → 比较结果。

**阶段 0–6 完成，产品化改进推进中（R 轮次）**：版本化模型 Schema（迁移 + 校验）、
统一模拟引擎（时间步进 + 离散事件、检查点/恢复/取消、资源上限）、七个内置模型、
可视化模拟工作台、实验管理、批量实验与统计、插件式模型库、报告导出、性能基准、
异常恢复测试、端到端测试与 Docker 部署验证。R1 完成可信执行基础（种子溯源、
聚合口径、批量在途上限、网格限量前移、检查点绑定）；R2 完成交通路网世界
（路网进 spec、信号灯、批量/敏感性零改动复用）；R3 完成三分钟上手
（一键场景库 + 全中文界面 + 模拟视图置顶 + 结果速读中文摘要）；R4 完成可视化重构
（排队/缓存/CPU 模型 log 抽稀历史进检查点，五视图 canvas 曲线图 + CPU 甘特图 +
缓存命中条，像素探针逐视图取证）；R5 完成同步步智能体——谢林隔离模型
（冻结快照评估 + 快照空格搬迁的确定性 agent 契约，双色网格 + 不满红点 +
隔离指数曲线实时可视化）；R6 完成批量自动发现——1-D 扫描跳变（因子 ≥3、
触及精确零记「完全消失/从无到有」）与重复离散异常（CV ≥0.5）两层启发式，
`GET /api/batches/{id}/findings` + 工作台自动发现区，固定声明只描述不因果；
R7 复验 Docker 生产形态并钉版依赖（uv.lock/npm ci + .dockerignore）；
R8 完成批量扫描曲线——从 summary 就地重建发现切片画「指标均值 vs 参数」
断崖曲线，默认跟随首条跳变发现、发现可点击联动切换；R9 完成第七个内置
模型 SIR 传染病（确定性仓室 Euler，R₀=β/γ 疫情阈值的教科书相变正好由
批量发现 + 扫描曲线呈现）；R10 巡检收口两处滞后——性能基准覆盖补全至
全部 7 个内置模型（实测 schelling 单步最贵 ≈186 steps/s，见
`docs/BENCHMARKS.md`），首页「一键运行」快速入口补全至 7 模型；R11
无障碍审计清零——axe-core 全页扫描修前 4 类违规（次要文字对比度
2.4–2.7:1、滚动区无键盘访问、无 main 地标），修后空态/会话态均 0 违规，
架构文档目录树同步对账，index.html 补 meta description；R12 续对账——
删除架构文档三处失实的 WebSocket 声明（实际为 REST + 轮询），批量 CSV
导出与取消批量首次浏览器实测通过（9 项 schelling 批次 5 秒取消，
cancelled: 9）；R13 修复运行中重置的锁序死锁（reset 持锁 join 运行线程
致状态卡「已取消」，join 移到锁外，附修前实证失败的回归测试），暂停/
恢复分片语义、错误参数 422 横幅均浏览器实测通过；R14 零缺陷验证轮——
报告导出、载入配置、比较面板（≤4 上限+跨模型警示）、终态禁用、单步
×N、存为新实验、批量非法参数报错、检查点保存→恢复快照逐字节相等九条
链路全部实测收编（检查点保持 API-only，见 DECISIONS D38）；R15 停止
条件对账——「按模拟时间」「直到事件队列为空」两型首次 UI 实测通过，
Docker 生产形态 R7 后首次复验通过（7 模型清单、容器内 SIR 全流程、
nginx 代理与快速入口一键运行，见 D39）；R16 三种种子策略与批量超时
语义实测收编（wall_timeout 计合法终态不重试），并修复无网格批量发现
文案的空占位（见 D40）；R17 修复参数表单数组字段缺陷（显式访问序列等
数组参数在 UI 上从未可用——字符串直传必 422，新增 ArrayField 解析与
红字提示，浏览器实测与 API 真值逐位一致），实验模块 API-only 端点
（rerun/cancel/clone/tags/delete）实跑核验保留（见 D41）；R18 ArrayField
JSON 分支（CA 指定初始图案）与 TrafficPanel 自定义路网全链路实测收编
（闪光灯终局逐格断言、7 节点请求体捕获），并修复可空参数字段中文描述
从未渲染的 resolve 缺陷（见 D42）；R19 结构化输入收尾验证轮（零代码改
动）——CPU 显式作业对象数组 FCFS/SJF 同输入双策略对照（调度顺序与等待/
周转指标逐位命中手算真值）、谢林全同网格不变量、CA 按模拟时间停止条件
补齐矩阵（见 D43）；R20 空停止值边界定性（后端 422 拒绝+横幅透明显示，
无静默兜底）与 SIR 交互会话重构后复验（50 天轨迹逐位命中欧拉手算真值、
仓室守恒、速读文案自洽，见 D44）。

## 内置模型

| 模型 | 类型 | 要点 |
| --- | --- | --- |
| `queueing` 排队系统 | discrete_event | 到达/服务过程（Poisson/指数等）、服务器数、容量、FIFO/SJF/SPT 调度；等待时间、吞吐、利用率、丢弃率 |
| `cpu_scheduling` CPU 调度 | discrete_event | FCFS / SJF / 优先级 / Round Robin（时间片可配）；等待/周转/响应时间、CPU 利用率 |
| `cache_sim` 缓存 | time_stepped | LRU / FIFO / LFU / random 替换、显式或 Zipf 访问序列；命中率、缺失率、访问成本 |
| `cellular_automaton` 元胞自动机 | time_stepped | 二维网格、生命游戏类规则配置、状态历史与演化可视化 |
| `schelling` 谢林隔离模型 | time_stepped | 同步步智能体（冻结快照统一评估、搬入快照空格不连锁）；容忍阈值、两组占比、显式初始布局；隔离指数、不满率、搬家数——轻微偏好涌现强隔离的经典结论 |
| `sir` SIR 传染病 | time_stepped | 确定性仓室 Euler（50 子步/时间单位，S+I+R 守恒）；传播率 β、康复率 γ、人口与初始感染；累计感染率、峰值感染与时刻——β/γ>1 的疫情阈值相变，扫 β 即见断崖 |
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
uv run pytest           # 全部测试：引擎/事件队列/四模型/Schema/迁移/会话/批量/插件/报告/性能/恢复/端到端
uv run python scripts/benchmark.py   # 性能基准（数字写入 docs/BENCHMARKS.md 的口径）
uv run uvicorn app.main:app --port 8000
# API: http://localhost:8000/api/health  文档: http://localhost:8000/docs
```

可选环境变量：`WORLDLAB_DB`（SQLite 路径，默认 `backend/data/worldlab.db`）、
`WORLDLAB_MAX_WORKERS`（并发运行上限，默认 2）、`WORLDLAB_MAX_WALL_SECONDS`（单次运行墙钟上限，默认 120）、
`WORLDLAB_DEFAULT_MAX_STEPS`、`WORLDLAB_CANCEL_POLL_INTERVAL`、`WORLDLAB_ZERO_DELAY_CHAIN_LIMIT`。

### 前端（Node 18+）

```bash
cd frontend
npm install
npm run dev             # http://localhost:5173 （/api 代理到 8000）
npm run test            # 前端单元测试
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
构建上下文经 .dockerignore 裁剪。R7 复验链路：health、六模型目录、
场景一键运行（跨环境确定性一致：谢林轻微偏好 382 次搬家/0 不满）、
批量创建 + 自动发现（含 ratio=null 的坍缩为 0 识别）；CSV/报告导出为
阶段 6 已验链路。

## 测试与质量保障

- **后端 pytest**（21 个测试文件）：引擎时间语义（同刻事件顺序、零延迟链上限）、
  六模型正确性（排队论对照、调度指标手算对照、缓存命中数、CA 规则、谢林同步步
  不变式、交通路网信号相位与守恒）、确定性
  （同种子逐位一致，含检查点恢复后续跑）、Schema 迁移、批量（网格/种子策略/取消/重试/并发上限）、
  统计汇总、自动发现（扫描跳变/离散异常）、插件注册、报告、性能回归阈值、异常恢复
  （进程重启后续跑、崩溃不丢数据）、端到端全生命周期（HTTP 层走真实 API 契约）。
- **前端**：vitest 单元测试（spec 编辑、状态映射、批量面板逻辑）。
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
`docs/DECISIONS.md`（决策记录）、`docs/PLUGINS.md`（插件接口）、`docs/TESTING.md`（测试策略）。
