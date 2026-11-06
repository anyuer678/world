# WorldLab 改进日志（R 轮次）

每一轮 = 找真问题 → 修 → 全量回归 → 浏览器/实跑取证 → 文档三件套（本文件 + DECISIONS D 行 +
TESTING 条目）→ 提交推送。本文件由 README 原样搬迁而来（R31），自 R31 起每轮新增一段，
不再往 README 正文里堆。

**阶段 0–6 完成，产品化改进推进中（R 轮次）**：版本化模型 Schema（迁移 + 校验）、
统一模拟引擎（时间步进 + 离散事件、检查点/恢复/取消、资源上限）、八个内置模型、
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
仓室守恒、速读文案自洽，见 D44）；R21 排队模型现代化复验收口七模型复验
矩阵（嵌套对象参数编辑传播、ρ=2 超载吞吐钳制、M/M/1 利用率/Little 定律/
精确解三断言、种子决定论逐位一致，见 D45）；R22 新增第八个内置模型
捕食者-猎物（Lotka-Volterra RK4，经典版守恒首次积分、容纳量版收敛到
与 K 无关的内平衡点；相平面轨道图+时间序列双视图、3 个中文一键场景、
基准/回归/Docker 全链路收编，见 D46）；R23 统计可信度集成——扫描曲线加
95% CI 阴影带（重复不足或零方差时明示无带），跳变发现加 CI 重叠三态判定
（显著/可能噪声/无法判定），同一批内双语义并排实证（见 D47）；R24 对账债清偿
——补 ARCHITECTURE/API_CONTRACT 滞后条目，修复插件场景契约真缺陷（前端曾把
seed/停止条件当必填、PLUGINS.md 未写该契约），临时插件端到端实证兜底语义（见 D48）；R25 把
API_CONTRACT 逐条实测对齐——落地契约承诺却缺失的 `runs/{id}/events` 分页端点，修正 snapshot
`time`、422 `errors[]`、runs 主键 `id` 等 4 处形状漂移（见 D49）；R26 基准可复现性
刷新（三张表改为单次运行 + 日期环境声明，修掉 R22 混入的跨机位行）与行为声称核对，
把「≤100ms 节流」按实测改写为「256 步分片边界缓存快照」（见 D50）；R27 检查点落实
审计——ARCHITECTURE 的 checkpoint 形状自 R1 未更新已按实重写，并为 `restore()` 的
四项指纹校验（错配一律 409，不返 500）补上此前缺失的拒绝测试（见 D51）；R28 审导出
链路并把报告 JSON 键集成入契约，同时补上端到端的老洞——`test_e2e` 自 R10 起只断言
4 个模型，现八个内置模型逐个跑通「建实验→运行→指标+SHA→报告 md/json」全链路（见 D52）；R29 消灭
上限双写——新增 `GET /api/limits`（值现场取自服务端校验规则），批量面板据此禁用与提示
（此前填 repeats=150 会被前端放行、后端 422），并纠正 BENCHMARKS 里 `default_max_steps`
的数量级失真（100,000 → 实际默认 1,000,000）（见 D53）；R30 入门文档实跑轮——照 README 逐条
真跑命令并修四处计数/清单漂移（四→八模型、测试文件数、模型正确性清单、Docker 段落口径，
环境变量补齐 `WORLDLAB_EVENT_LOG_SIZE`/`WORLDLAB_PLUGIN_MODULES`），修掉一处可用性真缺陷：
422 的 `detail` 有对象（应用层 spec 校验）与数组（FastAPI 请求体规则）两种形状，前端只读
对象形状导致数组形状横幅退化成裸「422」——新增 `errorDetailMessage()` 统一还原并让批量面板
消费 `/api/limits` 早已导出的重试边界，浏览器实测填 15 得到具体红字提示且按钮禁用；同时完成
R15 后首次 Docker 生产形态复验（八模型目录、nginx 反代、limits/events 分页/404、报告键集、
批量+CSV 导出、解析真值逐位命中）（见 D54）。


**R31（2026-11-05）写死清单根治 + 文档-现实一致性锁 + 基准报告口径修正**

① 内置模型清单的唯一事实源落到注册表：新增 `registry.builtin_ids()`（按注册类是否来自
`app.models.*` 判定，插件模型不在列），`test_e2e.BUILTIN_MODELS`、`test_scenarios.BUILTIN_IDS`
与 `scripts/benchmark.py` 的基准循环全部改为派生；基准脚本遇到「注册了但没配步数」直接
`SystemExit` 报错，端到端用 `test_e2e_step_budget_covers_every_builtin_model` 绑死步数预算。
② 新增 `tests/test_docs_consistency.py`（7 项）把文档声称钉到代码上：README「内置模型」表 ==
注册表、README「八个内置模型」措辞 == 实际数量、README 测试文件数 == 磁盘文件数、
BENCHMARKS 覆盖每个内置模型、OpenAPI 的 32 个端点逐个必须在 API_CONTRACT 出现、
契约不得承诺路由里不存在的端点。六路失败模式全部实测会红（端点从契约消失、契约虚构端点、
计数错、措辞错、表内容错、基准缺行）；本轮它就抓到一件事——新增测试文件后 README 的
「23 个测试文件」立刻变红，改成 24。
③ 真缺陷修复：`BenchResult.per_second` 在耗时 <1ms 时报 **0.0 steps/s**。cpu_scheduling 的
示例作业集在约 400 个事件后排空队列提前停止，0.0 读起来像「慢到跑不动」，实际是快到测不出。
现改为 `steps_per_second: null` + `measurable: false`，文本表打印「n/a（<1 ms，测不出）」，
BENCHMARKS 补口径说明，`test_bench_result_never_reports_zero_throughput` 与早停如实呈现测试
各绑一路。
④ R11 的无障碍声称复扫（R22/R29/R30 新增界面从未验过）：axe-core 4.10.2 在空态、
捕食者-猎物运行态（含 R22 相平面图）与批量面板展开（含 R29/R30 数字输入）三种状态下均
**0 违规**；两张 canvas 都带 `role="img"` + 中文 aria-label（相平面那条含坐标轴含义与
平衡点说明）。
⑤ README 的 73 行 R 轮次长段逐字搬到本文件（README 7,835 → 4,645 字符，只留摘要 + 链接），
搬迁用脚本并自检内容完整；此后每轮在 CHANGELOG 追加一段，不再往 README 正文里堆——
那段长文同时是编辑锚点误删的高发区。
⑥ 新增 `.github/workflows/ci.yml`：把 README 教的两条命令（`uv run pytest`、
`npm ci && npm run test && npm run build`）变成推送后自动门禁。
首跑已核验（run 42019027707）：后端 job **270 passed / 22.5 s**（ubuntu-latest、`uv sync --frozen` 装的 CPython 3.12.16），前端 job 60 项 + `tsc -b`/vite build 通过——这是本项目**第一次**在 Linux 上跑通整套测试。

