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
16. **批量扫描曲线**（R8，sweepChart.ts + BatchPanel 扫描曲线区）：前端从
   batch summary 就地重建发现切片（D32 镜像 D31 规则）。4 项单测：仅
   modal 切片 ≥3 值的参数可选（混合网格 servers 可选、load 两值被排除）、
   序列按参数排序且其余参数固定在众数（load=0.5）、指标缺数据/切片 <2 点
   返回 null、默认选中跟随 jump 发现的指标（无发现落字母序首）。42 项前端
   全过、tsc/build 干净。浏览器 E2E（批「发现验证-服务器数扫描」）：默认
   选中 servers×avg_queue_length（首条 null-ratio 发现）——实测先修掉一个
   时序 bug（findings 未返回时默认落到 arrived）；点击 final_queue_length
   发现 → 指标切换且曲线重绘（#2563eb 蓝像素 148）；指标下拉换
   avg_waiting_time → 重绘（115 蓝像素）；控制台无错误。
17. **SIR 传染病模型**（R9，确定性仓室 Euler + SirView 三曲线）：模型契约见
   DECISIONS D33。后端 10 项单测：S+I+R 守恒（80 步后与总人口差 <1e-6）、
   阈值下方熄灭（β=0.05/γ=0.1 → 感染率 <5%、峰值 <100）、阈值上方爆发
   （β=0.5 → 感染率 >60%、峰值 >10% 人口、峰值先于终点）、β 扫描相变
   （5 点严格递增、两端 0.044/0.579 悬崖）、同种子确定性、引擎
   checkpoint/restore 往返等价、600 步历史有界且覆盖全程、零传播只清空
   感染者、参数校验（人口下限/初始感染越界/β γ 负值）、三场景实跑守恒。
   科学核对：万人 R₀=5 场景峰值 4786（第 21 天）vs 连续解析解
   1-(1+ln5)/5≈47.8%——47.9% 精确吻合。前端 SirView 三曲线（S 蓝/I 红/
   R 绿，复用 chartRender）+ 统计行（第 N 天/R₀/三仓室/峰值），43 项前端
   单测含 sir 速读分支（大流行/扩散/熄灭 + 峰值）。浏览器 E2E：场景卡
   「疫情爆发」跑 120 天渲染正常；批量 β∈[0.05,0.3] 扫描发现 5 条——
   attack_rate 13.2 倍断崖、peak_time ratio=null「从无到有」；扫描曲线
   默认 beta×peak_time，点击 attack_rate 发现切换重绘（#2563eb 352 px）；
   后端 223/223、tsc/build 干净、控制台无错误。
18. **R10 巡检轮：基准覆盖补全 + 快速入口补全**（决策见 DECISIONS D34）。
   巡检发现两处「加模型欠下的对账债」：性能基准只测 4/7 模型
   （schelling/traffic_network/sir 无实测数字、无回归保护），首页
   QUICK_PICKS 只有 4/7 模型。修复：benchmark.py 三模型进基准
   （schelling 500 步 / traffic 500 步 / sir 5,000 步），test_performance.py
   加 3 条宽松回归（各 <10 s），BENCHMARKS.md 全表复测刷新（2026-10-28：
   queueing ≈23.8 万 steps/s、cache ≈35.5 万、CA ≈3,570、schelling ≈186
   最贵——每步全扫 1200 格邻居、traffic ≈6,410、sir ≈40,000；API p95
   16 ms、批量 8 项 0.19 s），QUICK_PICKS 补 sir/cpu_scheduling/cache_sim
   至 7 条且 logic.test.ts 断言同步。浏览器 E2E：刷新后首页快速入口
   7 模型齐全，点「疫情爆发」快捷按钮实跑 SIR 完成；SIR 曲线三色像素
   探针（S 蓝 483 / I 红 338 / R 绿 505）；交通 rush-aftermath 400 拍
   152 发车全完成、CPU 调度 30 作业完成甘特图正常；实验报告导出复验
   （实验 #5 SIR：MD/JSON 均 200，含 spec/运行记录/result_sha256/聚合）。
   后端 226/226（+3 性能回归）、前端 43/43、tsc/build 干净、控制台无错误。
