# 测试策略

## 层级
1. **core 单元**（pytest）：事件队列排序（time/priority/seq、零延迟 FIFO、链上限）、
   时间步进引擎、DES 引擎、检查点恢复等价性（中断续跑 == 一次跑完，逐值相等）、
   RNG 种子确定性、资源上限触发。
2. **模型正确性**：
   - 排队：同种子两次运行指标完全一致；M/M/1 (ρ=0.5) 的 L、W、利用率与理论值
     容差对照；M/M/1/1 丢弃率对照 Erlang 损失公式；参数校验边界（λ≤0、servers=0、
     capacity=0 拒绝）；边界（capacity=1、确定性到达）。
   - 其余模型阶段 3 同模式：理论对照 + 确定性 + 边界。
3. **schema**：非法 spec 拒绝、v0→v1 迁移升级、未知 model_id 拒绝、参数双层校验。
4. **API 集成**（httpx + 临时 SQLite）：健康检查、模型列表、建实验→运行→取结果
   全链路、非法参数 422、取消、克隆、tags、结果 sha256 一致性、迁移幂等。
   **交互会话**（test_sessions.py）：创建/单步计数、连续运行到完成、轮询在
   running 期间必须见到 step 递增（回归：分片间节流缓存刷新）、暂停/恢复后
   步数单调不减。
5. **前端**（vitest，`npm run test`）：15 项单元测试覆盖纯逻辑——状态标签映射
   （statusLabel）、状态值格式化（formatValue）、批量网格值解析（parseValues）、
   参数 schema 引用解析（resolve：$ref/anyOf/allOf）。组件级与浏览器自动化
   （Playwright）未引入；工作台核心链路已在真实浏览器手工实测（创建会话/单步/
   连续运行实时步数/暂停/重置/确定性重放/存为实验/载入配置），跨层端到端由
   API 级 test_e2e.py 覆盖。
6. **性能**（阶段 6）：基准脚本记录吞吐（事件/秒）、内存；结果写入 docs/BENCHMARKS.md。
7. **阶段 6 专项**：test_performance.py（吞吐/API 延迟/批量回归阈值）、
   test_recovery.py（进程重启恢复/中断续跑/损坏 spec 拒绝）、test_e2e.py
   （建实验→运行→比较→导出→批量全链路）。
8. **完整性专项**（test_integrity.py，R1）：run 行种子可复现（seed=None 运行后
   用落库种子重放 sha256 一致）、聚合只计 completed（截断运行带 metrics 不污染
   均值）、巨型网格先计数后展开（10^12 组合直接 422 且不物化）、批量在途并发
   逐批封顶（_TrackingExecutor 实测 concurrency=1/2 下峰值在途数）、检查点绑定
   model_version+params 摘要（跨版本/跨参数恢复拒绝）。

## 已知环境噪声
- Windows + CPython 3.11 下 pytest 偶发打印
  `Windows fatal exception: access violation` + 线程栈（栈顶多为
  `_pytest/tmpdir make_numbered_dir` 或 pathlib `stat/mkdir` 文件探测）。
  这是 faulthandler 对 first-chance 异常的良性上报：改动前基线 3/3 复现同一
  签名、进程不退出、exit=0、junitxml 136/136 全过，与平台代码无关。判据：
  只看 exit code 与 junitxml 计数，不把该噪声当测试失败。

## 原则
- 所有随机测试用显式种子；理论对照允许统计容差并注明样本量。
- 每阶段完成先跑全量 pytest 再进下一阶段；失败必须修复而非跳过。
- 禁止 mock 掉被测的模拟逻辑本身；DB/API 边界可用临时文件库。