回归：后端 **270/270**、前端 **60/60**、tsc -b/vite build 干净。


**R32（2026-11-05）版本化能力的真实缺口：多模型版本从「宣称」到「可用」**

探针（临时插件给 `sir` 挂 2.0.0 与 10.0.0 两个版本，真起 uvicorn 打真接口）暴露三处缺陷，
且都是「单版本时看不见」的：① 版本号按**字符串**比较，`versions_of` 给出
`['1.0.0','10.0.0','2.0.0']`；② `registry.get()` 的「最新版本」用字符串 max，于是选中
`2.0.0` 而数值最新是 `10.0.0`——运行会静默用错版本；③ `GET /api/models` 每个版本出一条
（实测 3 张 `sir` 卡片），而 `GET /api/models/{id}` 返回**第一条＝最旧版本**（1.0.0），
用户照它写的 spec 与实际跑的模型不是一回事。
修法：新增 `registry.version_key()`（按点/横线/加号分割的数字组分比较，非数字段视作 0），
`get/versions_of/list` 统一走它；目录改为「每个 model_id 一条（最新）+ `versions` 列表」，
`/api/models/{model_id}` 默认最新版并支持 `?version=` 指定，未知 model_id 与未知版本都是
404 `not_found`，后者 message 带 `available: [...]`。前端 `ModelInfo` 加 `versions` 字段后，
`tsc` 立刻抓到测试夹具缺这个键（正是类型跟着契约走的收益）。
验证：新增 `tests/test_model_versions.py` 5 项（数字序、最新解析、目录去重+versions、
`?version=` 与 404、未知 id 404；探针模型注册后在夹具里摘掉，不给全局注册表留垃圾）；
改后重跑同一探针：目录 8 条 / `sir` 详情 10.0.0 / 运行的 `model_version` 10.0.0 三者一致、
`?version=1.0.0` 命中旧版、`?version=9.9.9` 给出 available 清单；浏览器复跑确认模型下拉
仍是 8 个且无重复项、SIR 场景一键运行到 completed。API_CONTRACT 模型节按实重写。
后端 **275/275**、前端 **60/60**、tsc -b/vite build 干净。


**R32 收口审计（成文于 docs/TESTING.md §43）**：六个维度（声称 vs 实现、测试与门禁、
生产形态、无障碍与入口质量、内容型拓展、其余候选的拒绝理由）逐条给证据或取舍；
本轮另补查三个此前未单独验证的资源类声称（`sim_time` 停止、零延迟链上限、
批量在途上限——后者由「建批时写入 effective 值 + 线程池上限」双重构造保证，并有实测绑定）。
Docker 用 R32 代码重建复跑全链路，predator_prey 的 `result_sha256` 与 R30 逐位一致。


**R33（2026-11-05）钉版本的实际效力 + `normalized_spec` 契约兑现**

R32 修好了「多版本目录」，本轮把同一能力的下半段验完并补上缺口。探针（临时注册两版**行为可辨**
的探针模型：γ 默认 0.1/上限 1.0 对 0.4/上限 5.0）给出结论：`spec.model_version` **确实**决定
校验与执行——γ=3.0 在 1.0.0 被拒而在 2.0.0 通过；同参数不同版本跑出峰值 303.9 对 10.0；
批量与实验记录 `model_version=1.0.0`；未知版本是 422 `spec_invalid/unknown_model` 而不是 500。
能力是真的，但**此前一条测试都没有**。
真缺陷一处：契约承诺 `POST /api/models/{id}/validate` 的 `normalized_spec` 是「迁移补齐后的形态」，
实测 `model_version`/`display_name` 恒为 None、`params` 原样回吐不含默认值——`validate_spec_only`
只是把入参 dump 回去，而 `validate_spec` 已经算好的 `model_cls`/参数对象被丢弃。改为给出解析后的
版本、注册表显示名与套默认值后的完整 params（前端不消费该端点，属 API-only，无 UI 涟漪；
存储侧的 spec 原文与 params_digest 语义刻意不动，以免影响检查点指纹）。
新增 4 项回归（normalized_spec 形态、未知版本的两条错误路径、钉版本改变校验边界、钉版本改变
实际执行且未钉时解析到数值最新），API_CONTRACT 与 README「实验可比性」按实补写。
后端 **279/279**、前端 **60/60**、tsc -b/vite build 干净。


**R34（2026-11-05）批量数据的透明度 + 网格能力边界成文**

① 沿 R32/R33 的「只在单实例/正路径验过」审计法，本轮探两类边界：
`schema_version` 全形态（省略/=1/=0/未来版本 2/99/字符串/负一）——结论是**已经做对且已有测试**
（v0 迁移、`schema_too_new`、`migration_missing`、类型错分别给出可读 422；顺带纠正我自己
一次因 `grep | head` 截断而误判的「缺测」，复核后确认 `test_schema.py` 覆盖到位）；
`grid` 键边界（平铺合法/拼错/点号嵌套路径/空列表/未知顶层）——行为正确（一律 422 并列出
具体键名）但**既没成文也没有测试**，尤其「不支持点号嵌套」这条对嵌套参数模型（排队的到达/
服务过程）是真实能力边界。② 修一处会误导结论的 UX 缺陷：批量面板一次只取 50 项，表头却只写
「前 50 项」而不写总数——60 项或 1200 项的批次会被读成「这就是全部」。新增纯函数
`itemsHeading(shown,total)`，实读浏览器文案为「单项结果（显示前 50 / 共 60 项，其余见「导出 CSV」）」，
并实测该批次 CSV 恰有 60 行数据（导出走 500/页循环）→ 指路是真的能拿到全量。
③ 网格表单加一条能力边界提示（只扫顶层参数名，嵌套字段先在参数面板设好）。
④ **我自己引入、又被浏览器渲染当场抓住的缺陷**：提示文案里按 markdown 习惯写了 `**顶层参数名**`，
JSX 不解析 markdown → 页面原样显示星号，改为 `<strong>` 后复验。教训写进守则：文案对不对只能看 DOM。
⑤ 新增测试 4 项：后端（嵌套/空列表 422 的 code 与文案、`items` 按 offset 续读不重不漏且 total 稳定）、
前端（`itemsHeading` 满页/截断两分支）。API_CONTRACT 的 `POST /api/batches` 与 `items` 两处按实补写。
后端 **281/281**、前端 **62/62**、tsc -b/vite build 干净。