19. **R11 巡检轮：axe-core 无障碍清零 + 架构文档对账**（决策见 DECISIONS D35）。
   工具链：Chrome 未装、chrome-devtools MCP 不可用，改用 browser-use 注入
   axe-core@4.10.2（CDN 实际加载成功）对 dev 页全量扫描。修前空态 4 类
   违规：color-contrast 5 处（#9ca3af 2.43:1 模型元信息行、#999 2.72:1
   参数说明 small）、scrollable-region-focusable（事件日志滚动区不可键盘
   访问，serious）、landmark-one-main / region（无 main 地标，55 节点悬空）。
   修复：灰阶文字 #888/#999/#9ca3af → #6b7280（App/SimView/ParamForm/
   ComparePanel，SVG 文字同步，canvas 刻度不动）、日志滚动区
   tabIndex=0+role=region+aria-label、顶层容器改 <main>。修后空态 0 违规
   （34 规则过）、跑排队场景后的会话态 0 违规（42 规则过）。
   另对账两处：ARCHITECTURE.md 目录树（阶段 1 后未更新——models 缺
   schelling/traffic/sir 三包且旧目录名拼写错误、engine/services/前端文件
   按实际重列）、index.html 补 meta description（lang/title 原本就在）。
   回归：后端 226/226、前端 43/43、tsc/build 干净。
20. **R12 巡检轮：WebSocket 声明对账 + 批量操作按钮首次实测**（决策见 DECISIONS
   D36）。grep 证实 routes.py/api.ts 零 WebSocket 实现，ARCHITECTURE.md 三处
   「REST + WebSocket / REST/WS 契约 / REST/WebSocket 路由」均为失实描述，
   已改为 REST + 轮询并保持框图风格。浏览器实测两个此前只有 pytest 覆盖的
   操作：① CSV 导出——GET /api/batches/4/export.csv 返回 200
   text/csv，头三行 # 元信息 + 列名行齐全，前端为同一 URL 的 <a download>；
   ② 取消批量——新建 schelling 批次 #5（tolerance 0.1/0.3/0.5 × 3 重复 =
   9 项，单项最高 10000 步 ≈54 s），启动 5 秒后点「取消批量」→ UI 状态行
   「状态 cancelled」、API counts {cancelled: 9}，无悬挂 running 项。控制台
   0 错误（仅 vite/React DevTools debug 信息）。本轮零代码改动（仅文档），
   后端链路经实跑覆盖（创建/轮询/取消/导出均真请求）。
21. **R13 巡检轮：暂停/恢复 E2E + 运行中重置死锁修复**（决策见 DECISIONS D37）。
   浏览器实测暂停语义：schelling 会话运行至 step 1536 点「⏸ 暂停」→ 第一次
   读数仍在推进（1280→1536）属 D15 分片语义（256 步一片，≈1.4 s 到边界），
   边界后连续 4 s 读数定格 1536、状态「已暂停」，「⏵ 恢复」继续推进——行为
   符合设计非缺陷。同轮发现真缺陷：运行中点「↺ 重置」→ step 归 0 但状态
   卡「已取消」，此后 run/step 409，需二次 reset。根因：reset() 持锁 join
   运行线程，线程退出要拿同锁写 "cancelled"，互等至 join 超时后线程覆写
   "idle"。修复：join 移到锁外（与 pause() 一致）。回归测试
   test_session_reset_while_running（新增 toy_slow_step 测试模型，每步
   sleep 0.5 ms 保证 reset 落在分片中途）：临时还原修复实证失败
   （status=cancelled），复用修复后 13/13 通过。浏览器修复后复验：重置 →
   「就绪」step 0 → 重跑推进至 1024 正常。错误路径实测：占用率填 1.5
   （上限 0.98）提交 → UI 错误横幅「spec validation failed:
   params.occupancy Input should be less than or equal to 0.98」，控制台
   仅该预期 422。回归：后端 227/227（+1）、前端 43/43、tsc/build 干净。
22. **R14 巡检轮：报告导出/载入配置/比较面板/终态 UX/检查点全链路实测**（决策见
   DECISIONS D38）。本轮零代码改动，九条此前仅 pytest 覆盖或从未实跑的链路
   全部浏览器/HTTP 实测通过：① 报告导出——历史区「报告MD/报告JSON」
   （<a download> 指向 /api/experiments/{id}/report），curl 实测 MD 200
   text/markdown（标题/配置/指标齐全）、JSON 200 application/json
   （report_version/generated_at/software/experiment/runs/aggregate 七键）；
   ② 载入配置——点历史行「载入配置」→ 表单切换至 queueing v1.0.0 并提示
   「已载入实验 #3 的配置」；③ 比较面板——勾选 ≤4 个实验（第 5 个勾选被
   上限拒绝）→「比较所选实验」→ 31 列指标按模型补齐、不适用显示 —，跨
   模型比较自动显示「默认不可直接比较」警示；④ 终态 UX——queueing 会话
   跑至 200/200 状态已完成（completed）后，单步/连续运行/暂停/恢复全部
   正确禁用（disabled=true，仅重置可用），点按无请求发出（前端静默防呆
   属预期）；⑤ 单步 ×N——步数填 25 后按钮动态显示「单步 ×25」，一次请求
   推进 25 步；⑥ 存配置为新实验并运行——生成 #6 并全新运行，历史即时
   刷新；⑦ 批量非法参数名——网格参数名填 bogus_param 提交 → 错误横幅
   「grid unknown parameters for model queueing: ['bogus_param']」，批量
   未创建，控制台仅该预期 422；⑧ 检查点全链路（阶段 2 功能首次脱离
   pytest 的 HTTP 实测）——cache_sim 会话跑 500 步 → POST checkpoint
   （step 500, model v1.0.0, params_digest 等十键）→ 新会话 POST restore
   → 快照与源会话逐字节相等（hits 267 / hit_rate 0.534 / 缓存内容 /
   recent 历史 / metrics）；⑨ 恢复后重跑——停止条件已达成时 run 返回
   200 并优雅再次完成（无悬挂）。回归：后端 227/227、前端 43/43、
   tsc/build 干净。
