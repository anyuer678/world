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
9. **交通路网**（test_traffic.py，R2）：路网参数校验（重复节点/未知端点/自环/
   重复边/共点无长度/信号分组覆盖/spawn 源）；同种子确定性 + 异种子不同；
   检查点续跑等价；理论对照（30 格单车道 v_max=2 单车行程恰 15 tick）；单向环
   隔 tick 放行节奏（10 tick 发 6 辆）且全部排空；信号灯降低吞吐并增加等待
   （同种子对照）；占用不变量（任意 tick 每格至多一车、车辆表与占用表一致）；
   车辆上限；API 会话/实验闭环。前端（trafficRender.ts 单测 + 浏览器实测）：
   路网解析/边界退化/格数推导；工作台路网编辑（预设/JSON/预览）与实时车辆
   canvas 渲染经像素级探针验证（车辆蓝/红点、信号相位、路段占用着色）。
10. **场景库**（test_scenarios.py，R3-P0）：内置 5 模型每个 ≥2 个场景；逐场景
   校验形状（六键齐全、params 非空 dict、steps 停止条件、seed 非负）、
   标题/描述含中文、经 `validate_spec` 双层校验、引擎实跑 200 步产出非空
   metrics；`/api/models` 暴露 scenarios；模型 display_name/description 中文。
   前端（App.tsx 导出纯函数单测 + 浏览器实测）：modelTypeLabel/scenarioSpec
   单测；一键场景卡片点击 → 自动建会话 + 连续运行 + 滚动到模拟视图，经
   evaluate 探针实测三模型链路（排队三窗口等待 0.03s vs 单窗口 9.59s、
   交通场景 canvas 像素证据：车辆/停止车/红灯像素均 >1000，指标 400 拍
   完成 596 辆）。
    - 浏览器环境注意：内嵌离屏浏览器中 `requestAnimationFrame` 永不触发、
      `behavior:'smooth'` 平滑滚动不执行——滚动引导必须用瞬时
      `scrollIntoView({block:'start'})`，勿用 rAF 门控。
11. **结果速读与首屏**（R3-P1，summary.ts + App.tsx）：summarizeMetrics 按
   visualizer.kind 分派（queue/cache/ca/traffic/cpu_schedule）把 metrics 翻译成
   2-3 句中文判断（利用率分级、命中率分级、种群峰值/萎缩、完成率判拥堵、
   CPU 等待/周转），未知 kind 与缺失指标安全降级（返回空/“-”）；26 项前端
   单测覆盖全部分支。浏览器实测：排队超载场景速读「利用率 95.0% 贴近极限 +
   丢弃率 37.2% 容量不足」，交通高峰消散场景「152 发 152 完 整体畅通」。
   首屏重构（模拟视图置顶、模型/场景/运行控制在左、参数在右、批量与比较
   折叠进「高级」details 默认收起）经 DOM 探针验证：标题顺序、details 默认
   关闭、展开后批量面板可用、下方卡片点击后向上滚动到位并完成运行。
   空态引导（R3-P2）：模拟视图空态直接渲染 3 个推荐场景快捷按钮
   （生命游戏/高峰堵死/无灯路口，quickPicks 从 models 列表现查、缺失安全
   跳过，28 项前端单测）；浏览器实测从空态点击「生命游戏」直达完成运行，
   ca 速读判级经 population_max 核对（81/239=34% → 波动中）分支正确。

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
12. **可视化重构**（R4-vis，chartRender.ts + SimView.tsx + 三模型历史数据）：
   后端 queueing/cpu_scheduling/cache_sim 的 `_s` 增加 log 抽稀历史（新样本计数
   `hist_n % hist_stride == 0` 才落点，超 256 点整体减半 `hist[::2]` 且
   `hist_stride *= 2`——任意时长运行都保有约 128-256 个跨全程样本，确定性、
   进检查点；cpu 另记 `run_log` 最近 256 段 `[start,end,seq]` 甘特记录，cache
   另记 `recent` 最近 256 次命中位串；load_state 对旧检查点缺键 setdefault
   兜底）。前端新建 chartRender.ts（drawLineChart/drawGantt/drawAccessStrip +
   seriesBounds/niceMax/fmtTick/ganttRows/ganttExtent/runsFromBits 纯函数，
   与 trafficRender 同风格）；SimView 五视图全部接入 canvas 图表：排队三曲线
   （忙碌服务台/在系统/等待队列，绘制顺序=图层层序，大线后画）、CPU 甘特图
   （按最近活跃取 ≤16 行）+ 就绪/已完成双曲线、缓存命中条（RLE 连续段着色）
   + 累计命中率曲线、CA/交通 SVG 折线升级为坐标轴 canvas 曲线。验证：后端
   180/180、前端 34/34、tsc/vite build 干净；浏览器像素探针逐视图取证——
   排队三色（amber 2295/blue 142/green 453 px，15002 到达）、CPU 甘特+双曲线
   （rr 30/30 完成、利用率 73.7%）、缓存命中条（绿 5310/红 4032 px，5000 次
   命中率 50.0%）、CA（11664 黑像素 = 81 细胞 × 12px² 精确吻合）、交通（400
   tick、798 发 736 完、车辆蓝 1778 px）；控制台无错误。