**R35（2026-11-05）「只在新实例/单例/正路径验过」审计线：孤儿模型实验的两处真缺陷**

① 会话并发与状态机（探针）：同一会话 6 个并发 `/step` 精确推进 1..6、无重复无异常；
`run → pause → step` 后停在 257 步且 1.2 秒后仍不动；`reset` 回 `idle`/step 0；
**运行中** `DELETE /api/sessions/{id}` → 204、列表移除、再 GET 404。状态机竞态是干净的，本轮不改。
② 实验列表过滤 × 分页（探针）：`total` 确实是被过滤后的条数、`model_id`+`tag` 是 AND、
未知 tag/模型返回空、`offset` 续读不重叠——行为全对，但**没有一条测试断言这些语义**，补 1 项。
③ 真缺陷一（提交时校验不一致）：库里存在「注册表已无此模型」的实验时（插件模块没配好、
版本被撤下——D21 的常态后果），`run`/`rerun` 原本先答 200 `queued`，再由工作线程把 run 标成
`failed`；而 `create`/`clone`/建批同样是这个 spec 却当场 422。改为**提交时校验**（且发生在状态改写
之前，实验不会被留在 `running`）。线上复验（真起 uvicorn、载入插件建实验、重启不载插件）：
详情/结果/报告 200，`run`/`rerun`/`clone` 422 `unknown_model`，实验状态仍是 `created`。
④ 真缺陷二（诊断即泄漏又噪声）：`run.error` 存的是 `类型: 消息\nTraceback …`，
**带本机绝对路径**，而它会进导出报告；批量单项与交互会话的错误本来就只存一行。
抽出 `describe_run_failure()`：预期内失败族（`SpecValidationError`/`RegistryError`/`SimulationError`）
只留一行原因，其它意外仍保留 3 层栈便于定位。
⑤ 契约纠偏：`POST /api/experiments/{id}/run` 实测是 **200 `{experiment_id, run_id, status}`**，
契约此前写成 202 + `{runs:[run_id]}`（`rerun` 同）；补 `error` 字段口径与「提交时校验」两条；
README 关键语义加「插件卸载不吞历史」。
⑥ 卫生：R33 探针在本地 dev 库留下 18 条孤儿实验，已删除（探针产物自己收口）。
后端 **285/285**、前端 **62/62**（本轮未改前端）、tsc -b/vite build 干净。


**R36（2026-11-05）ARCHITECTURE/PLUGINS 深审：把「设计意图」与「已实现」分开**

R25 对 API_CONTRACT 做过逐条实测，但 ARCHITECTURE.md 自 R27 局部修补后再没整体审过。
本轮逐句对磁盘、代码与前端分发器核账，抓到 **9 处** 失真（多数是阶段 0/4 的设计意图被
当成现状留在文档里）：幻影文件 `core/schema/migrations.py`（迁移实际在 `db/migrations.py`，
schema 侧是 `evolution.py`/`errors.py`）与 `services/run_worker.py`（根本没有该模块，
三个服务各持自己的 `ThreadPoolExecutor`）；幻影字段 `Limits.max_events`（真实只有
`max_steps`/`max_wall_seconds`/`zero_delay_chain_limit`/`cancel_poll_interval`，模拟时间上限
属于 `stop_condition`）；ModelSpec 谎称含 `model_type` 字段（引擎类型由注册表决定）；
「pydantic v1 校验」（实际 v2）与不存在的 `MIGRATIONS`/`load_spec` 名称（实际
`register_migration`/`upgrade_spec`，v0→v1 还把 `horizon` 迁成 `stop_condition`）；
「取消标志（DB 状态）」（实际是进程内 `threading.Event`，每 `cancel_poll_interval` 步协作检查）；
`/api/.../steps`（实际 `/step`）；**「比较 API 返回 `cross_version=true` 警告字段」——代码里
全仓无此名**，不可比提示实际由前端 `ComparePanel` 判定显示、报告用 `comparability_note` 声明；
以及 `result_artifacts` 表**建了但没有任何写入方**，旧文档把它写成可用能力。

重写后的文档不再靠人记得去对账：`test_docs_consistency.py` 新增 7 项锁——文件清单与磁盘
**双向**比对（幻影路径与漏写文件都会红，`__init__.py` 除外）、`Limits` 字段名与 dataclass 一致、
文档表集合 = 迁移声明集合且**死表必须标注「没有写入方」**、PLUGINS.md 的 kind 清单 =
`SimView` 实际分发集合（并须写明未知 kind 落到 `StateTable`、`series` 前端不消费）、
架构文档出现的 `/api/...` 字面量必须存在于 OpenAPI（带方法名与裸写法都查，且带
「匹配数过少即失败」防空锁）、`cross_version` 不得再被当作已有能力宣称。
**八路注入验证**这些锁真的会红（改一个 kind、删一行清单、加一个幻影文件、把死表说成可用、
把端点写成复数、裸路径改名等）。另修 `visualizer.series` 的口径：内置模型带着它，但前端从不读，
文档改为明示「只是元数据」而不是暗示能自动出图。
后端 **292/292**、前端 **62/62**、tsc -b/vite build 干净。


**R37（2026-11-05）配置一致性：环境变量对交互会话静默无效 + 三路径 Limits 锁**

