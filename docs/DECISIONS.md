# 决策记录（ADR 简表）

| # | 决策 | 理由 | 备选 |
|---|------|------|------|
| D1 | SQLite 直用 `sqlite3` + 自写顺序迁移 runner（`.sql` 文件 + `schema_migrations` 表） | 依赖最小、迁移过程完全可测可控；SQLAlchemy/alembic 对单文件库收益低 | alembic |
| D2 | 随机源用 stdlib `random.Random`，每模型实例独占一个实例；RNG state 进检查点 | 纯 Python state 可 JSON 序列化，检查点/恢复确定性强；NumPy 仅在需要向量计算时引入 | numpy Generator |
| D3 | 事件队列 `heapq`，排序键 `(time, priority, seq)`；`seq` 单调递增 = 同刻 FIFO | 满足同刻顺序与零延迟事件语义；可复现 | SortedList |
| D4 | 零延迟链上限（默认 10_000 事件/时刻）触发即报错 | 防止模型 bug 造成死循环占用资源 | 静默合并 |
| D5 | 检查点与快照强制 JSON 可序列化 | 快照须经 API/WebSocket 传输；同时保证检查点可入库 | pickle |
| D6 | 后台运行用进程内 `ThreadPoolExecutor`（默认 2 workers） | 模拟为纯 Python CPU 混合 IO，线程足够；避免子进程序列化复杂度。阶段 6 压测后如需再引入进程池 | multiprocessing |
| D7 | 取消 = 协作式：模拟循环每 N 事件轮询取消标志 | 简单可靠；不杀线程 | 强杀线程（不可移植） |
| D8 | 结果校验 = 对 metrics 规范化 JSON（sorted keys, ensure_ascii=False）计算 SHA-256 | 轻量完整性校验，满足"结果文件校验信息" | 整文件哈希 |
| D9 | 模型插件不执行任何用户任意代码；模型逻辑全部为平台内置 Python 包 | 满足"不允许任意模型代码在主进程执行"；DSL 为后续阶段 | 沙箱子进程 |
| D10 | 实验默认重复 1 次；批量/重复与种子策略（固定/每重复递增）阶段 4 落地 | 阶段 1 先保证单次运行闭环正确 | — |
| D11 | 时间为 `float` 秒（模拟单位由模型自解释）；步进引擎步长恒定 | DES 与步进时间语义分离，各自引擎保证单调性 | int tick |
| D12 | API 返回指标时同时附 `result_sha256` 与 `deterministic: seed非空` 提示 | 复现性可被前端展示与验证 | — |
| D13 | 排队模型容量 `capacity=None` 表示无限；`capacity>=1`（含在服务者） | 与 M/M/c/K 文献对齐；capacity=0 无意义故禁止 | — |
| D14 | 前端骨架阶段 1 即建（Vite+React+TS），完整工作台阶段 2 | 阶段验收要求工程骨架完整可运行 | — |
| D15 | 会话进程内存储 + 单工作线程按 256 步分片推进；spec 创建时固定 | 会话是交互对象非持久资产；分片让暂停/轮询/取消有固定响应粒度 | 每步轮询、WebSocket 推送 |
| D16 | running 期间 `state()` 返回 ≤100ms 节流的缓存快照（分片间隙在锁内生成） | 避免高频轮询与工作线程争锁造成撕裂读/饥饿；100ms 交互延迟可接受 | 锁内实时读模型 |
| D17 | 引擎 `run(max_steps)` 必须在同一调用内强制步数上限，达上限返回 `chunk_done`（不写入内部 status） | 回归修复：原实现 hard_cap 只算不用，连续运行一步到底，轮询恒见 step 0、暂停仅在结束后生效；快照 status 保持 running 供会话层判别 | — |
| D18 | 前端 300ms 轮询 running 会话 + `visibilitychange` 回前台立即拉取一次 | 后台标签页定时器被浏览器强节流（最长约 1 分钟/次），轮询间隔本身无法对抗节流，回页签即时补偿 | WebSocket 推送（阶段 6 视压测决定） |
| D19 | `Limits.max_steps` 只约束「无界」`run()`（批量实验/直连调用）与手动 step 批量；分片连续运行（`run(max_steps=N)`）不受绝对上限截断，改由 `max_wall_seconds`（worker 循环顶）+ spec 停止条件约束 | 回归修复：原语义下会话分片运行累计步数一到 `default_max_steps` 即终止（轮询测试 500k 步恒在 100k 处 step_limit 收场）；而「worker 无视 step_limit」又会死转——chunked run 达上限后每次瞬间返回 0 步。改为 `_stop_reason(enforce_step_limit=)` 开关 + worker 顶墙钟；无界调用仍受保护 | 会话层记录并跳过 step_limit（治标不治本） |
| D20 | 批量实验：专用 `ThreadPoolExecutor(max_workers=settings.max_workers)` 跑 batch item，单批次并发再经 `min(concurrency, max_workers)` 封顶；item 采用无界 `run()`（受 D19 绝对步数上限 + 每项 `per_run_wall_seconds` 与全局墙钟取 min 约束）；只重试**异常**（completed/step_limit/wall_timeout 是合法结果）；DB 只存 metrics+sha256 不存事件日志；统计纯 Python 实现（无 numpy），CI 为正态近似并显式标注；敏感性 = 数值网格参数与「每组合指标均值」的皮尔逊相关，响应内固定携带「相关性≠因果、单次批量不足以断言普遍最优」说明 | 并发总量有界（实验池 + 批量池各自 ≤ max_workers）；事件日志体量大且对统计无用（大型数据不逐帧全量传输）；避免为统计引入重依赖；防止把观察性关联当因果结论展示 | 共享单一全局池（需重构 ExperimentService 构造）；逐步回归分位数置信区间（需 bootstrap） |
| D21 | 插件加载 = 环境变量 `WORLDLAB_PLUGIN_MODULES`（逗号/分号分隔模块名）+ 模块级 `register(registry)` 钩子；registry 注册契约强制 `description` 非空、`visualizer` 为含字符串 `kind` 的 dict、`model_type` 必须与继承的基类严格一致（DES↔discrete_event / 步进↔time_stepped）。插件是运维者安装的受信代码（与依赖包同级信任），非受信模型代码不在支持范围——行为由 spec 定义而非代码 | 新增模型零核心模块改动（只装包+配置环境变量）；强契约防「声明 DES 实则步进」之类的错位插件 | 请求头/URL 动态装插件（引入运行期信任问题）；放宽 model_type 校验（保留原始宽松检查） |
| D22 | 单次运行执行时用 run 行落库的 seed，而非 spec.seed 原值 | 回归修复：spec.seed 缺省时 run 行生成随机种子，但执行仍取 spec.seed=None → 结果不可从落库数据复现，违背「种子溯源」承诺 | 执行后回写 spec（掩盖溯源缺口） |
| D23 | 聚合均值与批量汇总只计 `status=='completed'` 且 metrics 非空的运行 | 截断/失败运行可能带部分 metrics，混入均值会把「跑了一半的数字」当统计样本 | 全量计入（统计口径失真） |
| D24 | 批量编排按批维护在途上限：`max_inflight = min(concurrency, max_workers)`，完成一个补交一个（`wait(FIRST_COMPLETED)` 循环），不再一次性提交全部 item | 回归修复：原实现整批 submit 全进队列，单批取消时已排队 item 全部落入 CancelledError 依赖 executor 内部行为，且在途数与并发声明脱钩 | 一次性 submit 全部（取消语义靠 executor 兜底） |
| D25 | 批量创建先对网格笛卡尔积计数（combos×repeats），超 `MAX_BATCH_ITEMS` 直接拒绝，不做任何展开物化 | 回归修复：原实现先物化 item 列表再校验总量，10^12 级网格会在校验前把进程内存吃光 | 先物化后校验（OOM 风险） |
| D26 | 检查点携带 `model_version` 与 `params_digest`（params 规范化 JSON 的 SHA-256）；`restore()` 校验两者，跨版本/跨参数恢复拒绝 | 模型版本或参数不同则状态布局不可信，恢复只会产出静默错位的世界 | 只校验 model_id（放过版本漂移） |

## 环境审查（阶段 0，实测）

- Windows 11 x64，git-bash；Python 3.12.3（`python` 命中官方安装）；uv 已装。
- Node v24.15.0 / npm 11.12.1；Docker 29.6.2（Docker Desktop）。
- 无网络受限迹象（后续 `uv sync`/`npm i` 实测确认）。
- 结论：无技术障碍，按既定技术选型执行。
