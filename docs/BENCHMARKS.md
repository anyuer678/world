# WorldLab 性能基准

所有数字均来自真实运行（`backend/scripts/benchmark.py`，共享逻辑在
`app/services/benchmarks.py`，回归阈值在 `backend/tests/test_performance.py`）。
没有任何数字来自常量或估算。

## 测量环境

| 项 | 值 |
| --- | --- |
| 日期 | 2026-11-06（R76 复测，含新模型 sandpile；上一轮为 R38、同一台机器） |
| 解释器 | **Python 3.11.13**——即 `backend/.venv`（`uv run` 使用的解释器）。注意直接敲 `python scripts/benchmark.py` 会走系统 3.12.3，属另一机位，不可与本表混引 |
| 引擎版本 | 1.0（app 0.1.0） |
| 平台 | Windows-10-10.0.26200-SP0（x64，开发机，非专用基准机） |
| CPU | Intel64 Family 6 Model 183 Stepping 1, GenuineIntel |
| 运行方式 | `cd backend && uv run python scripts/benchmark.py`（README 记录的即此条） |

> 下表全部来自**同一次** `benchmark.py` 运行。数字随机器负载明显浮动：R26、R38、R76
> 三轮（同机同解释器链）之间 0–80% 的差异属常态（R76 跑表时有后台进程抢占 CPU，
> 同一脚本连跑两次 schelling 可差 2 倍以上）。因此**只有量级与模型间相对排序可用**，
> 引用数字必须连同上面的日期与解释器一起引用；跨机位数字不得混进同一张表（R26 的教训）。

## 引擎吞吐（进程内，连续 run）

| 模型 | 步数 | 实测耗时 | 吞吐 |
| --- | ---: | ---: | ---: |
| queueing（离散事件） | 100,000 | 0.407 s | ≈245,700 steps/s |
| cache_sim（时间步进） | 100,000 | 0.297 s | ≈336,700 steps/s |
| cellular_automaton（时间步进） | 500 | 0.125 s | ≈4,000 steps/s |
| schelling（同步步智能体） | 500 | 3.375 s | ≈148 steps/s |
| traffic_network（时间步进） | 500 | 0.078 s | ≈6,410 steps/s |
| sir（确定性 ODE） | 5,000 | 0.109 s | ≈45,900 steps/s |
| predator_prey（确定性 ODE） | 5,000 | 0.078 s | ≈64,100 steps/s |
| sandpile（自组织临界） | 20,000 | 0.718 s | ≈27,900 steps/s |

说明：

- cellular_automaton 每步要更新整个网格（例：20×20），单步成本远高于
  排队/缓存模型，吞吐低一个数量级属预期，不是回归。
- **schelling 是目前单步成本最高的模型**：每步对 40×30=1200 个格子做
  全量邻居扫描与重定位（纯 Python），吞吐仅 ≈148 steps/s——适合它的批量规模要据此控制（默认参数 500 步约 1.7–3.4 s/项，随负载浮动）。
- **sandpile 的单步成本随沙堆进入临界态而上升**：前 2,000 步几乎不崩塌（耗时 <1 ms，
  上一轮因此报 n/a），20,000 步时已进入临界、雪崩级联占主导（0.718 s）。基准固定为
  20,000 步就是为了让数字可测；它不适合用「固定步数吞吐」横向比较。
- **分片粒度决定控制延迟**：会话后台线程每片 256 步，所以暂停/重置的生效时间上限就是
  一片的墙钟时间。实测 256×256 元胞自动机（参数上限）一片 **≈4.28 s**，20×20 时一片
  仅 ≈0.06 s——这也是 R40 把控制端点改成「不等待分片、边界交接」的直接依据。
- traffic_network 每步成本取决于路网车辆数，示例路网（小图）下车均
  占用低，500 步仅 0.078 s；大路网/高峰场景下单步成本会上升。
- sir 每步执行 50 个欧拉子步（每子步仅数次乘加），吞吐 ≈45,900 steps/s，与人口规模无关（仓室模型不追踪个体）。
- predator_prey 每步 8 个 RK4 子步 ×4 次斜率评估（32 次/步乘加），
  吞吐 ≈64,100 steps/s，与种群数量无关；同为纯 ODE 仓室级成本。