① 顺着「配置声称 vs 行为」这条线探到一处真缺陷：`SessionService.create()` 构造
`Limits` 时只传了 `max_steps`/`max_wall_seconds`，另两项落进 dataclass 默认值——于是
`WORLDLAB_CANCEL_POLL_INTERVAL` 与 `WORLDLAB_ZERO_DELAY_CHAIN_LIMIT` **对交互会话完全无效**，
而 `GET /api/limits`（R29 的单一事实源端点）报给前端的却是 Settings 里的值：
advertising 与执行分叉。实测（`WORLDLAB_CANCEL_POLL_INTERVAL=7 WORLDLAB_ZERO_DELAY_CHAIN_LIMIT=99`）
Settings 收到 7/99，会话引擎实际仍是 256/10000。修：新增 `SessionService.session_limits()`，
四项全部取自 Settings，并有行为测试绑定；生产容器内复核
（`-e WORLDLAB_CANCEL_POLL_INTERVAL=9 -e WORLDLAB_ZERO_DELAY_CHAIN_LIMIT=77` → limits 9/77）。
② 锁三条（`test_docs_consistency.py`）：README 环境变量清单 ↔ `config.py` 实际读取集合**双向**
一致（R30 曾漏写两个变量）；清单里写明的默认值逐个等于代码默认值（R29 的数量级病灶）；
实验/会话/批量三条路径里每个 `Limits(` 构造都必须给全四字段——**对修复前的
`session_service.py` 跑这条锁会准确报出缺的那两个字段**（已验证）。
③ 文档纠正：`BENCHMARKS.md` 原写「交互式会话不受 `default_max_steps` 约束」是假的——
会话引擎的 `max_steps` 就是它，分片只是每次 `run` 至多推进 `CHUNK_STEPS=256` 步；
README「资源有界」条目按实重写（并去掉前端用例数的硬编码，改为看运行汇总），
ARCHITECTURE 后台执行段补上三路径一致性说明。
④ Docker 生产形态复验（R36 代码 + 本轮修复后重建 api 镜像）：原 15 项链路全绿，
另跑会话生命周期——restore 回到的 `(step=300, time=165.1952)` 与检查点前**逐位一致**，
继续步进到 310，错配 model_id 的 restore 得 409 `conflict`（message 指明 `'sir' != 'queueing'`），
delete 204 → 再 GET 404。
后端 **296/296**、前端 **62/62**、tsc -b/vite build 干净。


**R38（2026-11-05）基准可追溯性：解释器机位归属 + 表内算术自洽锁**

① 抓到归属错误：`BENCHMARKS.md` 的测量环境写 Python 3.12.3，而 README 记录、实际使用的
运行方式是 `uv run python scripts/benchmark.py` → 走 `backend/.venv` 的 **3.11.13**。
两种解释器都"合法"（旧文档还写着"或 uv run"），于是 R26 辛苦确立的「同一机位」原则
实际上无法判定——引用者不知道数字是谁跑出来的。本轮重跑一次基准，环境块改为
**逐项抄录脚本自己打印的 environment**（解释器 3.11.13 / 平台 / CPU 型号 / app 与引擎版本），
并明写「系统 python 3.12.3 属另一机位，不可混引」。
② 三张表全部换成这一次运行（R38）：queueing ≈246,000、cache ≈337,000、CA ≈4,000、
schelling ≈202（最贵）、traffic ≈6,410、sir ≈40,000、predator_prey ≈64,100 steps/s；
API 单步 p50 0 / p95 16 / max 31 ms；批量 8 项 0.203 s ≈39.41 items/s。
跨轮对照也按实更新：R26 与 R38 同机相差 0–80%（predator_prey 摆动最大），
并明确「只有量级与相对排序可用」。回归阈值表的括注原先拿 5 万步测试冒充 10 万步数字，
改为引用本表同行。
③ 新锁（`test_benchmarks_are_internally_consistent_and_attributed`）：每一行的
「步数 ÷ 耗时」必须与该行吞吐在 3% 内算得通（够覆盖 3 位有效数字舍入），
批量行同理；API 的 p50 ≤ p95 ≤ max 必须成立；环境块必须给出解释器版本与
`uv run python scripts/benchmark.py` 的命令归属。五路注入全部变红，包括
「把上一轮的 8% 差值数字混进来」「只改耗时不改吞吐」这类真实的混机位症状。
后端 **297/297**、前端 **62/62**、tsc -b/vite build 干净。

**R39（2026-11-05）会话控制语义：暂停不再等于取消 + 引擎所有权交接 + 会话 TTL 可配置**

本轮按「能力声称只在顺利路径上被执行过」这条老线索巡检，用一次 HTTP 探针抓到了自阶段 2
以来一直存在的 P0：⏸ 暂停把会话写成 `cancelled` 终态。实跑（toy_slow_step 运行 0.25 s 后
暂停）显示 `status='cancelled'`、`resume` 与 `step` 全部 409「session already finished」，
唯一出路是「重置」——也就是丢掉整段进度。根因在停止入口而不在状态机：
`_stop_thread()` 无条件同时置 `cancel_event` 与 `pause_event`，而运行循环先检查 cancel。
修法是把「暂停」和「丢弃」拆成两个意图：`pause/reset/restore` 只置 pause 标志（worker 在
分片边界落 `paused`，可继续、可单步），`delete`/空闲回收/进程关停才置 cancel。
值得注意的是旧 `test_session_pause_and_resume` 一直绿：它的等待集合含 `completed`，
运行总在暂停前就自然结束，于是从未真正走过暂停——把代码注入回旧行为后它也变红，
这条元信息比修复本身更值得记下（绿色测试集 ≠ 功能可用）。

② 引擎所有权交接：join 超时后旧实现照样改状态并放行 step/reset/checkpoint，
而分片期间是故意不持锁的（否则前端轮询会被卡住），两个线程因此并发改同一台引擎。
新增 `stopping` 标志与 `_finish_run()`（状态落定与清标志在同一次加锁里完成），
五个入口在交接完成前一律返回可重试的 409；两条新测试用 gate 卡住 worker，
不靠 sleep 赌时序，并断言 `engine.steps` 在被拒期间保持 0。
③ 会话空闲回收时限从硬编码 3600 秒改为 `WORLDLAB_SESSION_TTL_SECONDS`，
README / API_CONTRACT / ARCHITECTURE 三处成文（此前用户离开一小时后只拿到无解释的 404）。
④ 新文档锁：全部「见 D5x」指针必须命中 DECISIONS 真实行号。
⑤ 间歇性 Windows faulthandler access violation 按环境噪音如实记录（三次连跑 2/2/0 次、
测试始终全绿、Linux CI 日志 0 次、栈帧散落在无关 stdlib），不宣称归因。
后端 **302/302**、前端 **62/62**、tsc -b/vite build 干净。

**R40（2026-11-05）会话控制端点不再等待分片：pause/reset/delete 改为边界交接**

