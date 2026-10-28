# WorldLab 性能基准

所有数字均来自真实运行（`backend/scripts/benchmark.py`，共享逻辑在
`app/services/benchmarks.py`，回归阈值在 `backend/tests/test_performance.py`）。
没有任何数字来自常量或估算。

## 测量环境

| 项 | 值 |
| --- | --- |
| 日期 | 2026-10-28（R10 复测，模型覆盖补全至全部内置模型） |
| Python | 3.11.13 |
| 引擎版本 | 1.0 |
| 平台 | Windows-10-10.0.26200-SP0（x64，开发机，非专用基准机） |
| 运行方式 | `cd backend && uv run python scripts/benchmark.py` |

## 引擎吞吐（进程内，连续 run）

| 模型 | 步数 | 实测耗时 | 吞吐 |
| --- | ---: | ---: | ---: |
| queueing（离散事件） | 100,000 | 0.421 s | ≈237,500 steps/s |
| cache_sim（时间步进） | 100,000 | 0.282 s | ≈354,600 steps/s |
| cellular_automaton（时间步进） | 500 | 0.140 s | ≈3,570 steps/s |
| schelling（同步步智能体） | 500 | 2.688 s | ≈186 steps/s |
| traffic_network（时间步进） | 500 | 0.078 s | ≈6,410 steps/s |
| sir（确定性 ODE） | 5,000 | 0.125 s | ≈40,000 steps/s |

说明：

- cellular_automaton 每步要更新整个网格（例：20×20），单步成本远高于
  排队/缓存模型，吞吐低一个数量级属预期，不是回归。
- **schelling 是目前单步成本最高的模型**：每步对 40×30=1200 个格子做
  全量邻居扫描与重定位（纯 Python），吞吐仅 ≈186 steps/s——适合它的
  批量规模要据此控制（默认参数 500 步约 2.7 s/项）。
- traffic_network 每步成本取决于路网车辆数，示例路网（小图）下车均
  占用低，500 步仅 0.078 s；大路网/高峰场景下单步成本会上升。
- sir 每步执行 50 个欧拉子步（每子步仅数次乘加），吞吐 ≈40,000
  steps/s，与人口规模无关（仓室模型不追踪个体）。
- cpu_scheduling 的示例参数（作业集）在约 400 个事件后事件队列为空，
  引擎因“无事件可处理”提前停止，因此其吞吐数字没有意义——该模型的
  步数由作业数量决定，不适用于“固定步数吞吐”基准。正确性由
  `tests/test_cpu_scheduling.py` 保证。

## API 延迟（TestClient 进程内往返）

| 指标 | 值 |
| --- | --- |
| POST /api/sessions/{id}/step（n=1），50 次 | p50 = 7.5 ms，p95 = 16.0 ms，max = 31.0 ms |

说明：TestClient 不经过真实 TCP/HTTP 栈；真实部署下的延迟由 uvicorn
另测（见 `docs/` 部署章节的已知限制）。此数字只用于捕捉“单步处理本身”
的数量级劣化。

## 批量吞吐（2 工作线程）

| 项 | 值 |
| --- | --- |
| cache_sim 网格 4 容量 × 2 重复（fixed 种子），每项 1000 步 | 8 items in 0.188 s ≈ 42.6 items/s，status=completed |

说明：条目极小（1000 步/项），该数字主要反映任务调度与 SQLite 写入
开销，而非模拟计算本身；大批量场景下的真实吞吐以 per-item 均值×
引擎吞吐估算更准确。并发上限由 `Settings.max_workers` 控制。

## 回归阈值（tests/test_performance.py）

阈值相对上表实测值留 20–80 倍余量，只用于捕获数量级劣化，
避免 CI / 低配机器上的假失败：

| 测试 | 断言 |
| --- | --- |
| queueing 5 万步 | > 10,000 steps/s（实测 ≈23.8 万） |
| cache_sim 5 万步 | > 10,000 steps/s（实测 ≈35.5 万） |
| cellular_automaton 500 步 | < 10 s（实测 ≈0.14 s） |
| schelling 500 步 | < 10 s（实测 ≈2.7 s，最贵模型） |
| traffic_network 500 步 | < 10 s（实测 ≈0.08 s） |
| sir 5,000 步 | < 10 s（实测 ≈0.13 s） |
| 会话单步 API p95 | < 1000 ms（实测 ≈16 ms） |
| 4 项批量 | < 60 s 完成（实测 ≈0.19 s） |

## 已识别的瓶颈与结论

1. **模拟计算瓶颈**：纯 Python 引擎，吞吐在 10⁵ steps/s 量级。若未来
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

### 运行时资源上限语义（重要）

4. **批量条目受 `default_max_steps` 硬上限约束**：批量执行的每个条目
   `max_steps=None`，引擎按 `Limits.max_steps`（默认 100,000 步）硬截断，
   条目以 `step_limit` 终态结束——这是资源有界的**设计语义**，不是缺陷。
   需要更长运行的模型应调大 `Settings.default_max_steps` 或使用
   `stop_condition` 显式限步。交互式会话不受此默认值约束（分片推进时
   不以 `default_max_steps` 截断）。
5. **取消语义存在轮询粒度**：引擎每 `cancel_poll_interval`（默认 256）
   步检查一次取消标志，因此从发出取消到实际停止最多有一个轮询窗口的
   延迟；同时已到终态（如 `step_limit`）的条目不会因迟到取消而改判——
   批量状态由条目终态聚合，`_finalize` 在无 cancelled/failed/pending/running
   条目时输出 `completed`。

### 测试可靠性（已修复的实例）

6. **test_cancel_running_batch 曾间歇失败**：原测试用 toy_des（每事件
   无 sleep）造 5,000,000 事件批次，条目实际在 ≈0.23 s 内被
   `default_max_steps` 截断为 `step_limit`；在全量测试套件的 GIL 竞争下
   取消请求可能晚于引擎最后一次取消检查，条目以 `step_limit` 终态落库，
   批量聚合为 `completed` 而非 `cancelled`。经容器内探针证实根因后，
   测试改用 `toy_slow_des`（每事件 sleep 0.5 ms，释放 GIL，且天然死亡
   时间 ≈50 s 不可达），使取消确定性地先于自然终态生效。修复后连续
   30 次运行 0 失败。生产代码语义不变。
