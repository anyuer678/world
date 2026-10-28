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
| D27 | 交通模型 = 时间步进元胞传输：有向图路网（节点带布局坐标）进 params（pydantic 深校验：节点唯一、边端点存在、禁自环/重复边、共点节点须显式长度、格数上限）；信号灯为节点上两个**显式**来向分组（group_a/group_b 恰好覆盖全部驶入源）交替放行，不做奇偶自动分组（字母序奇偶会把十字路口配成 E+S 同绿的几何冲突相位）；车辆 NS 跟驰（加速-刹车-随机慢化-移动），新发车车辆 v=0 落在入口格、被前车 gap=0 压住时当 tick 不动并占用入口格一 tick——入口自然形成隔 tick 放行的排队节奏；路线 = 发车时按长度 Dijkstra 最短路；slow_prob=0 时全模型确定性 | 路网/信号/发车全部为 spec 参数 → 现有批量网格、敏感性、种子策略零改动复用；显式信号分组把路口配时知识留给建模者；入口格占用语义给出真实排队物理 | 把路网放 spec 顶层字段（破坏 spec 通用契约）；奇偶自动分组（默认十字路口相位错误） |
| D28 | 场景库 = 模型类上的 `scenarios` ClassVar（id/title/description/params/seed/stop_condition），registry 校验形状（必填非空 + params 为 dict + id 唯一）并随 `/api/models` 暴露；内置模型全部中文 display_name/description + 中文 Field(title)；前端在「模型与参数」区渲染一键场景卡片：点击 → 用场景 spec 直接建会话 → 自动连续运行 → 滚动到模拟视图，表单同步为场景配置 | 「不好用」的根源是新概念负担与英文术语墙；场景把「定义模型→调参→运行」折叠成一次点击，且场景是 registry 契约的一部分——插件模型同样可以声明场景获得同等入口；所有场景经 test_scenarios 回归（形状/中文/spec 校验/实跑 200 步） | 前端硬编码场景（与后端契约脱节、插件模型无法享受）；新手引导浮层（维护成本高、挡操作） |
| D29 | 可视化历史 = 模型 `_s` 内的 log 抽稀序列（`hist_n % hist_stride` 落点、超 256 点减半并翻倍 stride，约 128-256 点覆盖任意时长），随检查点走；前端图表 = chartRender.ts 纯函数（drawLineChart/drawGantt/drawAccessStrip），SimView 按模型接入，绘制顺序即图层层序 | 历史放模型状态则检查点/恢复/确定性零特殊处理，抽稀保证内存与快照体积有界且长跑不失真；纯函数图表模块可单测坐标换算而不碰 DOM；旧检查点缺新键用 setdefault 兜底（持久化边界防御） | 前端自行累积历史（会话重载/换页即丢、与检查点脱节）；SVG 逐点折线（点数大时 DOM 卡顿） |
| D30 | 同步步智能体契约（谢林隔离模型 = 首个 agent 类模型）：一步 = 先在 t 时刻冻结快照上统一评估所有智能体的满意度，再按扫描序把每个不满者搬到一个「快照空格」（每空格本步至多用一次、不连锁）——被腾出的格子本步不可作为目标，满员且无空格时不满者原地不动；满意度 = 同组邻居/已占用邻居（8 邻域，无邻居视为满意），随机目标用模型自有 RNG（确定性、随种子） | 同步步（先评估后移动）保证所有智能体基于同一世界状态决策，无顺序伪影；不连锁使结果可复现、检查点等价可测试（引擎 checkpoint/restore 往返验证）；这是继元胞（局部规则）与事件（调度）之外的第三种建模范式，零改动复用引擎/批量/场景/图表机制 | 异步逐个更新（结果依赖扫描顺序，引入系统性偏差）；允许本步腾出格即占（链式搬迁，世界状态不一致） |
| D31 | 批量自动发现 = 对已聚合 summary 的两层描述性启发式：①1-D 扫描跳变——仅取「单参数变化、其余数值参数取众数、≥3 个取值」的切片，相邻点因子 = max(\|a\|,\|b\|)/min(\|a\|,\|b\|) ≥ 3 记跳变；触及精确零（坍缩为 0 / 从无到有）无有限因子，记 ratio=null 并按最强信号排序；0→0 不算变化；②重复离散异常——n≥3 时 CV=std/\|mean\| ≥ 0.5。每（参数×指标）只留最大跳变，两类各截 5 条；页面固定声明「只报告显著变化，不构成因果解释」 | 批量已有聚合统计，补一层「帮用户看」的自动发现即可让网格结果可读（实测 servers 1→2 时队列长从 9311 坍缩为 0 = 真实相变）；描述性而非因果避免过度解读；精确零报 null 而非用 1e-12 地板算倍数（浏览器实测会渲染出 9.3e15 倍的无意义数字） | 差值/相对变化率阈值（量纲不可比）；ratio 钉死为 number（零目标溢出）；对 0→0 报坍缩（假阳性，实测复现后修掉） |
| D32 | 扫描曲线 = 前端从已返回的 batch summary 就地重建「发现」所用的同一切片规则（sweepChart.ts 纯函数：数值网格参数、其余数值参数取众数、切片内 ≥3 个不同取值才可选；单指标均值序列排序后复用 drawLineChart）；默认选中跟随第一条同参数跳变发现（findings 未返回前不取默认，避免时序落到字母序首指标）；发现列表跳变项可点击 → 切到该参数×指标 | 文字「9311 坍缩为 0」不如一条肉眼可见的断崖曲线有说服力；切片规则镜像后端（D31）保证图表画的正是发现所依据的数据；纯函数重建零后端改动、零额外请求（summary 本就随详情返回）；默认等 findings 是浏览器实测时序 bug 的修正 | 后端加聚合端点（summary 已够用）；用 CI 区间带（drawLineChart 不支持带状，留作后续）；默认不等 findings（实测会默认到 arrived 而非真正的临界指标） |

## 环境审查（阶段 0，实测）

- Windows 11 x64，git-bash；Python 3.12.3（`python` 命中官方安装）；uv 已装。
- Node v24.15.0 / npm 11.12.1；Docker 29.6.2（Docker Desktop）。
- 无网络受限迹象（后续 `uv sync`/`npm i` 实测确认）。
- 结论：无技术障碍，按既定技术选型执行。