R39 把「暂停后不许并发改引擎」立住了，但用的是 join：`pause` 最多阻塞 5 秒。本轮实测
256×256 元胞自动机（参数上限）的 256 步分片要 **4.28 s**——暂停请求会挂住近 5 秒再返回
「仍在运行」，按钮看着像坏了；`reset` 在 join 超时后回 409 让用户重试，等于逼人大网格上连点；
`DELETE` 与 TTL 回收也在请求里同步等别人的分片，把一个用户的操作算到另一个用户头上。
改为边界交接：`pause` 只置标志立即返回；运行中的 `reset` 排进 `pending_action`，由 worker 在
分片边界执行（交接与清 `stopping` 在同一次加锁里，避免孤儿动作）；`DELETE`/TTL 回收摘除即返回。
`restore` 保持 API-only 的同步 409（检查点校验失败必须回给调用方）。契约按实更新：
`pause`/`reset` 的响应是交接前状态，`paused`/`idle` 在 ≤1 个分片内经轮询到达。
后端 **302/302**、前端 **62/62**、tsc -b/vite build 干净。

**R42（2026-11-05）生产形态复验：R39/R40 的会话控制语义在容器里同样成立**

R30 做过 Docker 复验，但那时还没有 R39（暂停≠取消）与 R40（控制端点边界交接）的改动；
本轮把 compose 重新构建（api 镜像含最新代码）后经 nginx 反代实测：
256×256 元胞自动机会话 `POST /pause` **HTTP 200 / 31.9 ms**（`time_total`）且响应体仍是
`running`，随后轮询到 `paused`（step 256）；`POST /reset` **200 / 37.7 ms**，随后落
`idle`（step 0），再单步 3 步得 `paused`（step 3）；`DELETE` 204。
容器内 `WORLDLAB_SESSION_TTL_SECONDS=12.5` 覆盖生效（`Settings.from_env()` 读出 12.5）。
另验两条**重启语义**：运行中的实验在 `docker compose restart api` 后变
`failed | interrupted: service restarted while run was in progress`，
会话列表如约清空（内存态）。本轮未发现缺陷，未改代码；证据记入 `TESTING §53`。

**R43（2026-11-05）批量并发取消的聚合口径核验 + 钳制值的透明度成文**

用 8 并发、16 项（toy_slow_step，每项 20 万步）在运行中途取消：终态 `cancelled`、
`counts={cancelled:16}` 与 `total_items` 自洽、无 pending/running 残留、`items.total=16`、
`export.csv` 数据行 16（前三行是导出头注释）、`findings` 200——**聚合口径没有缺陷**。
但同一探针暴露一处透明度缺口：请求 `concurrency=8` 时服务端 `max_workers=2`，批量
记录的是**生效值 2**；`per_run_wall_seconds` 同样被 `min(值, max_wall_seconds)` 钳制。
行为是对的（报告值与实际在途一致），但契约只在取消端点旁提过一句，创建端点没有说明。
补：`API_CONTRACT` 的建批条目写明两个钳制公式与「回显生效值」，并新增
`test_batch_records_effective_limits_not_requested` 绑定该语义（请求 64/3600 →
记录 2/60）。本轮无产品代码改动。

**R44（2026-11-05）工作台可访问性实测：补上异步状态的朗读**

对工作台做了一轮「人怎么用」的审计：525 个文本节点的对比度全部达标（0 处低于 AA），
81 个可聚焦控件全部有可访问名，无正向 tabindex、无 `outline:none`，真实 Tab 按键下
`:focus-visible` 生效且 UA 焦点环可见。**发现一处真缺陷**：会话状态由 300 ms 轮询异步变化
（运行中→已暂停→已完成），但页面没有任何 live region，读屏用户按下「暂停」后得不到任何反馈；
错误横幅也只有 TrafficPanel 有 `role="alert"`。修：会话状态改为 `<span role="status">`、
顶部提示与批量提示加 `role="status"`、三处错误横幅（顶部/会话/批量）加 `role="alert"`〔R52 更正：实际只加了两处，批量面板顶部漏加，已于 R52 补上并实测〕、
批量状态加 `role="status"`。浏览器实测：运行时朗读文本「状态 运行中」→ 暂停后「状态 已暂停」，
422 错误进入 `role=alert` 区域。前端 62/62、tsc/vite 干净。

**R45（2026-11-05）界面状态值统一中文化**

会话状态早已本地化，但实验历史、批量列表、批量详情、批单项、比较面板仍在直接渲染后端
英文枚举（`completed` / `cancelled` / `queued`…），中文界面里混着英文状态。修法：把
`statusLabel()` 从 App.tsx 抽到 `frontend/src/labels.ts`（五个界面共用），补齐
`created/queued/pending/failed` 四个此前会原样漏出的枚举，未知值仍原样返回（不静默吞掉
新状态）；App 的历史表与 BatchPanel/ComparePanel 全部改为调用它。浏览器实测：实验历史、
批量列表、批量详情头部均显示「已完成」，`td` 中不再出现任何英文状态；`labels.ts` 已加入
ARCHITECTURE 清单（文档锁双向校验通过）。前端 62/62（新增 4 条枚举断言）、tsc/vite 干净。

**R46（2026-11-05）错误提示可读性：字段名与常见校验消息中文化 + 孤儿配置载入即告知**

实测两条真实用户路径：① 把「步数」填成 2000000 再点单步，横幅显示
`错误：422: n Input should be less than or equal to 1000000`——英文、裸状态码、字段名是内部缩写；
② 载入一条模型已被移除的历史实验（R35 允许读），界面只说「已载入配置」，直到点运行时
才吃到一个英文 422。修：`errorDetailMessage` 识别常见 pydantic 消息与已知字段名
（`n`→步数、`repeats`→每组重复…），全部可识别才译成中文（「步数 不能大于 1000000」），
**有一条识别不了就整条回退原文**（不混排、不丢信息）；对象形状里已知 code 的顶层文案中文化
（`spec_invalid`→参数校验失败、`unknown_model`→模型或版本不存在）。载入历史配置时，
若模型已不在目录中，提示改为「配置可查看，运行会被拒绝」。浏览器实测两条路径均按预期显示。

**R47（2026-11-05）会话单步上限进入 /api/limits，越界在界面里不可达**