13. **谢林隔离模型**（R5，同步步智能体 + 前端 SchellingView）：模型契约见
   DECISIONS D30。11 项单测：零容忍零移动、同色网格恒满意、孤立错组者有
   空格一步安顿、满员无空格不动（同步步契约性质）、群体守恒不变式
   （pop_a+pop_b 步间不变）、同种子确定性、引擎 checkpoint/restore 往返
   等价、轻微偏好隔离指数上升、参数校验边界、三场景实跑、无偏好场景零
   搬家。科学结论核对（seed 4）：无偏好 seg≈0.503/0 moves；轻微偏好 60 步
   seg 0.729/382 moves/全员安顿；苛刻偏好 seg 0.994/12202 moves（持续动荡）。
   前端：SchellingView 双色 canvas（蓝/琥珀）+ 不满红点叠加 + 不满率/隔离
   指数双曲线（复用 chartRender），速读分支按 moves_total=0 / 不满率分级
   （35 项前端单测）。浏览器像素探针：轻微偏好跑完 60 步「不满 0（0.0%）·
   隔离指数 0.73 · 累计搬家 382」蓝 111313/琥珀 115425 px；苛刻偏好重置后
   单步 ×3，第 3 步「不满 764（76.0%）」→ 网格红点 19100 px =
   764 × 5px² 精确吻合，速读「动荡不休、大体混居」分支正确；控制台无错误。
14. **批量自动发现**（R6，analysis_service + `GET /api/batches/{id}/findings`
   + BatchPanel 自动发现区）：启发式契约见 DECISIONS D31。后端 10 项单测：
   单参数扫描检出跳变（2.6→26 因子 10）、平坦扫描/多参数混合网格零误报、
   每（参数×指标）去重留最大（0.8→0.95 检出 10.0 倍）、坍缩为零
   ratio=null、从零激增 ratio=null、0→0 零对不算变化、离散 CV≥0.5 且
   n≥3 才报、analyze_summary 形状与免责声明、API 实批 200/未知批 404。
   前端 findings.ts 跳变方向/因子、完全消失/从无到有、离散文案单测
   （38 项全过）。浏览器 E2E（真批「发现验证-服务器数扫描」servers
   [1,2,4,8]、确定性 ρ=1.9 排队、130000 步）：自动发现区渲染 4 条——
   队列长 4654.89 / 等待 2462.45 / 终队长 9311 三条「坍缩为 0（完全
   消失）」+ 平均逗留 2462.97→1（约 2462.974 倍），免责声明文案在列；
   0→0 假阳性（drop_rate/dropped）与 9.3e15 无意义倍数均在浏览器实测
   复现后修掉；后端 207/207、前端 38/38、tsc/vite build 干净。
15. **Docker 复验与镜像钉版**（R7）：R1-R6 大量改码后重验生产形态，并修掉三个
   交付缺陷——①前后端均无 .dockerignore，构建上下文携带 node_modules/.venv
   共约 149MB（实测 du）→ 新增两个 .dockerignore；②前端镜像只 COPY
   package.json 且用 npm install，锁文件完全不参与 → 改为 COPY
   package-lock.json + `npm ci`；③后端镜像未 COPY uv.lock，`uv sync --frozen`
   在容器内必然失败并静默回退到非锁定解析 → COPY uv.lock 并去掉 `||`
   回退。复验（compose up）：api healthcheck 通过；nginx 反代 /api 返回六
   模型；浏览器在 5173 点「轻微偏好」场景卡跑完 60 步，不满 0（0.0%）/
   累计搬家 382，与 R5 本地验证逐位一致（确定性跨环境成立）；容器 API 建
   批（servers [1,2,4]）后 GET findings 返回 4 条（final_queue_length
   ratio=null 坍缩 + 3 条有限因子）。阶段 6 已验的会话步进/实验运行/导出
   链路本轮未重复验证。