- cpu_scheduling 的示例参数（作业集）在约 400 个事件后事件队列为空，
  引擎因“无事件可处理”提前停止，因此其吞吐数字没有意义——该模型的
  步数由作业数量决定，不适用于“固定步数吞吐”基准。正确性由
  `tests/test_cpu_scheduling.py` 保证。
- **R31 报告口径**：早停且耗时低于 1 ms 时，`benchmark.py --json` 现在报
  `steps_per_second: null` + `measurable: false`，文本表打印「n/a（<1 ms，测不出）」。
  旧行为把这种情况报成 `0.0 steps/s`——那会被读成数量级回归，而事实恰好相反
  （快到测不出）。有测试绑定（`test_bench_result_never_reports_zero_throughput`）。

## API 延迟（TestClient 进程内往返）

| 指标 | 值 |
| --- | --- |
| POST /api/sessions/{id}/step（n=1），50 次 | p50 = 0.0 ms，p95 = 16.0 ms，max = 31.0 ms |

说明：TestClient 不经过真实 TCP/HTTP 栈；真实部署下的延迟由 uvicorn
另测（见 `docs/` 部署章节的已知限制）。此数字只用于捕捉“单步处理本身”
的数量级劣化。

## 批量吞吐（2 工作线程）

| 项 | 值 |
| --- | --- |
| cache_sim 网格 4 容量 × 2 重复（fixed 种子），每项 1000 步 | 8 items in 0.141 s ≈ 56.74 items/s，status=completed |

说明：条目极小（1000 步/项），该数字主要反映任务调度与 SQLite 写入
开销，而非模拟计算本身；大批量场景下的真实吞吐以 per-item 均值×
引擎吞吐估算更准确。并发上限由 `Settings.max_workers` 控制。

## 回归阈值（tests/test_performance.py）

阈值相对上表实测值留 20–80 倍余量，只用于捕获数量级劣化，
避免 CI / 低配机器上的假失败：

| 测试 | 断言 |
| --- | --- |
| queueing 5 万步 | > 10,000 steps/s（上表同模型 ≈24.6 万，10 万步口径） |
| cache_sim 5 万步 | > 10,000 steps/s（上表同模型 ≈33.7 万，10 万步口径） |
| cellular_automaton 500 步 | < 10 s（上表实测 0.125 s） |
| schelling 500 步 | < 10 s（上表实测 3.375 s，最贵模型） |
| traffic_network 500 步 | < 10 s（上表实测 0.078 s） |
| sir 5,000 步 | < 10 s（上表实测 0.109 s） |
| predator_prey 5,000 步 | < 10 s（上表实测 0.078 s） |
| sandpile 5,000 步 | < 10 s（上表同模型 20,000 步 0.718 s） |
| 会话单步 API p95 | < 1000 ms（本表 p95 = 16.0 ms） |
| 4 项批量 | < 60 s 完成（本表 8 项 0.141 s） |

## 已识别的瓶颈与结论

1. **模拟计算瓶颈**：纯 Python 引擎，排队/缓存吞吐在 10⁵ steps/s 量级，ODE 类在 10⁴–10⁵，智能体类（schelling）在 10² 量级。若未来
   需要 10⁶+ 量级，方向是 NumPy 向量化时间步进模型或 PyPy/Rust 扩展，
   目前不引入（符合“NumPy 仅必要时”的选型原则）。
2. **渲染瓶颈**：前端可视化按采样/节流拉取会话状态，CA 演化视图只渲染
   当前网格而非全量历史（历史仅按需拉取），无逐帧全量传输。
3. **SQLite 写入**：运行指标与批量条目在完成时一次性写库，不在每步写，
   因此 API 单步延迟不受磁盘影响（p50 ≈ 0 ms）。

## 已知限制

### 测量环境与口径限制

1. **开发机基准**：所有数字来自 Windows 开发机（非专用基准机），仅用于
   量级判断与回归捕捉，不代表生产环境绝对性能。
2. **API 延迟不含网络栈**：延迟数字来自 FastAPI TestClient 的进程内往返，
   不经过真实 TCP/HTTP；真实部署下的网络延迟需另行测量。
3. **单节点 SQLite**：存储层为单文件 SQLite，写入为串行化单写者。适合
   开发、教学与中小规模实验；不支持多进程并发写与横向扩展。