R46 把「步数 2000000」的 422 变成了可读中文，但那仍是**事后报错**：`/api/limits` 没有暴露
会话单次步进上限，前端只能把值发出去等拒绝。本轮把 `n` 的上限抽成
`session_service.MAX_STEP_BATCH`（校验与端点共用一处），`/api/limits` 新增
`session:{max_step_batch}`；工作台的步数输入据此设置 `min/max`，越界时显示
「步数不能超过 1000000」、`aria-invalid` 置位并禁用「单步」，因此该 422 从界面上不可达。
浏览器实测：输入 2000000 → 提示 + 按钮禁用；改回 5 → 提示消失、单步成功（step 5）。
后端 **303/303**、前端 **65/65**、tsc/vite 干净。

**R48（2026-11-05）实验历史的截断透明度**

`refreshHistory()` 只取 `/api/experiments?limit=20`，界面却把 20 行当成全部——开发库当时已有
**46 条**实验，也就是说这个缺陷在真实数据上早已生效：用户会误以为更早的实验不存在。
批量面板在 R34 已按「显示前 N / 共 M」处理，实验历史漏掉了同一口径。修：`historyHeading()`
在标题里写明「显示最近 20 条 / 共 46 条，更早的未在界面列出」，比较面板同步显示
「可选范围：最近 20 条（共 46 条）」。浏览器实测两处文案均正确渲染；探针实验已删（75/74），
总数回到 46。前端 **66/66**、tsc/vite 干净。

**R49（2026-11-05）比较面板的上限不再静默吞点击**

比较面板最多同时选 4 个实验，但第 5 次勾选被 `s.length < MAX_COMPARE ? … : s` 直接丢弃，
界面没有任何反馈——按钮文案里的「≤4 个」是唯一线索。修：抽出纯函数 `toggleCompare()`
（单测覆盖满额、取消、已选项取消），界面常显「最多同时比较 4 个（已选 x / 4）」，到顶时
变为「已达上限，取消一个后可再选」并**禁用未勾选项**；取消任一项后立即恢复可选。
浏览器实测：4 项后第 5、6 项为 disabled、点击无效、计数保持 4/4；取消一项后回到 3/4 且全部可选。
前端 **67/67**、tsc/vite 干净。

**R50（2026-11-05）会话被回收后的恢复路径：轮询不再吞 404**

R39 给会话加了空闲回收（默认 3600 s），但前端没有处理「会话已不在」：轮询的
`.catch(() => {})` 把 404 **整个吞掉**——运行中的会话一旦被回收，界面会永远停在
「运行中」且不再更新；点任何按钮则弹出英文 `session '…' not found`，死会话一直挂在页面上。
修：`api.ts` 抛带 `status/code/path` 的 `ApiError`；`isSessionGone()` 只在「404 且路径含
`/sessions/`」时判定（删实验的 404 不能清掉当前会话）；命中后清空会话并提示
「会话已被服务端回收（空闲超时）或删除；请重新开始模拟。」，轮询与手动操作两条路径都覆盖。
浏览器实测：空闲会话被删后点单步、运行中会话被删后等轮询，均清空并提示，不再卡在运行中。

**R51（2026-11-05）把前端其余空 catch 逐个判定：两处仍会吞掉状态变化**

R50 修掉会话轮询吞 404 之后，把前端所有 catch 过了一遍。判定结果：`getLimits` 失败回落默认值、
批量轮询的瞬时错误继续重试，属于**可容忍抖动**（保留并写注释）；但还有两处会掩盖状态变化——
① 标签页重新可见时的一次性刷新 `getSession(...).catch(() => {})`：此时轮询往往已停止，
会话被回收后回页面只会看到过期画面；② 批量列表 `listBatches().catch(() => {})`：服务端不可达时
界面只显示「暂无批量」，把失败伪装成「没有数据」。修：抽出通用 `isNotFoundOn(e, pathPart)`
（会话/批量各自按路径段判断，删实验的 404 不会误清会话），可见性刷新走与轮询相同的恢复逻辑；
批量列表失败显示原因，批量轮询遇 404 则提示「批量已不存在」并关闭详情（其余错误继续重试）。
浏览器实测：暂停中的会话被删除后触发可见性刷新 → 清空 + 中文提示（当前内嵌浏览器
`visibilityState=hidden`，按环境限制改为覆盖属性后触发同一处理函数，已在 TESTING 注明）；
批量 404 的界面分支未在浏览器里走通（查看按钮未打开详情），仅由 `isNotFoundOn` 单测覆盖。

**R52（2026-11-05）补验 R51 的批量分支 + 修正 R44 的「三处错误横幅」声明**

R51 探测时点「查看」无反应，本轮定性为**探针问题**：高级面板是 `<details>`（没有
`aria-expanded`），我点的是折叠状态下隐藏的按钮——打开后同一按钮正常打开详情（批量 #19）。
借这次补验，把 R51 未验证的批量分支走通：运行中的批量 #21 在库中被删除后，轮询 404 使详情
关闭（`setBatch(null)` 生效）。补验时又发现一处**文档与现实不符**：R44 声称「三处错误横幅
（顶部/会话/批量）都加了 `role=alert`」，实际批量面板顶部那处漏了——批量 #22 被删后点「查看」，
错误只以普通段落出现，读屏用户听不到。已补 `role=alert` 并实测：
`[role=alert]` 文本为「错误：batch 22 not found」，详情不再显示。

**R53（2026-11-05）重建生产镜像，逐项确认 R44–R52 的改动进入交付形态**

镜像最后一次构建停在 R42，而 R44–R52 全部是前端改动（外加上 R47 的 `/api/limits` 字段）。
本轮 `docker compose up -d --build` 重建后经 nginx 逐项核验：
`/api/limits` 返回 `session.max_step_batch=1000000`；构建产物文件名与本地一致
（`index-D_pFbmaR.js`），包内含「步数不能超过」「会话已被服务端回收」「最多同时比较」
「显示最近」「参数校验失败」五个新文案；浏览器在容器页面上验证——步数输入 `max=1000000`、
越界提示与禁用生效、实验历史标题「共 3 条」（容器库规模）、会话状态与提示均在
`role=status` 朗读区、非法参数提交后错误进入 `role=alert`（文案
「参数校验失败：params.width Input should be greater than or equal to 5」）。
该尾句暴露一处**中英混排**：对象形状的 spec 错误只翻译了顶层，嵌套的 pydantic 消息仍是英文，
留待下一轮处理。

**R54（2026-11-05）对象形状 422 的嵌套消息也翻译，两种形状规则统一**