23. **R15 巡检轮：停止条件两型实测 + Docker 生产形态复验（R7 后首次）**（决策见
   DECISIONS D39）。①「按模拟时间」停止条件——queueing 会话停止值 50，
   运行至 sim_time 49.8152（step 89）状态已完成（completed），语义正确
   （越过阈值即停）；②「直到事件队列为空」——cpu_scheduling（作业数量
   200，到达率 1）运行至 sim_time 227.6721 全部作业完成，UI 正确隐藏
   「停止值」输入框；③ Docker 复验——docker compose build 重建两镜像
   （依赖层缓存命中，仅源码层重建），up 后 api 健康检查通过，/api/models
   返回全部 7 个内置模型（含 R9 新增 sir），容器内 SIR 会话创建→运行→
   300/300 完成（attack_rate 0.941、峰值 3008 @ 38 天）→checkpoint 200，
   nginx 产线前端首页渲染 + /api 代理 200 + 快速入口一键运行 SIR 会话
   跑完；down 后数据卷 world_worldlab-data 保留。本轮零代码改动。回归：
   后端 227/227、前端 43/43、tsc/build 干净。
24. **R16 巡检轮：批量超时/种子策略实测 + 发现文案修复**（决策见 DECISIONS
   D40）。① 三种种子策略 UI 实测（API items 逐项核对）：fixed——6 项全部
   seed=42（同配置同种子，配对比较语义，亦解释历史实验中重复行指标完全
   相同）；unique——servers 1/2 × 3 重复 → 42–47 按 item_index 连续递增；
   per_repeat_increment——单组合 × 5 重复 → 42–46 按 repeat_index 递增。
   ② wall_timeout 批量语义（默认 60s 墙钟 + schelling 10000 步首次实测）：
   3 项中 2 项 wall_timeout（7936 步@60s，尝试=1 不触发重试——重试仅为
   异常保留）+1 项 completed，批量状态 completed（wall_timeout 计为合法
   终态而非失败）；两项超时项 metrics 完全一致（同种子同分片边界=确定性
   轨迹的旁证）；详情面板计数行「completed: 1 · wall_timeout: 2」、单项
   行含尝试数与 steps。③ 修复发现文案缺陷：无网格参数批量的 dispersion
   类发现渲染为「在 处，指标…」（占位符空白），findings.ts 空参数时去掉
   位置从句，新增单测（44/44），浏览器复验文案直接以「指标 …」开头。
   回归：后端 227/227、前端 44/44、tsc/build 干净。
25. **R17 巡检轮：参数表单数组字段修复 + API-only 实验端点核验**（决策见
   DECISIONS D41）。① 发现并修复真实缺陷：ParamForm 对数组类型参数
   （cache_sim 的显式访问序列 accesses 等）无渲染分支，兜底文本框把原始
   字符串（如 "1,2,3,…"）直接塞进 params 提交，后端 422 "Input should
   be a valid list"——该字段在 UI 上自始不可用（网络面板证实点击后仅此
   一个 422 POST，无会话创建）。修复：新增 ArrayField——整数列表用逗号/
   空格/分号分隔解析（number 类型放行小数），嵌套数组/对象数组走 JSON
   文本；解析失败红字提示且保留最近一次合法参数（与数字字段行为一致，
   不静默清空）；schema.ts 补 items 类型声明。浏览器实测：显式序列
   1,2,3×3 + 容量 3 + 停止 9 步 → completed，命中 6/缺失 3/命中率
   66.7%/总成本 36/平均成本 4.0，与 API 直传列表的先行真值逐位一致（缓存
   槽位显示 key 1-3）；输入 "abc" 出红字提示且输入不被吞、清空后恢复。
   连带受益：CA/谢林 initial_grid、CPU jobs（同为可选数组参数，此前同样
   只能走兜底字符串）。② 实验模块 API-only 端点首次实跑核验（前端零
   引用，与 D38 检查点同例：能跑通即记录，不删契约）：run(wait=false)
   → run_id 排队 → 中途 cancel → cancelled；rerun → 新 run_id 排队；
   clone → 新实验（含 spec 复制）；PUT tags 生效；DELETE ×2 → 204，
   列表还原至 1–6（探针数据清理干净）。回归：后端 227/227、前端 49/49
   （新增 parseArrayText 5 条）、tsc/build 干净。