3b. **必须单进程运行（`--workers` 只能为 1）**（R66 实测）：会话是进程内存态，
   实验/批量的取消标志也是进程内的 `threading.Event`。用 `uvicorn --workers 2` 实测：
   同一 sid 的 `GET /api/sessions/{id}` 12 次中 **仅 3 次 200、9 次 404**；6 个实验各
   `POST /cancel` 一次（全部返回 200）后仍有 **1 个继续 running**——取消打在了不拥有该
   run 的进程上，静默失效。请使用 `uvicorn app.main:app`（1 worker）或 compose 的默认
   单进程配置；需要水平扩展必须先把会话与取消标志外置（当前未做，见 DECISIONS D85）。

### 运行时资源上限语义（重要）

4. **批量条目受 `default_max_steps` 硬上限约束**：批量执行的每个条目
   `max_steps=None`，引擎按 `Limits.max_steps`（取 `Settings.default_max_steps`，
   默认 **1,000,000** 步；R29 核对：旧文档误写 100,000）硬截断，
   条目以 `step_limit` 终态结束——这是资源有界的**设计语义**，不是缺陷。
   需要更长运行的模型应调大 `Settings.default_max_steps` 或使用
   `stop_condition` 显式限步。**交互式会话同样以 `default_max_steps` 为累计上限**
   （分片推进只是每次 `run` 至多走 `CHUNK_STEPS=256` 步，并不解除总上限；
   R37 核对：旧文档误写「会话不受此默认值约束」）。
5. **取消语义存在轮询粒度**：引擎每 `cancel_poll_interval`（默认 256）
   步检查一次取消标志，因此从发出取消到实际停止最多有一个轮询窗口的
   延迟；同时已到终态（如 `step_limit`）的条目不会因迟到取消而改判——
   批量状态由条目终态聚合，`_finalize` 在无 cancelled/failed/pending/running
   条目时输出 `completed`。
5b. **上限取自配置的一致性（R37 修）**：`Limits` 的四项（`max_steps`、
   `max_wall_seconds`、`zero_delay_chain_limit`、`cancel_poll_interval`）在**实验、
   交互会话、批量三条路径**上都必须取自同一份 `Settings`。此前会话侧构造时只传了
   前两项，后两项静默退回 dataclass 默认值，导致 `WORLDLAB_CANCEL_POLL_INTERVAL`
   与 `WORLDLAB_ZERO_DELAY_CHAIN_LIMIT` 对会话无效，而 `GET /api/limits` 报的却是
   Settings 的值。现由 `test_sessions.py::test_session_limits_come_from_settings`
   与 `test_docs_consistency.py::test_every_service_passes_all_four_limits_fields` 双向绑定。

### 测试可靠性（已修复的实例）

6. **test_cancel_running_batch 曾间歇失败**：原测试用 toy_des（每事件
   无 sleep）造 5,000,000 事件批次，条目实际在 ≈0.23 s 内被
   `default_max_steps` 截断为 `step_limit`；在全量测试套件的 GIL 竞争下
   取消请求可能晚于引擎最后一次取消检查，条目以 `step_limit` 终态落库，
   批量聚合为 `completed` 而非 `cancelled`。经容器内探针证实根因后，
   测试改用 `toy_slow_des`（每事件 sleep 0.5 ms，释放 GIL，且天然死亡
   时间 ≈50 s 不可达），使取消确定性地先于自然终态生效。修复后连续
   30 次运行 0 失败。生产代码语义不变。
7. **本机 `tests/test_sessions.py` 间歇出现 faulthandler「Windows fatal exception:
   access violation」（R39 记录，未归因）**：三次连跑分别为 2/2/0 次，**测试结果始终全绿**
   （16 passed），崩溃转储的栈帧散落在 `tempfile`、`typing`、anyio `queue.get`、
   `random.expovariate` 等互不相关位置；同一轮在 Linux CI 的三个后端 job 日志里出现 0 次。
   本轮确实定位并修掉了一个真实的并发缺陷（join 超时后主线程仍改 engine，见 D64，
   有确定性 gate 测试绑定），但**没有证据表明该缺陷就是这些转储的来源**，因此此处只登记
   现象与「不据此声称已修复」的口径；如需归因需在 Linux 下复现或拿到可稳定复现的最小用例。