R46 只把**数组形状**（FastAPI 请求体规则）的字段消息译成中文；**对象形状**（应用层 spec 校验）
只翻译了顶层 code，嵌套的 pydantic 消息仍是英文——同一个参数越界，两种入口两种语言。
本轮把 `humanizeSpecError()` 接到对象形状：`params.width` 去掉 `params.` 前缀、套用同一张
消息翻译表，规则与数组形状一致（**全部可识别才翻译，否则整条回退原文**）。浏览器实测：
CA 宽度填 3 → `错误：参数校验失败：width 不能小于 5`（原为
`参数校验失败：params.width Input should be greater than or equal to 5`）。前端 **69/69**。

**R55（2026-11-06）PLUGINS.md 的示例插件从伪代码变成可运行代码，并由测试绑定**

插件章节是课程交付物里「如何扩展」的主入口，但它的示例是
`# ... 实现各方法` 的伪代码——同一文档还要求插件必须附「可运行示例」。学生照抄只会得到
一堆抽象方法未实现的报错，而且看不出该实现哪五个方法。本轮把示例改成完整实现
（`step`/`snapshot`/`dump_state`/`load_state`/`finalize_metrics`），并新增
`test_documented_plugin_example_is_runnable`：**直接从 PLUGINS.md 抽取代码块**、写成临时插件、
经 `load_plugin_modules` 注册后跑 5 步，断言同 seed 两次运行逐位一致、`total=50`、指标键为
`{heads, ratio}`。反证注入：把示例换回伪代码，该测试立即变红（断言文案写明原因）。
后端 **304/304**。

**R56（2026-11-06）按文档原样起服务：插件启动路径与失败路径均已实测**

R55 只验到加载器层面；本轮把 `PLUGINS.md` 的示例代码块原样抽成 `_r56_plugins/lottery.py`，
用文档写的 `WORLDLAB_PLUGIN_MODULES=... uvicorn app.main:app` 启动真实服务：
`GET /api/models` 返回 **9 个模型**（8 内置 + lottery v1.0.0，中文显示名完好）；
用 `lottery` spec 建会话、单步 5 次 → `completed`，快照 `{heads:22,total:50,ratio:0.44}`，
指标 `{heads:22.0,ratio:0.44}`。失败路径同样成立：`WORLDLAB_PLUGIN_MODULES=no_such_plugin.module`
时应用启动即失败（退出码 1），错误信息为
`plugin module 'no_such_plugin.module' could not be imported: No module named 'no_such_plugin'`
——与文档「加载失败会让应用启动失败，并指明插件与原因」一致。探针目录与临时库已删除。

**R57（2026-11-06）批量列表的截断口径（与历史/单项统一）**

`listBatches()` 固定 `limit=10`，而开发库有 **19 个批量**——界面只显示 10 行且没有任何说明，
这处截断**当前就在发生**，与 R48 修的历史截断、R34 修的单项截断是同一类缺陷。修：新增
`batchesHeading(shown, total)`，列表上方显示「批量实验（显示最近 10 条 / 共 19 条，更早的未在
界面列出）」；总数取自列表响应里本就返回的 `total`。浏览器实测 19 条数据下标题与 10 行一致。
前端 **70/70**、tsc/vite 干净。

**R58（2026-11-06）最终完成审计（目标：分析拓展并完善，直到没有能拓展和开发的新任务）**

逐项对照证据后结论如下，并补记两条此轮新识别的「有意不做」候选。本次审计另补上一处文档缺口：
`PLUGINS.md` 只写了本地启动，未说明容器里插件模块必须可导入（构建进镜像或挂载 + `PYTHONPATH`）。

| 维度 | 结论 | 证据 |
| --- | --- | --- |
| 分析 | 57 轮持续巡检，每轮有实跑证据的发现或明确的设计取舍 | `docs/CHANGELOG.md` R1–R57；`DECISIONS` D1–D78；`TESTING` §1–§68 |
| 拓展 | 8 个内置模型、插件机制（含可运行示例 + 真实启动路径）、批量网格/种子策略/统计分析、报告与三种导出、场景库、基准脚本、Docker 与 CI | `PLUGINS.md`（R55/R56）、`BENCHMARKS.md`、`test_plugins.py`、`test_e2e.py` |
| 完善 | 会话控制语义（R39/R40/R50）、错误可读性（R46/R54）、上限前移（R47）、截断口径（R34/R48/R57）、可访问性（R44/R52）、状态中文化（R45） | 对应 D 行与 TESTING §；浏览器/容器实跑记录 |
| 门禁 | 后端 304、前端 70、`tsc -b`/vite 干净；HEAD 与远端一致；CI 全绿 | 本地实跑 + `gh run list` |
| 生产形态 | 镜像重建后逐项核验（R53），会话控制、上限、live region、错误横幅在容器内均生效 | `TESTING §64` |
| 新识别、有意不做 | ① 界面层删除实验/批量：破坏性操作无需求驱动，API 已提供；② 插件热加载：重启是受支持的路径，热加载会引入模块状态与信任边界问题 | 本条 |

**审计结论**：能力、正确性、可复现、文档、门禁、生产形态六个维度上，**没有「已知可做且不靠猜」的剩余项**；
剩下的均为内容扩充或范围外偏好（第 9 个模型、WebSocket、鉴权、分页 UI 等），需要用户点名才动。

**R59（2026-11-06）分页参数补边界：`limit=-1` 曾等于「无上限」，`events_limit=0` 曾返回全部事件**

实跑取证：`/api/experiments?limit=-1` 返回**全部 52 条**（SQLite 的 `LIMIT -1` 即无上限）、
`limit=999999` 同样全量、`offset=-5` 被当成 0；会话的 `events_limit=0` 返回 **49 条**事件
（`[-0:]` 等于 `[0:]`），`events_limit=-1` 返回「除第一条外的全部」。修：所有列表端点的
`limit` 用 `Query(ge=1, le=1000)`、`offset` 用 `Query(ge=0)`，`events_limit` 用 `Query(ge=0, le=500)`，
越界一律 422；`_build_state` 对 `events_limit=0` 明确返回空列表；`/api/limits` 新增
`pagination:{max_limit, max_events}` 作为单一事实源。实跑复核：三个越界值全部 422、
`events_limit=0` 返回 0 条、`=2` 返回 2 条。后端 **306/306**。

**R60（2026-11-06）实验名称长度上限下沉到服务层：clone 不再能绕过**

