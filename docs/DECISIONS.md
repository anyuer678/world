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

## 环境审查（阶段 0，实测）

- Windows 11 x64，git-bash；Python 3.12.3（`python` 命中官方安装）；uv 已装。
- Node v24.15.0 / npm 11.12.1；Docker 29.6.2（Docker Desktop）。
- 无网络受限迹象（后续 `uv sync`/`npm i` 实测确认）。
- 结论：无技术障碍，按既定技术选型执行。