26. **R18 巡检轮：ArrayField JSON 分支 + TrafficPanel 全链路实测**（决策见
   DECISIONS D42）。① CA 指定初始图案（嵌套数组 JSON 分支）浏览器 E2E：
   5×5 initial_grid 水平闪光灯 + 停止 1 步 → completed，API 快照断言终局
   rows=["00000","00100","00100","00100","00000"]（横→竖精确符合 B3/S23，
   出生 2/死亡 2/存活 3/密度 0.12）；非法 JSON（"1,2"）出红字「需为合法
   JSON 数组」，尺寸不匹配（2×2 配 5×5）出 422 横幅「initial_grid must be
   exactly height rows of width cells」。② 顺带修复 resolve() 折叠 anyOf
   时丢弃外层 title/description——可空字段（accesses/initial_grid 等）的
   中文描述自阶段 3 起从未渲染，修后「给出 0/1 矩阵…」正常显示，新增
   单测（49→50）。③ TrafficPanel 首次全链路：预设单向环线（6 节点 6 边）、
   非法 JSON role=alert「JSON 解析失败…」、手工加 n6 节点后失焦提交——
   脚本化 focus/blur 得到「UI 显示 7 节点但 POST 6 节点」的假象，改用真实
   Tab 键事件 + 捕获请求体证实 n0–n6 全部到达 POST body（自动化伪影而非
   产品缺陷）；环线 300 tick 跑完（发车 241/完成 82）、自定义 7 节点
   300 tick 跑完（发车 289/完成 48）。回归：后端 227/227、前端 50/50、
   tsc/build 干净。
27. **R19 巡检轮：CPU jobs 对象数组 + 谢林初始布局 + sim_time 补矩阵**（决策
   见 DECISIONS D43，零代码改动验证轮）。① CPU 调度显式作业列表（对象数
   组，ArrayField JSON 分支第三形态）浏览器实测：表单填
   `[{"arrival":0,"service":5,"priority":1},{"arrival":1,"service":3,"priority":2},{"arrival":2,"service":2,"priority":0}]`，
   捕获请求体证实 jobs 为真 JSON 对象数组（非裸字符串）；停止条件
   until_empty + FCFS → completed，API 快照 run_log=[[0,5,0],[5,8,1],
   [8,10,2]]、avg_wait=10/3≈3.3333、avg_turnaround=20/3≈6.6667、CPU 利用
   率 100%、吞吐 0.3，与手算真值逐位一致；同一份 jobs 表单切 SJF 重跑 →
   run_log=[[0,5,0],[5,7,2],[7,10,1]]（t=5 短作业 #2 插队）、avg_wait=3.0、
   avg_turnaround=6.333，页面事件日志 dispatch 顺序 #0→#2→#1 与 API 一致。
   ② 谢林指定初始布局 5×5 全 1（宽高同步改 5）跑 1 步 → API 快照 rows 逐
   格等于输入（"11111"×5）、unhappy_rate=0、moves_total=0、隔离指数 1.0、
   population=25（全同网格人人满意不变量）。③ CA 停止条件「按模拟时间」
   3 → completed、step=3、time=3.0（时间步进模型 sim_time 与按步数等价，
   停止条件矩阵补齐）。回归：后端 227/227、前端 50/50、tsc/build 干净。
28. **R20 巡检轮：空停止值边界定性 + SIR 交互会话复验**（决策见 DECISIONS
   D44，零代码改动验证轮）。① 空停止值边界：UI 清空停止值输入框（无本地
   守卫，提交 Number('')=0）→ 后端 422「spec validation failed:
   stop_condition.steps.value Input should be greater than 0」→ 页面红字
   横幅如实显示、无会话创建（网络日志 422 POST、无 201 跟随）；API 直探
   证实 steps/sim_time 的 0 与负值同拒。② SIR 交互会话 E2E（R9 后首次复
   验，历经 ParamForm/resolve 重构）：表单默认参数 β=0.3/γ=0.1/万人/10
   感染跑 50 天 → API 快照 S=1346.011/I=1977.234/R=6676.755、峰值
   3008.003@38 天，逐位命中按引擎同式（50 子步欧拉 h=0.02）手算的真值；
   S+I+R=10000 守恒精确、r0=3.0 显示正确；页面速读「累计感染率 86.5%，
   大流行：绝大多数人口被感染。感染峰值 3008 人、占总人口 30.1%（第 38
   天）」与 metrics 同源自洽。回归：后端 227/227、前端 50/50、tsc/build
   干净。