实跑：`POST /api/experiments` 带 10000 字符名称 → **422**；对同一实验
`POST /api/experiments/{id}/clone` 带同样名称 → **200，库里存了 10000 字符**。根因是规则只写在
`CreateExperimentBody`（路由层 pydantic），而 clone 走服务层、没有任何长度校验。修：
`EXPERIMENT_NAME_MAX = 200` 常量同时供路由与服务层使用，`create_experiment()` 自己校验长度；
`/api/limits` 新增 `experiment.name_max_length`，工作台的实验名称输入框据此设 `maxLength`，
超长名称在界面层就不可输入。实跑复核：clone(201) → 422、clone(200) → 200。
后端 **307/307**、前端 **70/70**。

**R61（2026-11-06）测试污染真实数据：两处 `create_app()` 未传 settings，每轮往开发库塞 3 个实验**

起因是开发库的实验数在几轮之间从 46 涨到 64，而我没有创建这么多。实测：跑一次全量测试，
`backend/data/worldlab.db` 的实验数 **58 → 61**（runs 同步 +3）。二分定位到
`tests/test_model_versions.py`：两个 fixture 用 `TestClient(create_app())` 且未传 settings，
`create_app` 回落 `default_settings` → 直接写仓库里的开发库；`two_behavioral_versions` 每次
创建 3 个 `mrp_probe` 实验。修：两个 fixture 改用 `settings` 临时库；并在 `conftest.py` 加
**会话级 autouse 保险**——把 `app.main.default_settings` 换成临时库，任何"忘了传 settings"的
调用都写不到仓库数据；新增 `test_default_app_never_points_at_repo_database` 绑定该保险。
复核：全量测试前后实验数 **64 → 64**（修前 58 → 61）。开发库里已被写入的 51 条 `mrp_probe`
探针实验（模型不在注册表、名称 `mrp`）按 R35 判据清理（先备份到临时目录），剩 13 条真实数据
（queueing 6 / sir 6 / cache_sim 1）。后端 **308/308**。

**R62（2026-11-06）并发 `POST /run` 的 TOCTOU：同一实验曾被并发执行两次**

`run_experiment` 是「先读 status、再无条件 UPDATE + INSERT」两段式，检查与占位之间没有原子性。
探针用 8 线程同时打同一实验（schelling 2000 步保持 running）：**2 个成功、库里 2 条 run**——
同一 spec 被并发执行两次，结果目录里出现两条互相竞争的 run。修：占位改成一条**条件 UPDATE**
（`WHERE id=? AND status!='running'`），以 `rowcount` 判定归属，输者 409；SQLite 单写者
串行化使这条判断成立。复核：服务层 8 线程 → ok=1 / conflict=7 / DB run=1；真实 HTTP
8 个并发 curl → **1×200、7×409**、run=1。新增
`test_concurrent_run_claims_exactly_once`。后端 **309/309**。

**R63（2026-11-06）删除实验的 TOCTOU：检查通过后被并发 claim，运行中的实验仍可被删**

`delete_experiment` 先 `_assert_not_running`（读 status）再无条件 `DELETE`。若两段之间正好有
`POST /run` 抢到占位，删除会成功并级联删掉 run 行，而 worker 仍在执行——最终在后台线程里
抛出一个没人观察的 `NotFoundError`。修：① 删除改为条件语句
（`DELETE … WHERE id=? AND status!='running'`），`rowcount=0` 时再区分 404 与 409；
② worker 启动时若实验或 run 行已消失则**安静退出**，不再把异常留在 Future 里。
反证：把删除改回无条件语句，`test_delete_refuses_when_a_run_claims_between_check_and_delete`
立即变红；还原后全绿。后端 **311/311**。

**R64（2026-11-06）畸形输入不再漏 500：大整数 offset / 路径 id**

对 11 个畸形输入做了一轮扫描（深度嵌套 checkpoint、错误类型的 spec/grid、坏 tag、坏 version、
超大 id 与 offset）：**只有一处漏出 500**——`GET /api/experiments?offset=999999999999999999999`
让 Python 大整数进入 SQLite，抛 `OverflowError`；路径 id 同理（`/api/experiments/999…`）。
修：`offset` 加 `le=1_000_000_000`；路径 id 统一 `Annotated[int, Path(ge=1, le=2**63-1)]`；
边界经 `/api/limits.pagination.max_offset` 导出。复核：11 个用例全部 4xx/201（畸形 restore
深度嵌套也稳定 422）。新增 `test_malformed_inputs_never_leak_500` 常驻。后端 **312/312**。

**R65（2026-11-06）空状态与并发写负载复核（阴性），并更新本周期审计口径**

本轮把 R59–R64 修复过的三类面（输入边界、并发/生命周期、测试卫生）之外的两个面补测：
① **空状态**：新建实验在**尚未运行**时取 `result` 与 `report?format=markdown|json` 均 200，
JSON 报告键集完整（aggregate/experiment/runs/software/comparability_note…），无 500；
② **并发写负载**：20 个并发建批全部 201、10 个并发列表全部 200，SQLite 单写者下无锁超时；
探针批量已从开发库删除（回到 19）。两项均为阴性，未改代码。
审计口径更新：本周期（R59–R64）共修 6 处真实缺陷——分页无下界（`limit=-1` 拉全表）、
名称长度只在路由校验（clone 绕过）、测试写真实库（每轮 +3 实验）、并发 run 双执行、
删除实验 TOCTOU、大整数输入 500。这些都属于上一周期「只看合法输入/单线程」的盲区；
新增的边界扫描、并发测试与畸形输入基线已进回归套件。

**R66（2026-11-06）多进程部署的实测边界：会话随机 404、取消静默失效**

`uvicorn app.main:app --workers 2` 实测（独立临时库）：① 同一会话 id 连续 GET 12 次，
**200 仅 3 次、404 9 次**——会话对象是进程内存态；② 6 个实验各 `POST /cancel` 一次，
全部返回 200，10 秒后仍有 **1 个 running**——取消标志是进程内 `threading.Event`，请求落到
不拥有该 run 的 worker 上就静默失效。这不是可修的「bug」而是**部署约束**：要支持多进程必须
把会话与取消标志外置（Redis/DB 轮询），属于架构变更。本轮把它写成明确限制：README
「已知限制」+ BENCHMARKS 3b + ARCHITECTURE「后台执行模型」三处成文；未改产品代码。
探针库与进程已清理。后端 **312/312**（无代码改动）。
