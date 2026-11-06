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
29. **R21 巡检轮：queueing 现代化复验（七模型复验矩阵收口）**（决策见
   DECISIONS D45，零代码改动验证轮）。① 嵌套对象参数分支首次 UI 实测：
   到达过程/服务过程渲染为嵌套 fieldset，表单改「平均服务时间」1→2 →
   后端实收 service={kind:'exponential',mean:2,half_spread:0}（嵌套合并正
   确）。② 超载工况（λ=1、均值 2，ρ=2）：利用率 0.9997、队列终长 6715、
   吞吐 0.4999 被钳制到服务容量 0.5，served+队列+在服=arrived 守恒。③
   稳定 M/M/1（均值 0.5，ρ=0.5，steps 20000，seed 42）：利用率 0.4952、
   Little Lq=λ·Wq 偏差 0.74%、平均逗留 0.956 vs 精确解 1.0（4.4% 波动）、
   served=arrived=10000 零丢弃。④ 决定论：UI 与 API 直建同 spec+seed
   metrics 逐位一致；速读文案自洽。回归：后端 227/227、前端 50/50、
   tsc/build 干净。
32. **R22 开发轮：第八内置模型「捕食者-猎物」（Lotka-Volterra）**（决策见
   DECISIONS D46）。① 后端：time_stepped 纯确定性 ODE，RK4 8 子步/时间单位，
   参数 α/β/δ/γ/两群初值/可选容纳量 K（nullable）。10 条单测全绿：经典版
   首次积分 δx−γ·ln x+βy−α·ln y 守恒（60 步漂移 1.5e-05）、K=8 收敛内平衡
   (5.000000, 0.937500)（偏差 1e-15 级，x*=γ/(δβ) 与 K 无关的解析结论入测）、
   y₀=0 时与指数/逻辑斯谛闭式解对照（<1%）、大振幅周期 > 小信号周期
   2π/√(αγ)、检查点逐字节恢复、历史抽稀 ≤256、参数边界 7 例、三场景全跑。
   ② 前端：新 kind `predator_prey`——时间序列双曲线 + 平台首个相平面轨道图
   （紫轨道/绿起点/红当前/蓝十字平衡点，复用 useCanvas 自绘管线）；速读分
   「仍在大幅兴衰循环 / 收敛到平衡点稳定共存」两型，新增前端单测（50→51，
   含 quickPicks 八模型顺序断言）。③ 浏览器 E2E（一键场景卡）：经典循环卡
   → completed 60 步，DOM 显示平衡点 (5.00, 2.50)、周期 9.0、峰值 7 次，
   与解析值/小信号下界一致；K=8 卡 → 收敛 (5.00, 0.94) 命中解析平衡点；
   相平面 canvas 像素探针（轨道 694px、起点 24px、当前 12px、平衡十字 12px、
   边框 232px）证明真实绘制而非空白；UI 会话与 API 同 spec+seed 复跑
   metrics 逐位一致；控制台零错误。④ 全链路同步：场景库回归（BUILTIN_IDS
   第八项）、基准脚本与 BENCHMARKS.md（实测 35,461 steps/s）、回归阈值、
   README 模型表、SEO meta 描述（八个内置模型）、QUICK_PICKS 快速入口。
   回归：后端 244/244、前端 51/51、tsc -b/vite build 干净；Docker 生产形态
   复验另条续记。
   ⑤ Docker 复验（新模型节奏，R15 后首次）：compose 构建起 api(healthy)+
   nginx web；容器内 `/api/models` 直连与经 nginx 代理均报 8 模型含
   predator_prey；生产 index.html 携带「八个内置模型」SEO 描述；经代理在
   容器内完整跑 predator_prey 会话（K=8、240 步）→ completed，收敛
   (5.000000, 0.937500) 命中解析平衡点（<1e-6）。验毕 compose down。
33. **R23 开发轮：扫描曲线 95% CI 区间带 + 发现文案 CI 显著性**（决策见
   DECISIONS D47）。① drawLineChart 新增 band：均值线后半透明填充多边形（上
   界正序+下界逆序），seriesBounds 并入带界防裁切；sweepChart 仅当 n≥2 且带
   宽>0 输出带，否则 null。② 后端跳变发现加 ci_overlap 三态（False 不重叠
   /True 重叠/None 无法判定——n<2 或零宽退化 CI，如 fixed 种子重复全同）；
   前端发现文案三分支加注。③ 单测：后端 ci_overlap 三态+零宽退化 1 条新
   测试（analysis 套件 11 项）、前端带抽取（真实宽 CI 命中三点带、退化夹具
   band=null）+文案三分支（53 项，含 quickPicks 八模型）。④ 浏览器双分支实
   证：批 #11（queueing servers 1/2/3×重复 5、per_repeat_increment）扫描曲线
   像素探针——带色（rgba(37,99,235,.16) 合成后）11,324 px、均值线 630 px，
   aria-label 含「阴影为 95% 置信区间带」；同批发现双语义并排：final_queue_length
   0→1.2 跳变注「置信区间重叠，可能落在重复间噪声范围内」、avg_waiting_time
   69 倍跳变注「置信区间不重叠，跳变显著」、批 #10（fixed 种子，重复全同零方
   差）→ aria「重复次数不足，无置信带」+图下引导文案，控制台零错误。回归：
   后端 245/245、前端 53/53、tsc -b/vite build 干净。
34. **R24 巡检轮：文档对账债 + 插件场景契约真缺陷**（决策见 DECISIONS D48）。
   ① 文档对账：ARCHITECTURE 模型清单补 predator_prey/；API_CONTRACT findings
   契约补 ci_overlap 三态说明。② 真缺陷修复：PLUGINS.md 此前无 scenarios 契约、
   注册表场景校验无测试、前端把 seed/stop_condition 当必填（插件省略即炸）。
   改：ScenarioInfo 两字段可选、scenarioSpec 增 current 表单兜底（非法停止值
   退 steps/1000、种子留空 null）、PLUGINS.md 新增契约小节。新增测试：后端
   test_plugins +3（合法场景透传 list、形状不合 RegistryError、id 重复
   RegistryError）、前端 +1（省略字段兜底与默认）。③ 真插件端到端：临时插件
   r24_demo（场景刻意省略两字段）经 WORLDLAB_PLUGIN_MODULES 载入 → /api/models
   9 模型、场景仅含 id/title/description/params → UI 选模型点场景卡 → 会话
   completed，spec 实测 seed=42、stop=steps/10000（沿用表单值）、count=30000=
   bump3×10000、无错误横幅；验毕删临时插件、关服务器。回归：后端 248/248、
   前端 54/54、tsc -b/vite build 干净。
35. **R25 巡检轮：API 契约逐条实测对齐**（决策见 DECISIONS D49）。对
   API_CONTRACT 每个端点实跑 curl 比对，命中 1 处空头承诺 + 4 处形状漂移：
   ① `GET /api/runs/{id}/events` 契约有、实现无 → 落地实现（`{run_id,total,
   limit,offset,events}`；limit 钳 1..1000、越界 offset 空数组、未知 run 404
   not_found；事件源为落库 events_json，每 run 最近 100 条，total≤100，与会话
   内存 500 条环形日志分属两套口径）。② 会话 snapshot 时间键实为 `time`（非
   sim_time）且另有 `status`。③ 422 detail 实带 `errors[]`。④ result.runs[]
   主键为 `id`（run_id 只在 POST run 202 响应，前端 api.ts 用法本就正确）。
   另补 validate body 裸 spec 形状与 normalized_spec 附加键，标题范围改 R1–R25。
   新增 1 条端点测试（分页/续读差异/钳制/越界/404），实测取证后删除全部探针
   实验（experiments 回到 1–6）。回归：后端 249/249、前端 54/54（未改动）、
   tsc -b/vite build（未改动，R24 基线仍绿）。
36. **R26 巡检轮：基准可复现性 + 行为声称核对**（决策见 DECISIONS D50，零代码
   改动）。① 修 R22 造成的溯源污染：predator_prey 新行曾混进标注 2026-10-28/
   Python 3.11.13 的旧表。现以单次 benchmark.py 运行整体刷新三表（2026-11-05,
   Python 3.12.3, Windows-11-10.0.26200）：queueing ≈266,700、cache_sim
   ≈355,900、CA ≈4,550、schelling ≈288、traffic ≈6,410、sir ≈45,500、
   predator_prey ≈35,700 steps/s；API 单步 p50 0.0/p95 16.0/max 16.0 ms；
   批量 8 项 0.172 s ≈46.5 items/s；并写明「数字须连同日期环境引用，两轮相差
   0–55%、量级与排序不变」，回归阈值表括号内实测值同步。② 声称核对：
   `CHUNK_STEPS=256`、`cancel_poll_interval` 默认 256（引擎 `steps % 256`）、
   前端 running 300ms 轮询 + visibilitychange 补偿——均与代码一致。③ 机制
   失真纠正：契约与 D16 称 running 读取为「≤100ms 节流」，实现是**分片边界
   缓存快照**；实测 CA 64×64 运行中 40ms 连读 6 次得 `[0,256,256,256,512,512]`
   （相邻重复、不同值皆 256 倍数）→ 契约已按实改写，D16 原文保留由 D50 记录
   纠正。探针会话已删。回归沿用 R25 基线：后端 249/249、前端 54/54（本轮无代码改动）。
37. **R27 巡检轮：检查点形状对账 + 绑定拒绝补测 + restore 语义入契约**（决策见
   DECISIONS D51）。① ARCHITECTURE 检查点形状自 R1 起未更新（旧写
   `{step, clock, model_state, event_queue, rng_state}`），实现实为
   `{engine_version, model_id, model_version, model_type, params_digest, step,
   clock, status, rng, model_state, engine}`（DES `engine={queue,seq}`、时间步进
   `{}`），已按实重写并补「JSON 往返=深拷贝+可序列化校验」的用意；核实
   `deque(maxlen=500)` 事件环与文档一致。② 补测安全机制：`restore()` 的四项指纹
   校验（model_id/engine_version/model_version/params_digest → SimulationError）
   此前零覆盖 → 新增 `test_checkpoint_binding_rejects_mismatch`（逐字段篡改验四路
   拒绝 + 正常恢复对照），test_engines 17→18。③ API 层实测：restore 对四类错配
   一律 409 `conflict`（无 500），message 指明具体项；有效恢复后 status 沿用检查点
   当时值（单步后检查点 → `paused`）；契约原只写「→ SessionState」，现写明拒绝
   条件与状态语义。探针会话已删。回归：后端 **250/250**、前端 54/54（无前端改动）。
38. **R28 巡检轮：导出链路落实 + 端到端八模型覆盖**（决策见 DECISIONS D52）。
   ① `reporting.py`/批量 CSV 审计：报告全部取自库内已记录数据（metrics 通用转储，
   第八模型自动被报告覆盖）、CSV 逐 item 明细含 params/metrics JSON 列 + BOM，
   与契约一致；报告 JSON 真实键集此前不成文，已补入 API_CONTRACT（并说明
   `report_version` 仅为结构版本标签、无版本协商）。② 补真覆盖缺口：
   `test_e2e.BUILTIN_MODELS` 自 R10 起只有 4 个模型，schelling/traffic/sir/
   predator_prey 从未被端到端断言 → 新增 `test_every_builtin_model_full_chain`
   （八模型逐个：建实验 → wait 运行 → completed + 非空 metrics + result_sha256 →
   报告 markdown 200/text-markdown/含 model_id → 报告 json `report_version=1`
   且 metrics 与运行一致），步数按成本分档（schelling 20、queueing 500）整套
   秒级；`BUILTIN_MODELS` 扩到 8。回归：后端 **258/258**（+8 参数化）、
   前端 54/54（无前端改动）。
39. **R29 巡检轮：上限单一事实源 + 文档数量级纠正**（决策见 DECISIONS D53）。
   ① 新增 `GET /api/limits`（值取自 `CreateBatchBody` 的 pydantic 约束元数据 +
   `MAX_BATCH_ITEMS` + Settings，无第二份常量），BatchPanel 消费：重复数输入框
   min/max、提交禁用、红字具体原因（纯函数 `batchSubmitProblem`，拉取失败回落
   FALLBACK）。修掉此前漂移：前端只知 2000 上限、完全不知 repeats≤100 与
   name≤200 → 填 150 会放行到后端 422。② 测试绑定两端：后端断言
   `max_items==MAX_BATCH_ITEMS`、`repeats_max+1` 被 422 拒而 `repeats_max` 不被
   重复数规则拒；前端 +2 用例（重复数越界/超容量/空名/超长名/合法通过）。③
   BENCHMARKS 已知限制中「`Limits.max_steps` 默认 100,000 步」为失真数字，实际
   `Settings.default_max_steps` 默认 **1,000,000**（批量/会话/实验同取），已改。
   ④ 浏览器实测：repeats=150 → 提示「每组重复需在 1–100 之间（当前 150）」且
   按钮 disabled；改回 3 → 提示消失、按钮可用；控制台零错误。回归：后端
   **259/259**、前端 **56/56**、tsc -b/vite build 干净。
40. **R30 巡检轮：README 命令实跑 + 422 双形状缺陷 + Docker 生产复验**（决策见 D54）。
   ① 入门命令逐条真跑通过：`uv sync`、`uv run pytest`（260 项）、`uv run uvicorn`
   （health ok、/docs 200、openapi 31 路径含 `/api/limits`）、`npm run dev|test|build`
   （脚本名与 package.json 一致）。修 README 四处计数/清单漂移：四模型→八、
   21→23 个测试文件、六模型正确性→八并补 SIR/LV 描述、Docker 段落改成本轮实测口径；
   环境变量清单补齐 `WORLDLAB_EVENT_LOG_SIZE`(500)/`WORLDLAB_PLUGIN_MODULES`。
   工具事实：`pyproject.toml` `addopts="-q"` 再叠加命令行 `-q` = `-qq` 会吞掉通过计数行，
   需 `-o addopts=""` 才打印「260 passed」。
   ② **修一处可用性真缺陷**：422 `detail` 有对象形状（应用层 spec 校验）与**数组形状**
   （FastAPI 请求体规则：repeats/max_retries/concurrency/name 长度）两种，`api.ts` 只读
   对象形状 → 数组形状横幅退化成裸「422」。UI 可达路径实证：「失败重试」自由文本填 15
   → 后端数组 422 → 横幅无原因。修：纯函数 `errorDetailMessage()` 还原两种形状 +
   BatchPanel 消费 `/api/limits` 早已导出的 `max_retries_min/max`（输入框 min/max、
   提交禁用、红字原因）。浏览器实测：填 15 → 提示「失败重试需在 0–10 之间（当前 15）」
   且按钮 disabled；页面内 import 真实模块对**活后端**返回的数组 422 调 formatter 得
   「422: max_retries Input should be less than or equal to 10」，对象形状得
   「spec validation failed: params.servers Input should be greater than or equal to 1」。
   后端新增 `test_422_has_two_distinct_detail_shapes` 把两种形状钉成契约；前端 +3 组用例。
   ③ 契约补写两端点形状不对称：批量列表 `done_items`（含 step_limit/wall_timeout 非成功
   终态）vs 详情 `counts` 分桶。④ Docker 生产形态复验（R15 后首次、R25–R29 新增面纳入）：
   `compose build/up` 成功且 healthy，经 **nginx 反代 5173** 实测 health、八模型目录、
   predator_prey 三场景带 seed/stop_condition、`/api/limits`、实验→运行→指标+sha
   （K=8：`equilibrium_prey=5.0` 与解析真值 γ/(δβ) 逐位一致、`distance_to_equilibrium=0.0`）、
   `runs/{id}/events`（total=100、未知 run 404）、报告 md/json 键集、批量→终态→findings→
   `export.csv`（12 列 + BOM）、repeats=101 → 422；改动后前端镜像重建通过（容器内 `npm ci`
   + tsc/vite）。⑤ `.gitignore` 补 `pytest-of-*/`（README 的命令会生成该目录污染 status）。
   回归：后端 **260/260**、前端 **60/60**、tsc -b/vite build 干净。

41. **R31 巡检轮：写死清单根治 + 文档一致性锁 + 基准口径修正**（决策见 DECISIONS D55）。
    ① `registry.builtin_ids()` 成为内置模型清单唯一事实源；`test_e2e`、`test_scenarios`、
    `scripts/benchmark.py` 改为派生，基准脚本对「注册了但没配 `BENCH_STEPS`」直接 SystemExit，
    e2e 加步数预算覆盖测试。② 新增 `tests/test_docs_consistency.py` 7 项：README 模型表/计数
    措辞/测试文件数、BENCHMARKS 模型覆盖、OpenAPI 端点逐个进契约、契约不承诺不存在的端点。
    **锁的有效性经六路注入验证**（把端点从契约改名、往契约加虚构端点、改错计数、改错措辞、
    改错表名、删基准行，全部变红）。落地即抓到 README「23 个测试文件」→ 24。
    ③ 修基准假数字：耗时 <1ms 时 `per_second` 报 None（`measurable:false`），不再报 0.0
    steps/s；cpu_scheduling 早停（400 步/队列排空）实测该路径，BENCHMARKS 记口径。
    ④ axe-core 4.10.2 复扫 R22 新视图与 R29/R30 新输入：空态 / 捕食者-猎物运行态 /
    批量面板展开三态各 **0 违规**，两张 canvas 有 `role=img` + 中文 aria-label。
    ⑤ README R 段逐字外迁 `docs/CHANGELOG.md`（脚本自检内容完整），README 变短 3,190 字符。
    ⑥ 新增 GitHub Actions 门禁（后端 pytest + 前端 vitest/tsc/vite build）。
    首跑已核验（run 42019027707）：后端 job **270 passed / 22.5 s**（ubuntu-latest、`uv sync --frozen` 装的 CPython 3.12.16），前端 job 60 项 + `tsc -b`/vite build 通过——这是本项目**第一次**在 Linux 上跑通整套测试。
    回归：后端 **270/270**、前端 **60/60**、tsc -b/vite build 干净。

42. **R32 巡检轮：多版本模型的真实缺口（能力宣称 vs 单例实现）**（决策见 DECISIONS D56）。
    探针法：临时插件把 SIR 复制成 2.0.0/10.0.0 两个版本挂进注册表，真起 uvicorn 打真接口。
    ① 缺陷三处：版本号按字符串排序（`['1.0.0','10.0.0','2.0.0']`）；`registry.get()` 的
    「最新」= 字符串 max → 选 `2.0.0` 而真实最新是 `10.0.0`（运行静默用错版本）；
    `/api/models` 一版一条（3 张同 id 卡片）、`/api/models/{id}` 返回**最旧**版本
    （1.0.0）—— advertised schema ≠ 实际执行版本。② 修：`registry.version_key()` 数字组分
    比较（非数字段视作 0，注释写明不做完整 semver 预发布序），`get/versions_of/list` 统一；
    目录改「每 id 一条（最新）+ `versions`」，`/api/models/{id}` 默认最新 + `?version=` 指定，
    未知 id / 未知版本一律 404（后者 message 带 `available: [...]`）。③ 前端 `ModelInfo`
    加 `versions` 后 tsc 立即抓到测试夹具缺键——契约类型与后端形状绑在一起的价值当场体现。
    ④ 新增 `test_model_versions.py` 5 项（夹具在测后从全局注册表摘掉探针模型，避免污染
    其他用例）；改后同一探针复核：目录 8 条、`sir` 详情 10.0.0、运行 `model_version` 10.0.0
    三者一致，`?version=1.0.0` 取到旧版 Schema，`?version=9.9.9` 返回 available 清单；
    浏览器复跑：模型下拉 8 项无重复、SIR 一键场景到 completed。
    回归：后端 **275/275**、前端 **60/60**、tsc -b/vite build 干净。

43. **R32 收口审计（目标：「分析拓展并完善项目，直到没有能拓展和开发的新任务为止」）**。
    逐维度给结论与证据，不做无证据的「应该没问题」：
    ① **声称 vs 实现**（R24–R32 累计扫过并修）：API 契约逐端点（双向锁进测试）、文档计数与
    模型表（7 项一致性测试 + 六路注入验证）、检查点形状与四项指纹拒绝、导出链路 md/json/csv、
    插件场景契约、基准可复现性与「0.0 steps/s」假数、统计 CI 三态与零宽区间、
    版本化模型的多版本真实行为。本轮再补查三个此前没单独验过的资源类声称：
    `sim_time` 停止条件（`test_engines.py:223`）、零延迟事件链上限
    （`test_des_zero_delay_chain_limit`）、批量在途上限——实现是
    `min(concurrency, max_workers)` 在建批时写入 DB，运行线程池本身又以
    `settings.max_workers` 为上限，故「在途不超上限」由构造保证（非仅约定），
    `test_integrity.py::test_batch_concurrency_bounded_per_batch` 实测绑定。
    ② **测试与门禁**：后端 275 项 + 前端 60 项 + tsc/vite 干净；GitHub Actions 双 job
    在 ubuntu-latest 连续绿（R31 run 42019420098、R32 run 42021854641）。
    ③ **生产形态**：R32 代码重新 `compose build/up` 并复跑全套链路（八模型目录、nginx 反代、
    limits、实验→运行→指标+sha、events 分页与 404、报告键集、批量→findings→CSV 12 列+BOM、
    请求体越界 422）；predator_prey 的 `result_sha256` 与 R30 **逐位一致**
    （b62e6d59cb307616…）→ 跨镜像重建的确定性成立。
    ④ **无障碍/入口质量**：axe-core 三态 0 违规（含 R22 相平面图与 R29/R30 数字输入）、
    meta description 在位、README 已从 7,835 字符瘦身到约 4,700 并把 R 日志外迁。
    ⑤ **内容型拓展（有意不做）**：再加第 9 个内置模型属课设内容偏好，不是能力缺口——
    加模型的成本已经是「一个包 + 一行 import」，且有 `registry.builtin_ids()` 派生清单 +
    文档一致性测试兜住漏测/漏写。
    ⑥ **其余候选及拒绝理由**：WebSocket 实时推送（REST + 轮询是 D 记录在案的取舍，R12 已清除
    失实声明）；鉴权/多用户（单机 SQLite 课设范围，已写入「已知限制」）；模型版本下拉 UI
    （沿用 D38 的 API-only 先例，`?version=` 已可用）；semver 预发布全序（项目内版本号只有
    数字点分，`version_key` 注释写明边界）；给 8 个视图统一加可见图标题（现设计是 aria-label +
    下方数据行，改动需一致覆盖 8 处，属 UI 改版而非缺陷）；CI 加 Windows 矩阵或性能基准 job
    （Linux 单跑已能捕获断链，双平台翻倍 runner 用量而收益边际）。
    结论：能力、正确性、可复现、文档、门禁、生产形态六个维度上，已无「已知可做且不靠猜」的项；
    剩余全是内容扩充或范围外偏好，需要用户点名才动。

44. **R33 巡检轮：多版本执行路径 + normalized_spec 落实**（决策见 DECISIONS D57）。
    ① 探针法（同 `model_id` 临时注册两版，γ 默认值与上限不同好让「用了哪版」可观测）：
    `spec.model_version` 真实决定校验与执行——γ=3.0 在 1.0.0 被拒 / 2.0.0 通过；
    同参跑出的 `peak_infected` 303.9 vs 10.0；批量与实验记录 `model_version=1.0.0`；
    钉未知版本 → 422 `spec_invalid` + `errors[].code="unknown_model"`（**不是 500**）。
    ② 真缺陷：`validate` 的 `normalized_spec` 承诺「迁移补齐后的形态」，实测 `model_version`
    与 `display_name` 恒 None、`params` 不含默认值（`validate_spec_only` 直接 dump 入参）。
    修为解析后的版本 + 注册表显示名 + 套默认值的 params；不动 DB 里存的 spec 原文
    （避免改变 params_digest 与检查点指纹语义）。
    ③ 新增 4 项回归：`test_api.py::test_validate_returns_effective_spec`、
    `test_api.py::test_unknown_model_version_is_422_not_500`、
    `test_model_versions.py::test_pinned_version_selects_which_schema_validates`、
    `::test_pinned_version_changes_actual_execution`（含未钉版本解析到数值最新）。
    ④ API_CONTRACT 的 validate 条目与「model_version 有实际效力」段、README 可比性条目按实补写。
    回归：后端 **279/279**、前端 **60/60**、tsc -b/vite build 干净。

45. **R34 巡检轮：批量透明度 + 网格边界成文**（决策见 DECISIONS D58）。
    ① 探针一（`schema_version` 七种形态）：省略/=1 通过并落 1；=0 → `migration_error`
    （v0 需 `model`）；=2/99 → `schema_too_new` 422；字符串 → 类型错；=-1 → `migration_missing`。
    复核确认 `tests/test_schema.py` 已覆盖迁移与 too_new（**我先前一句 `grep | head -12` 截断
    导致的"缺测"判断是误读，已纠正**——巡检自己的检索也要防截断）。
    ② 探针二（`grid` 键边界）：拼错键 / 点号嵌套键 / 空列表 / 未知顶层字段 → 全部 422
    `spec_invalid`，`code:"grid"` 且 message 列出具体键名；行为对但从未成文与绑定 →
    API_CONTRACT 补写「只支持顶层参数名，不支持点号路径」+ 2 项后端测试；
    批量面板同步加该边界提示。
    ③ 真缺陷（会误导结论）：面板一次取 50 项、表头只写「前 50 项」不写总数 →
    新增 `itemsHeading(shown,total)`，60 项批次实测文案为「单项结果（显示前 50 / 共 60 项，
    其余见「导出 CSV」）」，且实测该 CSV 恰含 60 行数据（导出 500/页循环取全量）。
    ④ 自我缺陷并当场由渲染证据纠正：提示文案用了 markdown `**…**`，JSX 原样显示星号 → 改 `<strong>`。
    **守则：文案是否成立只能以浏览器 DOM 为准，不能以源码为准。**
    ⑤ 新增 `items` offset 分页稳定性测试（同序、total 不变、不重不漏）。
    回归：后端 **281/281**、前端 **62/62**、tsc -b/vite build 干净。

47. **R35 巡检轮：孤儿模型实验的校验一致性与诊断口径**（决策见 DECISIONS D59）。
    ① 会话竞态探针：并发 6 路 `/step` 得到步数 1..6 各一次（无重复无 500）；
    `run→pause→step` 停在 257 步、1.2s 后不自走；`reset` → `idle`/step 0；
    运行中 `DELETE` 会话 → 204 → 列表无 → GET 404。状态机无需改动（阴性结论也记录）。
    ② 实验列表 `model_id`+`tag` AND、`total` 随过滤、未知 tag 空集、`offset` 不重叠——
    行为正确但无测试 → `test_experiment_list_filters_combine_and_total_follows_filter`。
    ③ **缺陷一**：孤儿实验（模型注册表里已无，如插件模块未载入）`run`/`rerun` 先 200 queued、
    再由 worker 把 run 标 failed；`create`/`clone`/建批同 spec 却 422。修复为提交时
    `validate_spec`（位于状态改写之前）。线上复验：读路径 200、`run`/`rerun`/`clone` 422
    `unknown_model`、实验仍 `created`；新增 `test_run_rejects_unregistered_model_at_submit_time`。
    ④ **缺陷二**：`run.error` 含 `Traceback` 与本机绝对路径并会进导出报告；抽
    `describe_run_failure()`——`SpecValidationError`/`RegistryError`/`SimulationError` 只留一行
    `类型: 原因`，其它保留 3 层栈；测试断言前者无换行无路径、后者仍含定位信息。
    ⑤ 契约纠偏：`POST /experiments/{id}/run` 是 **200 `{experiment_id, run_id, status}`**
    （原文写 202 + `runs:[…]`）；补 error 口径与提交时校验；README 加「插件卸载不吞历史」。
    ⑥ 孤儿实验读/报告能力另绑测试（`test_orphan_experiment_is_still_readable`）。
    ⑦ 卫生：删除 R33 探针遗留在 dev 库的 18 条孤儿实验。
    回归：后端 **285/285**、前端 **62/62**、tsc -b/vite build 干净。

48. **R36 巡检轮：ARCHITECTURE/PLUGINS 深审 + 文档锁扩展七项**（决策见 DECISIONS D60）。
    ① 逐句核账抓到 9 处失真：`core/schema/migrations.py`、`services/run_worker.py` 两个幻影文件；
    `Limits.max_events` 幻影字段；ModelSpec 的 `model_type` 字段不存在；「pydantic v1」应为 v2、
    `MIGRATIONS`/`load_spec` 应为 `register_migration`/`upgrade_spec`；「取消标志=DB 状态」
    实为进程内 `threading.Event`（每 `cancel_poll_interval` 步检查）；`/api/.../steps` 实为 `/step`；
    「比较 API 返回 cross_version 警告」全仓无此名（实际由 `ComparePanel.tsx` 提示 + 报告
    `comparability_note` 声明）；`result_artifacts` 建表但无写入方，旧文当能力写。
    ② ARCHITECTURE 重写：文件清单改为**从磁盘生成**的逐路径块（含关键文件一句话说明），
    Limits/停止条件/RunResult 状态、ModelSpec 真实字段、表与写入方、执行模型（三服务各持
    ThreadPoolExecutor、批量在途 `min(concurrency, max_workers)`）、可视化 kind 与
    `StateTable` 兜底、registry 唯一事实源口径全部按实写明。
    ③ 锁扩展 7 项：清单↔磁盘双向、`Limits` 字段名、表集合↔迁移 + 死表必须标注、
    PLUGINS kind 清单↔`SimView` 分发、架构文档 `/api/` 字面量↔OpenAPI（含裸写法与
    「匹配数过少即失败」的防空锁 guard）、`cross_version` 不得再被宣称。
    ④ 有效性验证：八路注入全部变红（幻影文件、漏写文件、max_events 回归、表名改错、
    死表谎报、kind 漏写、kind 虚构、端点写成复数 / 裸路径改名）。
    ⑤ PLUGINS.md：`visualizer.series` 改口径为「只是元数据，前端不读取」。
    回归：后端 **292/292**、前端 **62/62**、tsc -b/vite build 干净。

49. **R37 巡检轮：配置→行为一致性（会话 Limits 漏传）+ 环境变量锁 + 生产复验**。
    ① 缺陷：`SessionService.create()` 只给 `Limits` 传 `max_steps`/`max_wall_seconds`，
    `zero_delay_chain_limit`/`cancel_poll_interval` 退回 dataclass 默认 →
    `WORLDLAB_CANCEL_POLL_INTERVAL`、`WORLDLAB_ZERO_DELAY_CHAIN_LIMIT` 对交互会话静默无效，
    而 `GET /api/limits` 报的是 Settings 值。实测 Settings=7/99 时会话引擎仍为 256/10000。
    修：`session_limits()` 四项全取 Settings；`test_session_limits_come_from_settings` 绑定
    （含引擎实例上的实际值）。
    ② 新锁 3 项：README 环境变量清单↔`config.py`（双向，R30 漏写病灶）、
    清单默认值↔代码默认值（R29 数量级病灶）、三服务每个 `Limits(` 构造四字段齐全；
    **用修复前的 `session_service.py` 验证第三条锁能准确报出缺失字段**。四路注入验证前两条会红
    （漏写变量、多写假变量、默认值改 64、步数上限改一个数量级）。
    ③ 文档纠正：BENCHMARKS「会话不受 default_max_steps 约束」为假（累计上限就是它，
    分片只是每次 256 步）；README 资源有界条目重写并去掉前端用例硬编码数；ARCHITECTURE
    后台执行段补三路径一致性。
    ④ 生产形态复验（重建 api 镜像后）：15 项 API 链路全绿；会话生命周期经 nginx 反代实测
    restore 逐位一致 `(300, 165.1952)`、续步 310、错配 409、delete 204→GET 404；
    容器内 env 覆盖 9/77 抵达会话 Limits。
    回归：后端 **296/296**、前端 **62/62**、tsc -b/vite build 干净。

50. **R38 巡检轮：基准归属与表内自洽锁**。① 环境块错误归属：文档写 Python 3.12.3，
    而实际/README 记录的命令 `uv run python scripts/benchmark.py` 用 venv 的 3.11.13
    ——「同一次运行」原则失去可判定性。改为抄录脚本自身打印的 environment
    （解释器 3.11.13、平台 Windows-10-10.0.26200-SP0、CPU Intel64 Family 6 Model 183、
    app 0.1.0/引擎 1.0），并注明系统 3.12.3 属另一机位。
    ② 三张表按 R38 单次运行刷新（7 行引擎吞吐、API p50 0/p95 16/max 31 ms、批量 8 项
    0.203 s ≈39.41 items/s）；跨轮差异说明改为 R26↔R38 的 0–80% 并强调只用
    量级与相对排序；回归阈值表括注改为引用上表同行（原来拿 5 万步测试值冒充 10 万步）。
    ③ 新锁：行内 steps/seconds 与吞吐 3% 内自洽、批量 items/seconds 自洽、
    p50≤p95≤max、环境块必须含解释器版本与命令归属；五路注入验证会红
    （混入他轮 8% 数字、只改耗时、批量数不自洽、max<p95、缺解释器）。
    回归：后端 **297/297**、前端 **62/62**、tsc -b/vite build 干净。

51. **R39 巡检轮：会话「暂停=取消」的 P0 语义缺陷 + 引擎所有权交接 + 可配置 TTL**。
    ① **实跑抓到的产品级缺陷**：HTTP 探针（toy_slow_step 运行 0.25 s 后 `POST /pause`）
    显示会话落 `cancelled` 终态，`resume`/`step` 一律 409「session already finished」，
    只有「重置」能继续而重置会清空进度——即工作台主打的「播放 → 暂停 → 继续」在浏览器里
    从未走通。根因：`_stop_thread()` 无条件同时置 `cancel_event` 和 `pause_event`，
    `_run_loop` 先查 cancel。修复：停止入口按意图分派（`cancel=False` 给 pause/reset/restore，
    `cancel=True` 给 delete/TTL 回收/shutdown），暂停落 `paused`、可继续可单步。
    ② **旧测试为什么没抓到**：`test_session_pause_and_resume` 的等待集合是
    `{paused, completed}`，运行在暂停前就自然完成，于是永远走 completed 分支。把代码
    注入回旧行为后这条测试**也变红**，证明它此前未真正执行暂停路径——这是本轮最有价值的
    元信息：绿色测试集 + 在册的「暂停恢复 E2E」条目，仍然掩住了一个从阶段 2 就存在的缺陷。
    ③ **引擎所有权交接**：join 超时后不得再动 engine。新增 `stopping` 标志 +
    `_finish_run()` 单锁交接；`step/run/checkpoint` 报 409「session is stopping…」、
    `reset/restore` 报 409「session is still stopping; retry in a moment」。
    两条新测试用 gate 把 worker 卡在分片内部（不靠 sleep 赌时序），断言五个入口全部拒绝、
    且 `engine.steps` 在分片结束前保持 0；`git` 反证（还原 reset/restore）使
    `DID NOT RAISE ConflictError` 精确复现旧行为。
    ④ **TTL 可配置**：会话空闲回收从硬编码 3600 秒改为 `WORLDLAB_SESSION_TTL_SECONDS`
    （默认 3600），测试覆盖默认值、env 覆盖（12.5）与到期回收/未到期不误回收。
    ⑤ **新文档锁**：`test_every_decision_reference_points_to_a_real_row` 校验全部文档的
    「见 D5x」指针命中 DECISIONS 真实行；注入一个不存在的编号即变红。
    ⑥ **间歇性 Windows 崩溃取证**：`tests/test_sessions.py` 在本机三次连跑出现
    faulthandler「Windows fatal exception: access violation」2/2/0 次（测试结果始终
    16 passed），栈帧散落在 `tempfile`、`typing`、anyio `queue.get`、`random.expovariate`
    等互不相关位置；Linux CI 三个后端 job 日志 0 次。按环境噪音记入 BENCHMARKS 已知限制，
    不宣称已归因，也不据此声称修掉了它。
    回归：后端 **302/302**、前端 **62/62**、tsc -b/vite build 干净。

52. **R40 巡检轮：控制端点的等待语义（pause/reset/delete 不再阻塞分片）**。
    ① 起点是 R39 引入的 join：`pause` 最多等 5 s。实测参数上限 256×256 元胞自动机的
    256 步分片 **4.28 s**——暂停请求会挂住近 5 秒后仍返回「运行中」；`reset` 超时回 409
    要求重试；`DELETE`/TTL 回收在请求里同步等别人的分片（TTL 回收挂在任意会话操作上，
    会拖慢无关请求）。
    ② 改为边界交接：`pause` 置标志立即返回；运行中 `reset` 排队到 `pending_action`，
    由 worker 在边界执行；`DELETE` 先摘除再置 cancel；`restore` 保留同步 409。
    `_finish_run()` 统一做「落状态 + 清 stopping + 执行排队动作 + 清缓存快照」，一次加锁完成，
    同时堵住 R39 的 409 误报窗口与「排队后 worker 恰好退出 → 重置被吞」的孤儿动作。
    ③ 测试：`test_session_reset_while_running` 断言调用 <0.5 s 且随后 idle/step 0；
    两个 gate 测试改为断言「运行中 reset = 200 + 排队」「engine.steps 在分片结束前为 0」；
    e2e 的 pause 改轮询（旧断言依赖阻塞语义）。反证：把 `_finish_run` 的排队分支删掉，
    gate 测试会停在 `running` 且 step 不回 0。
    ④ 契约成文（API_CONTRACT/ARCHITECTURE）：`pause`/`reset` 的响应是交接前状态，
    最终状态经 `GET /api/sessions/{id}` 在 ≤1 个分片内到达；前端 300 ms 轮询无需改动。
    ⑤ 真实网络栈复验（补 TestClient 不经 TCP 的口径缺口）：uvicorn + curl 打
    256×256 元胞自动机会话，`POST /pause` 返回 **HTTP 200 / 64 ms**（`time_total`）且
    响应体仍是 `running`，随后轮询到 `paused`（step 256）约 **2.2 s**；与浏览器内测得的
    211 ms / 1.44 s 同量级（差异来自分片起点不同，不是实现差异）。
    ⑥ 同轮的负结果（如实记录）：取消后的批量在 `GET /batches/{id}`、`/items`、`/findings`、
    `/export.csv` 上全部 200，状态 `cancelled`、计数 `{cancelled:5, step_limit:1}`，
    没有发现缺陷——本轮没有为此改动任何代码。
    回归：后端 **302/302**、前端 **62/62**、tsc -b/vite build 干净。

53. **R42 生产形态复验：会话控制语义在容器内复核（R39/R40 之后）**。
    ① 重新 `docker compose up -d --build`（api 镜像含最新代码，web 经 nginx 反代
    `/api/` → `api:8000`），全部请求走 `http://localhost:5173/api/...`。
    ② 256×256 元胞自动机：`POST /pause` **200 / 31.9 ms**，响应体 `running`；轮询到
    `paused`（step 256）。`POST /reset` **200 / 37.7 ms**，随后落 `idle`（step 0）；
    再 `POST /step {n:3}` 得 `paused`（step 3）；`DELETE` 204。与本地 uvicorn/浏览器
    测得的量级一致，说明边界交接语义不依赖运行方式。
    ③ 配置抵达：一次性容器 `-e WORLDLAB_SESSION_TTL_SECONDS=12.5` 下
    `Settings.from_env().session_ttl_seconds == 12.5`（默认 3600）。
    ④ 重启语义：运行中的实验在 `docker compose restart api` 后变为
    `failed | interrupted: service restarted while run was in progress`；
    `GET /api/sessions` 返回空列表（会话是内存态，文档已声明重启即失）。
    ⑤ 负结果：本轮未发现缺陷，未改动任何产品代码；探针实验已从容器库删除，
    compose 栈已 `down`（保留数据卷）。

54. **R43 批量并发取消的聚合口径（8 并发 / 16 项 / 真实中途取消）**。
    ① 探针：toy_slow_step 每项 20 万步，`concurrency=8`（服务端 max_workers=2 → 生效 2），
    0.45 s 后取消；终态 `cancelled`、`counts={cancelled:16}`、无 pending/running、
    `items.total=16`、`export.csv` 数据行 16（前 3 行是导出头注释，`rows==total+1` 的
    朴素断言是错的）、`findings` 200——**聚合无缺陷**。
    ② 同轮暴露的透明度缺口：建批时 `concurrency` 与 `per_run_wall_seconds` 会被
    服务端上限钳制后落库（响应回显的是生效值），但契约只在取消端点旁提过并发上限，
    创建条目没有说明。补契约两行公式，新增 `test_batch_records_effective_limits_not_requested`
    （请求 64/3600 → 记录 2/60，服务层与详情两头断言）。
    ③ 本轮无产品代码改动；探针文件已删。
    回归：后端 **303/303**、前端 **62/62**（无前端改动）。

55. **R44 工作台可访问性实测（对比度 / 可访问名 / 焦点 / live region）**。
    ① 对比度：遍历 525 个含文本节点（含展开后的批量面板），按 WCAG 计算前景与最近
    不透明祖先背景的对比度——**0 处**低于 4.5:1（大字 3:1）。
    ② 可访问名：81 个可聚焦控件（button/input/select/textarea）全部能解析出名字，
    无正向 tabindex，无 `outline:none`（全项目无 CSS 文件，样式内联）。
    ③ 焦点：**必须用真实按键**验证。程序化 `el.focus()` 在 Chromium 下不匹配
    `:focus-visible`，我第一版探针因此得到「77/77 控件无焦点环」的**假阳性**；改用
    browser-use 真实 `Tab` 后，`document.activeElement` 的 `:focus-visible=true`、
    `outline: auto 1px`。记录此坑：焦点样式不能用脚本 focus 判定。
    ④ **真缺陷**：异步状态无 live region。修后实测：创建会话 → 运行，
    `[role=status]` 文本为「状态 运行中」；点暂停并等待落地 → 「状态 已暂停」，
    同时暂停禁用、恢复可用；把步数设成 2000000 触发 422 → `[role=alert]` 出现
    并带后端消息。
    ⑤ 回归：前端 **62/62**、tsc -b/vite build 干净；后端未改动（303/303 沿用）。

56. **R45 界面状态值统一中文化**。
    ① 盘点：会话状态已本地化，但实验历史（App）、批量列表 / 详情 / 单项（BatchPanel）、
    比较面板（ComparePanel）共 5 处直接渲染后端英文枚举；`statusLabel` 还缺
    `created/queued/pending/failed` 四个枚举（会原样漏出英文）。
    ② 修：抽出 `frontend/src/labels.ts`（未知值原样返回，避免静默吞掉新状态），
    五处改为调用；`labels.ts` 同步写入 ARCHITECTURE 清单，文档锁的双向校验通过。
    ③ 单测：`statusLabel` 新增 queued/pending/failed/created 四条断言（前端 62/62）。
    ④ 浏览器实测：展开批量面板后，`main td` 中英文状态值的集合为空；实验历史、批量列表、
    批量详情头部 `<strong role=status>` 均为「已完成」。比较面板行未单独打开验证
    （与其余四处同一函数，由单测覆盖）。

57. **R46 错误提示可读性（字段校验消息 + 孤儿配置载入）**。
    ① 实测路径：步数填 2000000 → 横幅 `错误：422: n Input should be less than or equal to 1000000`；
    载入模型已移除的历史实验（如 mrp_probe）→ 只提示「已载入配置」，点运行时才吃英文 422。
    ② 修 `errorDetailMessage`：字段名映射（n/repeats/name/max_retries/concurrency/
    per_run_wall_seconds）+ 九类常见 pydantic 消息；**全部可识别才输出中文**，否则整条回退原文
    （带状态码），避免中英混排；对象形状的已知顶层 code 中文化。
    ③ 载入历史配置时对比 `/api/models`：模型不在目录中则提示「配置可查看，运行会被拒绝」；
    目录拉取失败（列表为空）时不误报。
    ④ 浏览器实测：单步越界 → `错误：步数 不能大于 1000000`；载入孤儿实验 → 新提示文案；
    用孤儿 spec 创建 → `错误：参数校验失败：unknown_model unknown model_id: 'mrp_probe'`。
    ⑤ 单测：`errorDetailMessage` 新增步数上限、`Field required`、不可识别回退三组断言
    （前端 **63/63**）；tsc/vite 干净。

58. **R47 会话单步上限单一事实源（/api/limits → 表单拦截）**。
    ① 缺陷：`step(n)` 的上限 1,000,000 只存在于后端校验，`/api/limits` 未导出，前端只能
    把越界值发出去吃 422（R46 只是把错误文案变可读）。
    ② 修：常量 `session_service.MAX_STEP_BATCH` 同时供校验与 `GET /api/limits` 使用，
    返回 `session:{max_step_batch}`；`test_limits_endpoint_tracks_validation_rules` 断言
    端点值与常量一致（两端绑定，不会各写一份）。
    ③ 前端：步数输入 `min=1 max=max_step_batch`，越界时红字提示 + `aria-invalid` +
    禁用「单步」；纯函数 `stepProblem()` 覆盖空值/0/负数/小数/超限（单测 4 组）。
    ④ 浏览器实测：2000000 → 「步数不能超过 1000000」、按钮禁用、`aria-invalid=true`；
    5 → 提示消失、单步成功到 step 5，无 alert。
    ⑤ 回归：后端 **303/303**、前端 **65/65**、tsc -b/vite build 干净。

59. **R48 实验历史截断透明度**。
    ① 缺陷：`refreshHistory()` 固定 `limit=20`，界面不显示总数；开发库实测 **46 条**，
    即真实数据下早已只剩前 20 条被展示且无人知晓。批量面板 R34 已有「显示前 N / 共 M」
    口径，实验历史是同一类漏网。
    ② 修：`historyHeading(shown, total)` 写明截断（「显示最近 20 条 / 共 46 条，更早的未在
    界面列出」），比较面板增加「可选范围：最近 20 条（共 46 条）」提示。
    ③ 单测：`historyHeading` 三种情形（空/全显示/截断），前端 **66/66**。
    ④ 浏览器实测：标题与比较面板提示均按预期渲染（46 条数据）；探针实验 75/74 已删除，
    总数回到 46，未污染开发库。

60. **R49 比较面板上限可见化（不再静默丢点击）**。
    ① 缺陷：`MAX_COMPARE=4`，第 5 次勾选被直接丢弃且无任何提示；按钮文案的「≤4 个」
    是唯一线索，用户会以为勾选失效。
    ② 修：纯函数 `toggleCompare(ids, id, max)`；界面常显「已选 x / 4」，到顶时提示
    「已达上限，取消一个后可再选」并禁用未勾选项（预防优先于报错），取消后立即恢复。
    ③ 单测 5 组（新增/取消/满额拒绝/满额仍可取消已选项），前端 **67/67**。
    ④ 浏览器实测：0/4 全可选 → 选满 4 个后第 5、6 项 disabled、点击后计数仍 4/4 →
    取消一项回到 3/4、全部恢复可选。

61. **R50 会话回收后的恢复路径（轮询吞 404 的修复）**。
    ① 缺陷：会话轮询 `.catch(() => {})` 把 404 吞掉——被 TTL 回收的运行中会话会让界面
    永远停在「运行中」且不再更新；手动操作则显示英文 `session … not found`，死会话不清除。
    ② 修：`ApiError{status, code, path}` + `isSessionGone()`（404 且路径含 `/sessions/`，
    避免删实验的 404 误清会话）；命中后清空会话并给出中文提示，轮询与手动操作都覆盖。
    ③ 浏览器实测：空闲会话 DELETE 后点单步 → 提示 + 面板回到「尚未开始」；
    谢林运行中 DELETE 会话后 1.5 s 内 → 轮询清空 + 提示，界面不再显示「运行中」。
    ④ 单测：`isSessionGone` 四例（会话 404 / 实验 404 / 409 / 普通 Error），前端 **68/68**。

62. **R51 前端空 catch 普查（R50 的同一把尺子）**。
    ① 普查结论：`getLimits` 失败回落、批量轮询瞬时错误继续重试——可容忍（保留 + 注释）；
    两处仍会吞状态：标签页可见性刷新（轮询已停时会话被回收，回页面看到过期画面）、
    批量列表拉取失败（显示成「暂无批量」）。
    ② 修：通用 `isNotFoundOn(e, pathPart)`；可见性刷新走与轮询相同的清空 + 中文提示；
    批量列表失败显示原因；批量轮询 404 提示「批量已不存在」并关闭详情，其余错误继续重试。
    ③ 浏览器实测（可见性路径）：暂停中的会话在服务端删除后触发可见性刷新 →
    会话清空并提示。**环境限制**：内嵌浏览器 `visibilityState` 恒为 `hidden`，直接派发
    `visibilitychange` 会被守卫跳过；改为覆盖该属性后派发同一事件，验证的是处理函数本身。
    ④ 未验证项（如实记录）：批量 404 的界面分支没有在浏览器里走通（批量面板「查看」
    未打开详情），只由 `isNotFoundOn` 单测覆盖；探针批量 #20 已取消并从库中删除（批量回到 19）。
    ⑤ 单测：`isNotFoundOn` 三例，前端 **68/68**、tsc/vite 干净。

63. **R52 补验 R51 的批量分支 + 更正 R44 的 live region 声明**。
    ① 探针定性：R51 中「查看」无反应不是产品缺陷——高级面板是 `<details>`（无
    `aria-expanded`），当时点的是折叠状态下隐藏的按钮；`details.open = true` 后同一按钮
    正常打开详情（批量 #19）。教训：用 `[aria-expanded]` 找原生折叠面板会静默落空，
    且隐藏元素的 `innerText` 为空串，不能当成「渲染缺失」。
    ② 补验 R51 未验证项：运行中的批量 #21 在库中删除后，700 ms 轮询得到 404，详情关闭
    （`setBatch(null)` 生效）。
    ③ **更正 R44**：其 CHANGELOG 声称三处错误横幅都加了 `role="alert"`，实测批量面板
    顶部未加（只加了会话与顶栏两处）；已补并实测批量 #22 删除后点「查看」→
    `[role=alert]` 文本「错误：batch 22 not found」、详情不显示。CHANGELOG R44 原文已就地
    标注更正。
    ④ 探针批量 #21/#22 均已从库中删除（批量回到 19）；前端 tsc/vite 干净。

64. **R53 生产镜像重建 + R44–R52 改动在容器内的核验**。
    ① 背景：镜像最后构建于 R42，其后 R44–R52 的前端改动与 R47 的 `/api/limits` 字段均未进镜像。
    ② `docker compose up -d --build` 后经 nginx 核验：`/api/limits` 含
    `session.max_step_batch=1000000`；打包产物名与本地构建一致（`index-D_pFbmaR.js`），
    bundle 内含五个新文案（步数不能超过 / 会话已被服务端回收 / 最多同时比较 / 显示最近 /
    参数校验失败）。
    ③ 容器页面实测：步数输入 `max=1000000`、越界提示 + 禁用；历史标题「共 3 条」；
    状态与提示位于 `role=status`；非法参数（CA width=3）提交后 `role=alert` 出现，
    文案「参数校验失败：params.width Input should be greater than or equal to 5」。
    ④ 新发现（下一轮处理）：对象形状的 spec 错误只翻译顶层 code，嵌套 pydantic 消息仍为英文，
    与数组形状（R46 已翻译）形成不对称。

65. **R54 对象形状 422 的嵌套消息翻译（与数组形状统一）**。
    ① 缺陷：R46 只覆盖数组形状；对象形状（spec 校验）只译顶层 code，嵌套 pydantic 消息仍英文，
    同一越界在两种入口下语言不同。
    ② 修：`humanizeSpecError()` 处理 `errors[]`：`params.` 前缀去掉、复用同一张消息表，
    规则同样为「全部可识别才译，否则整条回退」。
    ③ 单测：`params.width` + 英文消息 → 「width 不能小于 5」；不可识别的 `params.gamma ≥0`
    整条回退（前端 **69/69**）。
    ④ 浏览器实测：CA 宽度 3 → `错误：参数校验失败：width 不能小于 5`。

66. **R55 插件文档的示例必须真能跑（文档抽取式测试）**。
    ① 缺陷：PLUGINS.md 的示例是 `# ... 实现各方法` 伪代码，而同一文档要求插件附「可运行示例」；
    读者照抄必然缺方法，也看不出契约要求哪五个方法。
    ② 修：示例改为完整实现（五个必需方法 + 可选 `initialize`），并说明每个方法对应什么契约。
    ③ 新测试 `test_documented_plugin_example_is_runnable`：正则抽取文档中带 `register(registry)`
    的代码块 → 写成 `my_plugins/lottery.py` → `load_plugin_modules` 注册进独立 `ModelRegistry`
    → 跑 5 步，断言同 seed 逐位一致、`total=50`、指标键 `{heads, ratio}`。
    ④ 反证：把示例换成伪代码后该测试变红（`assert code` 的文案指明是示例不可运行）；
    还原后全绿。后端 **304/304**。

67. **R56 文档描述的插件启动路径（真实 uvicorn + 环境变量）**。
    ① 从 PLUGINS.md 抽取示例代码块写成 `backend/_r56_plugins/lottery.py`，按文档命令
    `WORLDLAB_PLUGIN_MODULES=_r56_plugins.lottery uvicorn app.main:app` 启动（独立临时库）：
    `GET /api/models` = 9 个（8 内置 + lottery v1.0.0，中文显示名完好）；建会话 + 单步 5 次
    → `completed`，快照 `{heads:22,total:50,ratio:0.44}`、指标 `{heads,ratio}`。
    ② 失败路径：`WORLDLAB_PLUGIN_MODULES=no_such_plugin.module` → 启动即失败（exit 1），
    信息 `plugin module 'no_such_plugin.module' could not be imported: No module named …`，
    与文档声明一致。
    ③ 环境备注：sqlite 库放在 git-bash 的 `/tmp` 下会报 `unable to open database file`，
    探针改用仓库内 `backend/data/` 路径；该库与插件目录跑完即删（工作树干净）。

68. **R57 批量列表截断口径（同一规则覆盖三个列表）**。
    ① 缺陷：`listBatches()` 固定取 10 条，开发库 19 个批量——当前就在静默截断；
    批量面板既无总数也无提示，用户会把 10 行当成全部。
    ② 修：`batchesHeading(shown, total)`（空/全量/截断三种），列表上方常显总数；
    总数取自已返回的 `total`。至此实验历史（R48）、批量列表（R57）、批单项（R34）三处
    截断口径完全一致。
    ③ 单测三例；浏览器实测 19 条数据 → 标题「批量实验（显示最近 10 条 / 共 19 条，
    更早的未在界面列出）」、表格 10 行。前端 **70/70**、tsc/vite 干净。

69. **R58 最终完成审计（逐项对证据）**。
    ① 目标复述：分析并拓展、完善项目，直到「没有能拓展和开发的新任务」。可证伪的验收口径：
    (a) 无已知未修缺陷；(b) 每个已识别候选要么已实现、要么有书面拒绝理由；(c) 门禁与文档一致；
    (d) 开发形态与生产形态都实跑过。
    ② 证据：后端 304/304、前端 70/70、tsc/vite 干净；HEAD 94f4c53 = 远端；CI 绿；
    CHANGELOG R1–R57、DECISIONS D1–D78、TESTING §1–§68；容器内核验见 §64；插件真实启动见 §67。
    ③ 新识别的「有意不做」：界面层删除实验/批量（破坏性操作、无需求、API 已具备）；
    插件热加载（重启是受支持路径，热加载引入模块状态与信任边界问题）。
    ④ 本轮补的文档缺口：PLUGINS 未说明容器内插件需可导入（构建进镜像或挂载 + PYTHONPATH），已补。
    ⑤ 结论：六个维度上无「已知可做且不靠猜」的剩余项；剩余属内容扩充/范围外偏好，需用户点名。

70. **R59 分页参数边界（未校验的 `limit=-1` 等于无上限）**。
    ① 实跑取证：`/api/experiments?limit=-1` → 全部 52 条；`limit=999999` → 全部；
    `offset=-5` 被当 0；会话 `events_limit=0` → 49 条（`[-0:]` 等于 `[0:]`）、
    `events_limit=-1` → 48 条（除第一条外全部）。
    ② 修：experiments/batches/items/runs-events 的 `limit` = `Query(ge=1, le=1000)`、
    `offset` = `Query(ge=0)`；`events_limit` = `Query(ge=0, le=500)`；越界 422。
    `_build_state` 在 `events_limit=0` 时返回空列表；`/api/limits` 新增
    `pagination:{max_limit,max_events}`。
    ③ 新测试：`test_pagination_bounds_are_enforced`（两个列表端点 × 4 个越界值 → 422，
    合法值 200）；`test_session_events_limit_is_validated_and_zero_means_none`（0→空、2→2 条、
    -1/501→422）。
    ④ 实跑复核（重启服务后）：limit=-1/0/999999、offset=-5 → 422；limit=20 → 200；
    events_limit 0/2 → 0/2 条、-1 → 422；`/api/limits.pagination` 呈现。后端 **306/306**。

71. **R60 名称长度上限下沉到服务层（clone 曾绕过）**。
    ① 实跑：直接创建 10000 字符名称 → 422；`clone` 同样名称 → 200 且库中存 10000 字符。
    规则只在路由的 `CreateExperimentBody` 里，服务层没有校验。
    ② 修：`EXPERIMENT_NAME_MAX=200` 同时供路由与服务层；`create_experiment()` 校验长度；
    `/api/limits.experiment.name_max_length` 导出，前端名称输入框据此 `maxLength`。
    ③ 测试：`test_clone_rejects_overlong_name_like_create`（201 → 422；200 → 200）。
    ④ 实跑复核：clone(201)=422、clone(200)=200；limits 呈现 200。探针实验已删。
    ⑤ 回归：后端 **307/307**、前端 **70/70**、tsc/vite 干净。

72. **R61 测试污染真实数据（create_app 未传 settings）**。
    ① 现象：开发库实验数几轮内 46 → 64，而这是测试在写。实测量化：跑一次全量测试，
    `backend/data/worldlab.db` 的 experiments **58 → 61**、runs +3。
    ② 二分定位：`tests/test_model_versions.py` 两个 fixture 用 `TestClient(create_app())`，
    未传 settings → `default_settings` → 仓库开发库；`two_behavioral_versions` 每次建 3 个
    `mrp_probe` 实验。
    ③ 修：fixture 改用 `settings`（tmp 库）；`conftest.py` 会话级 autouse 把
    `app.main.default_settings` 换成临时库（兜住所有「忘了传 settings」的调用）；
    `test_default_app_never_points_at_repo_database` 绑定该保险。
    ④ 复核：全量测试前后 **64 → 64**（修前 58 → 61）。已写入开发库的 51 条 `mrp_probe`
    探针实验按 R35 判据清理（先备份到临时目录），剩 13 条真实数据。后端 **308/308**。

73. **R62 并发 run 占位（TOCTOU：同一实验被并发执行两次）**。
    ① 探针：同实验 8 线程同时 `run_experiment`（schelling 2000 步保持 running）→
    **2 个成功、DB 2 条 run**；根因是先读 status 再无条件 UPDATE+INSERT。
    ② 修：占位改为 `UPDATE … WHERE id=? AND status!='running'`，以 rowcount 判定归属，
    输者 409；写事务由 SQLite 单写者串行化。
    ③ 复核：服务层 8 线程 → ok=1 / conflict=7 / run=1；真实 HTTP 8 并发 curl →
    1×200 + 7×409、run=1；探针实验已 cancel + delete。
    ④ 回归：`test_concurrent_run_claims_exactly_once`（8 线程、断言恰好 1 个成功且 DB 1 条 run）。
    后端 **309/309**。

74. **R63 删除实验的 TOCTOU + worker 静默异常**。
    ① 缺陷：`_assert_not_running` 读完后无条件 `DELETE`；检查与删除之间的窗口里若被
    `POST /run` claim，删除会成功并级联删掉 run 行，worker 仍在跑 → 后台线程抛
    `NotFoundError` 且无人观察。
    ② 修：删除改为 `DELETE … WHERE status!='running'`，rowcount=0 时区分 404/409；
    `_execute_run` 在实验或 run 行消失时安静退出。
    ③ 测试：`test_delete_refuses_when_a_run_claims_between_check_and_delete`（绕过检查函数
    模拟竞态窗口，断言 409 且实验仍在）与 `test_worker_exits_quietly_when_experiment_is_gone`
    （run 行在、实验已删，直接调 `_execute_run` 不抛异常）。
    ④ 反证：把 DELETE 改回无条件，第一条测试变红（AssertionError：运行中的实验不应被删除）；
    还原后全绿。后端 **311/311**。

75. **R64 畸形输入扫描（11 例）与 500 修复**。
    ① 用例：900 层嵌套 checkpoint、spec 为 list/null、grid 值非列表、坏 tag（非 UTF-8）、
    坏 version（ ）、超大 offset 与超大路径 id。
    ② 唯一 500：`offset=999999999999999999999` → SQLite `OverflowError`；路径 id 同理。
    ③ 修：offset `le=1_000_000_000`；路径 id 用 `Annotated[int, Path(ge=1, le=2**63-1)]`；
    `pagination.max_offset` 进 `/api/limits`。
    ④ 复核：11 例全部 < 500（422/404/201）；`test_malformed_inputs_never_leak_500` 常驻。
    后端 **312/312**。

76. **R65 空状态与并发写负载复核（阴性）+ 本周期审计口径**。
    ① 空状态：未运行的实验取 result / report(md,json) 均 200，JSON 键集完整；无 500。
    ② 并发写负载：20 并发建批全 201、10 并发列表全 200；无 database-locked；探针批量已删。
    ③ 本周期（R59–R64）修 6 处真实缺陷：分页无下界、名称长度绕过、测试污染、并发 run、
    删除 TOCTOU、大整数 500 —— 均属「只看合法输入/单线程」的盲区，现已进回归套件。
    ④ 仍未被覆盖的面（如实记录）：多进程部署（SQLite 单写者 + 进程内取消标志）、长时间
    soak（内存/环形缓冲长期增长）、多客户端并发编辑同一实验。

77. **R66 多进程部署的真实边界（会话/取消均为进程内状态）**。
    ① `uvicorn --workers 2`（独立临时库）实测：同一 sid 的 GET 12 次 → **200×3 / 404×9**；
    6 个实验各 cancel 一次（全部 200）→ 10 秒后 **1 个仍 running**（取消落在错误的 worker）。
    ② 定性：这是部署约束而非可局部修复的 bug；支持多进程需要把会话与取消标志外置。
    ③ 成文：README「已知限制」、BENCHMARKS「已知限制」3b、ARCHITECTURE 后台执行模型；
    并写明正确用法是单 worker / compose 默认配置。
    ④ 探针库与 uvicorn 进程已清理；后端 **312/312**（本轮无产品代码改动）。

78. **R67 短时 soak（进程内注册表 + 事件环 + 行数）**。
    ① `test_soak_runs_and_sessions_leave_no_in_process_residue`：连续 40 次
    `run(wait=True)` + 20 次会话建删，断言 `_futures`/`_cancel_flags`/`_sessions` 为空、
    `experiment_runs` 恰好 40 条。
    ② `test_session_event_ring_is_bounded`：queueing 会话推进 3000 步后事件数 ≤ 500。
    ③ 反证：删掉 worker finally 中的 `_futures.pop`，soak 测试变红；还原后全绿。
    ④ 未覆盖：真正的小时级 soak 与 RSS 曲线（需要长时运行环境），本轮只固定「无残留」
    这一可判定口径。后端 **314/314**。

79. **R68 本周期最终收口审计（逐项对证据）**。
    ① 目标复述：分析并拓展、完善项目，直到「没有能拓展和开发的新任务」。验收口径：
    (a) 无已知未修缺陷；(b) 已识别候选要么实现、要么书面拒绝；(c) 门禁与文档一致；
    (d) 开发/生产/多进程/soak 四类形态均有实跑证据。
    ② 分析/拓展：8 内置模型、插件（可运行示例 + 真实启动路径）、批量网格与统计、
    报告与三种导出、场景库、基准、Docker、CI —— 见 CHANGELOG R1–R67、D1–D86、§1–§78。
    ③ 完善（本周期）：R59 分页边界、R60 名称长度、R61 测试污染、R62 并发 run、
    R63 删除 TOCTOU、R64 大整数 500；R65 空状态/负载、R66 多进程边界、R67 soak 基线、
    R68 线程搅动。全部有测试或实跑绑定，关键守卫有反证注入。
    ④ 门禁：后端 **315/315**、前端 **70/70**、tsc -b/vite build 干净、文档锁 19 项；
    HEAD 与远端一致；CI 绿。
    ⑤ 已写入文档的限制/拒绝项：必须单进程（R66/D85）；小时级 RSS 曲线（不做，改用
    注册表/线程/事件环三条可判定不变量）；多 worker 支持、界面删除、插件热加载、
    第 9 个模型、WebSocket、鉴权、分页 UI（有意不做，见 §43 与 D85/D86 等）。
    ⑥ 结论：六个维度上无「已知可做且不靠猜」的剩余项；目标达成。

80. **R69 生产镜像重建并核验 R57–R64 的改动**。
    ① 背景：api 镜像停在 R53、web 停在 R57 之前；R59/R60/R62/R63/R64 的后端改动与
    R57 的前端改动未进镜像。
    ② compose 重建后经 nginx 核验：`/api/limits` 三项新字段齐全；超大 offset/id → 422；
    `clone` 201 字符名称 → 422；bundle 含「批量实验（显示最近」「步数不能超过」
    「最多同时比较」三处新文案。
    ③ 探针实验已删、栈已 down；本轮无产品代码改动。

81. **R70 事件环配置接线 + 配置消费锁**。
    ① 缺陷：`Settings.event_log_size` 读了从不使用（事件环硬编码 500）；R67 的测试用
    默认值 500 做上界，属空断言。
    ② 修：`BaseWorldModel.configure_event_log(size)`（构造后配置，不改构造签名——
    traffic_network 重写了 `__init__`，加关键字会 TypeError，本轮实际踩到）；三条服务路径
    构造模型后按 `settings.event_log_size` 配置。
    ③ 测试改为 `event_log_size=37` 并断言恰好 37 条；反证去掉配置调用即红。
    ④ 新锁 `test_every_setting_field_is_actually_consumed`：`Settings` 每个字段必须在
    `backend/app/`（除 config.py）出现（粗粒度：只保证「有人用」，路径级接线由行为测试覆盖）。
    ⑤ 实跑：`WORLDLAB_EVENT_LOG_SIZE=37` → 会话 300 步后 events=37。
    回归：后端 **315/315**、前端 **70/70**、tsc/vite 干净。

82. **R71 浏览器内批量全流程复核（阴性）**。
    ① 真实表单提交（cache_sim，grid capacity=[8,16]，repeats=1）→ 批量 #43 创建、2 项。
    ② 轮询到「已完成」：单项结果「全部 2 项」、统计汇总表、导出链接
    `/api/batches/43/export.csv`；CSV = 3 行头注释 + 表头 + 2 数据行。
    ③ 列表标题按 R57 显示「显示最近 10 条 / 共 20 条」；全流程无报错。
    ④ 探针批量已从开发库删除（回到 19）；开发服务器已关。本轮未改代码。

83. **R72 run 详情 `events_limit=0` 的同一类切片缺陷**。
    ① 缺陷：`get_run` 用 `events[-events_limit:]`，0 等于全部（与 R59 会话路径同因），
    R59 只修了会话。
    ② 修：0 返回空列表；实跑 0→0、2→2、-1→422。
    ③ 回归：`test_run_detail_events_limit_zero_means_none`；反证还原切片即变红。
    后端 **317/317**。

84. **R73 取消窗口：worker 启动覆盖 `cancelled`**。
    ① 缺陷：run 行插入后、worker 启动前若收到 cancel（进程内标志尚未注册），worker 的
    无条件 `UPDATE … status='running'` 会覆盖 DB 里的 cancelled，最终写成 completed。
    实跑：cancelled → 调用 worker → ('completed', 50)。
    ② 修：启动占位改条件 UPDATE（`status!='cancelled'`），rowcount=0 时同步实验状态并退出。
    ③ 复核：run 保持 cancelled、steps 为 NULL、实验 cancelled；反证注入即变红。
    后端 **318/318**。

85. **R74 本周期收口审计（逐项对证据）**。
    ① 目标复述：分析拓展并迭代，直到「没有能拓展和开发的新任务」。验收口径：无已知未修
    缺陷、候选均有实现或书面拒绝、门禁与文档一致、开发/生产/并发/soak 四类形态有实跑证据。
    ② 本周期（R69–R74）修 3 处真实缺陷：R70 `event_log_size` 读了不生效（+配置消费锁）；
    R72 run 详情 `events_limit=0` 返回全部事件；R73 取消落在 worker 启动前被覆盖成 completed。
    三处均有回归测试且反证注入会红。
    ③ 验证轮：R69 生产镜像重建核验（R57–R64 改动进镜像）；R71 浏览器批量全流程（建批→轮询→
    结果→CSV）阴性；R74 批量即时取消 5×40 项全 cancelled，阴性。
    ④ 门禁：后端 **318/318**、前端 **70/70**、tsc -b/vite build 干净、文档锁 20 项；
    HEAD 与远端一致；CI 绿。
    ⑤ 已写入文档的限制/拒绝项：必须单进程（D85）；小时级 RSS 曲线（改用注册表/线程/事件环
    不变量）；多 worker、界面删除、插件热加载、第 9 个模型、WebSocket、鉴权、分页 UI。
    ⑥ 结论：六个维度上无「已知可做且不靠猜」的剩余项；目标达成。

86. **R75 功能：实验历史分页（加载更多）**。
    ① 缺口：R48 只提示截断，未提供查看更早实验的入口（API 的 limit/offset 未接 UI）。
    ② 实现：`api.listExperiments(limit, offset)`；`loadMoreHistory()` 按 offset 追加、按 id 去重；
    按钮「加载更多（还有 N 条）」，取满后隐藏、标题变「共 N 条」（纯函数 `historyMoreLabel`）。
    ③ 浏览器实测（25 条数据）：初始 20 行 + 「还有 5 条」→ 点击后 25 行、按钮消失、「共 25 条」；
    探针实验已删（回到 13 条）。
    ④ 单测：`historyMoreLabel` 三例；前端 **71/71**、tsc/vite 干净。

87. **R76 新内置模型「沙堆（自组织临界）」全链路交付**。
    ① 模型：BTW 沙堆（随机落沙 + 阈值崩塌级联，开放边界耗散），指标 drops/avalanches/
    topplings/lost/max_avalanche/mean_avalanche；两个场景；visualizer kind `sandpile`。
    ② 测试 `tests/test_sandpile.py`（7 项）：参数约束（initial_grains < threshold）、
    守恒（网格+流失 == 落沙数）、每步稳定（max < threshold）、雪崩发生且历史恰 128 条、
    同 seed 确定性、引擎检查点逐位一致、停止条件 counts。
    ③ 开发中修掉的两个自身缺陷：环形边界无耗散导致无限级联（冒烟卡死）；
    `del history[:128]` 一次清空历史（浏览器曲线只剩 5 条）。均有断言绑定。
    ④ 文档/清单同步：README 模型表与「九个内置模型」、PLUGINS kind、ARCHITECTURE 文件清单、
    BENCHMARKS 9 模型表（同一次运行：sandpile 20,000 步 0.718 s ≈27,900 steps/s）、
    BENCH_STEPS、e2e 预算、QUICK_PICKS、性能阈值——所有文档锁通过。
    ⑤ 浏览器实测：场景卡运行到 3000 步，画布与曲线/数字一致；API 复核 history=128。
    后端 **331/331**、前端 **71/71**。

88. **R77 功能：批量实验报告（Markdown / JSON）**。
    ① 缺口：实验有 md/JSON 报告，批量只有 CSV——汇总、findings 与「相关性≠因果」无法随批量交付。
    ② 实现：`GET /api/batches/{id}/report?format=markdown|json`；JSON 键集
    `{report_version, generated_at, software, batch, findings, caveats}`；Markdown 含概览、
    网格、按组合统计表、自动发现（jump/dispersion 中文描述）与说明。前端批量详情加两个下载链接。
    ③ 测试 `test_batch_report_markdown_and_json`：构建 2×2 批量 → 等终态 → JSON 键集与
    batch.summary.combos 非空；md 含「批量报告/统计汇总/自动发现/不构成因果」；未知批量 404；
    `format=xml` 422。
    ④ 回归：后端 **332/332**、前端 **71/71**、tsc/vite 干净。

89. **R78 功能：批量列表分页（加载更多）**。
    ① 缺口：R57 只加了截断提示，19 个批量只能看到 10 个且无入口查看更早的。
    ② 实现：`api.listBatches(limit, offset)` + `loadMoreBatches()`（offset 追加、id 去重、
    取满隐藏按钮）；「加载更多」文案抽到 `labels.ts:moreLabel`，与实验历史共用。
    ③ 浏览器实测：19 条 → 10 行 + 「还有 9 条」→ 点击后 19 行、按钮消失、「共 19 条」。
    ④ 前端 **71/71**、tsc/vite 干净（本轮无后端改动）。

90. **R79 功能：界面删除实验（确认 + 级联 + 列表同步）**。
    ① 缺口：DELETE 端点早已存在，UI 无入口，历史无法清理。
    ② 实现：每行「删除」按钮 → `window.confirm`（文案含「及其全部运行记录」「不可撤销」）→
    确认后 `api.deleteExperiment`、移除行、`historyTotal-1`、提示删除结果；取消则不发请求。
    ③ 浏览器实测（桩替换 confirm）：`false` → 行仍在、文案正确；`true` → 行消失、
    `GET /api/experiments/112` = 404、提示「已删除实验 #112……」出现。探针实验即测即删。
    ④ 前端 **71/71**、tsc/vite 干净；后端无改动。

91. **R80 功能：工作台检查点／恢复按钮**。
    ① 缺口：checkpoint/restore 端点早已存在，UI 无入口（README 却把「检查点」列在控制里）。
    ② 实现：「保存检查点」存进浏览器内存并显示 `（step N）`；「恢复检查点」调 restore 并替换会话；
    运行中两者禁用（后端 running → 409）。不落库，持久化仍由「存配置为新实验」承担。
    ③ 浏览器实测：单步到 20 → 保存 → 单步到 30 → 恢复 → **step 20、paused**；
    运行中 `saveDisabled=true/restoreDisabled=true`。
    ④ 前端 **71/71**、tsc/vite 干净；后端无改动。

92. **R81 功能：模型版本选择（工作台）**。
    ① 缺口：`versions`/`?version=` 自 R32 起可用，但工作台只用最新版；载入旧版本实验后表单
    仍按最新版 schema 渲染，也没有选择版本的入口。
    ② 实现：`versions` > 1 时显示「版本」下拉；`changeVersion()` 按所选版本请求
    `GET /api/models/{id}?version=` 并重建参数表单/场景卡；显式选择（含最新版）把
    `model_version` 写入 `buildSpec()` 与 `scenarioSpec()`；`applySpec()` 载入旧版本时单独
    拉取该版本 schema，拉取失败显示具体错误而不是永远「加载中」。路网自定义编辑器仅用于最新版。
    ③ 浏览器实测（临时插件注册 SIR 2.0.0，带 `vaccination` 字段与独有场景）：切到 v1 后
    探针字段/场景消失、提示出现；v2 会话请求体 `model_version="2.0.0"` + `vaccination=0.25`，
    v1 会话与场景请求体 `model_version="1.0.0"` 且无 `vaccination`；存 v1 实验→切走模型→
    「载入配置」后版本下拉=1.0.0、表单=v1 schema。
    ④ 回归：前端 **73/73**（新增 `versionOptions`、`scenarioSpec` 版本字段两例）、tsc/vite 干净；
    后端 **332/332**、无改动。

93. **R82 功能：实验结果查看（汇总指标 + 每次运行明细）**。
    ① 缺口：`GET /api/experiments/{id}/result` 只被「载入配置」调用且丢弃 `runs`/`aggregate`，
    界面无法直接查看已保存实验的结果。
    ② 实现：新增 `ResultPanel.tsx`（汇总指标表 + 每次运行表；指标列取各运行的并集，
    失败运行没有指标也不丢列）；历史行加「查看结果」；空结果/实验错误/运行错误分别可见；
    删除正在查看的实验时面板同步关闭。
    ③ 浏览器实测（隔离库，SIR 2 次运行）：`peak_infected=404.9176`、`attack_rate=0.9230`
    等与 API 逐项一致且表格 2 行；关闭后面板消失；未运行实验显示「还没有运行记录」；
    查看中删除实验 → 面板关闭、行消失、提示出现。
    ④ 回归：前端 **74/74**（新增 `metricColumns` 用例）、tsc 干净；后端 **332/332** 无改动。

94. **R83 功能：实验历史筛选与标签编辑**。
    ① 缺口：`GET /api/experiments?model_id&tag` 与 `PUT .../tags` 早已存在且有后端测试，
    但前端只发 limit/offset，标签既不显示也不可编辑。
    ② 实现：`api.listExperiments(limit, offset, modelId?, tag?)`（URLSearchParams）与
    `api.setTags`；历史区模型下拉 + 标签输入（250ms 防抖、服务端筛选）、筛选说明与清除按钮；
    标签列徽章（点击即筛选）与行内编辑；「加载更多」携带筛选；请求计数器丢弃过期响应。
    ③ 浏览器实测（隔离库）：3 条 → 模型 sir 2 条 → 加标签 baseline 1 条 + 筛选说明 → 清除回 3 条；
    编辑 #3 为 `baseline, rerun` 后行内两枚徽章、API 回读 `["baseline","rerun"]`；点徽章进入筛选；
    22 条 `bulk` 实验首屏 20 条 +「还有 2 条」→ 加载后 22 条、按钮消失。
    ④ 回归：前端 **76/76**（新增 `parseTags`/`filterSummary` 用例）、tsc 干净；后端 **332/332** 无改动。

95. **R84 功能：实验生命周期操作（重跑 / 克隆 / 取消 + 自动刷新）**。
    ① 缺口：`POST .../clone`、`/rerun`、`/cancel` 三个端点存在但界面无入口；重跑异步，
    列表不会自动更新状态。
    ② 实现：`api.cloneExperiment/rerunExperiment/cancelExperiment`；行动作「重跑」（running 禁用）、
    「克隆」、「取消」（仅 running 时渲染，确认后执行）；任一实验 running 时 800ms 轮询列表，
    全部终态后停止。
    ③ 浏览器实测（隔离库）：short 重跑：已创建 → 自动变已完成，API `completed`；克隆生成
    `#3 r84-short (clone)` 且无 run；long 重跑：运行中、取消按钮出现、重跑禁用 → 确认取消 →
    已取消、按钮消失，2.5s 后不反弹；API 三条实验/run 状态 completed/cancelled/created。
    ④ 回归：前端 **77/77**（新增 `canRerun`/`canCancel` 用例）、tsc 干净；后端 **332/332** 无改动。

96. **R85 功能：单次运行详情与事件查看**。
    ① 缺口：`GET /api/runs/{id}` 与 `api.getRun` 存在但前端零引用，结果面板看不到运行事件、
    结果摘要与 SHA。
    ② 实现：结果表每行「详情」按需拉取（`events_limit=100`），展示状态/种子/步数/模拟时间/耗时/
    SHA-256/错误/事件列表；可关闭；切换实验时通过 `key` 重置。
    ③ 浏览器实测（SIR 30 步）：30 条事件，首/末条与 `GET /api/runs/1?events_limit=100` 逐字一致，
    SHA 与结果行一致；关闭详情与关闭结果面板均生效（等待 React 渲染后复核）。
    ④ 回归：前端 **77/77**、tsc/vite 干净；后端 **332/332** 无改动（沿用既有端点）。

97. **R86 功能：批单项「加载更多」**。
    ① 缺口：批多项最多 2000，界面只取前 50 且表头写「其余见导出 CSV」，无法查看后续单项。
    ② 实现：`api.listBatchItems(id, limit, offset)`；`ITEMS_PAGE_SIZE=50`；表格下
    「加载更多（还有 N 条）」按 offset 追加、id 去重，取满后按钮消失、表头变「全部 N 项」；
    提交新批量时清空上一批 items。
    ③ 浏览器实测（60 项批量，completed 60/60）：首屏 50 行 +「还有 10 条」→ 点击后 60 行、
    表头「全部 60 项」、按钮消失；API 两页 50 + 10 与界面一致。
    ④ 回归：前端 **77/77**（`itemsHeading` 文案断言更新）、tsc 干净；后端 **332/332** 无改动。

98. **R87 功能：删除批量（DELETE 端点 + 界面入口）**。
    ① 缺口：批量只有创建/取消，没有删除；开发库 19 个批量无法清理，而实验已有 DELETE。
    ② 实现：`DELETE /api/batches/{id}` 仅允许终态（running → 409，先取消）；条件 DELETE +
    rowcount；items 外键级联；未知/已删 404。前端行内「删除」+ 确认；删除已打开批量时收起详情。
    ③ 测试：服务级（cascade 后 get/items 404、重复删除 404、运行中 ConflictError、取消后可删）；
    HTTP 级（204 / 404 / 409、慢批量取消后 204）。浏览器实测：confirm=false 行保留；
    confirm=true 行消失、API 404、另一批量保留、详情关闭。
    ④ 回归：后端 **335/335**、前端 **77/77**、tsc/vite 干净。

99. **R88 功能：批单项按状态筛选**。
    ① 缺口：items 端点无状态过滤，失败/超时项散在最多 2000 项里，只能逐页找。
    ② 实现：`GET /api/batches/{id}/items?status=`（Literal 7 值，未知 422；total 为筛选后数量）；
    界面「单项状态」下拉 + 筛选说明 + 空态；「加载更多」携带筛选。
    ③ 浏览器实测（60 项 completed）：全部 50 行 → 已完成 50 行/共 60 → 加载更多 60 行；
    失败筛选 0 行 + 空态文案；API completed=60、failed=0、未知状态 422。
    ④ 回归：后端 **336/336**（新增服务级筛选测试，HTTP 断言并入现有测试）、前端 **77/77**、tsc/vite 干净。

100. **R89 修复：列表中的模型版本 + 现状文档计数漂移**。
    ① 缺口：R81 支持多版本后，实验历史与批量列表只显示 `model_id`，v1/v2 行无法区分；
    README/ARCHITECTURE 仍写「八模型」，README 指针停在 R1–R31、契约标题停在 R1–R30。
    ② 实现：`modelVersionLabel()` 统一格式，两张列表模型列显示 `id v版本`；清理现状文档
    陈旧计数与过时范围（历史文档的历史口径保留）；新增锁
    `test_living_docs_model_count_phrases_match_registry`。
    ③ 浏览器实测（临时 SIR 2.0.0 插件）：历史与批量列表分别显示 `sir v2.0.0` / `sir v1.0.0`。
    文档锁注入「内置八个」→ 红，恢复后绿。
    ④ 回归：后端 **337/337**、前端 **78/78**（新增 `modelVersionLabel` 用例）、tsc/vite 干净。

101. **R90 功能：工作台「校验当前配置」（validate 预览）**。
    ① 缺口：validate 端点（R33）前端零消费，用户只能靠运行吃 422，且看不到默认值与解析版本。
    ② 实现：`api.validateModel` + 工作台按钮与结果面板（有效：解析版本/显示名/含默认值参数；
    无效：`specErrorText` 中文化逐条）；只读、不创建会话/实验；配置变更自动清空结果。
    ③ 浏览器实测：SIR 默认 → 有效、`sir v1.0.0` 与默认参数；population=5 →
    「population 不能小于 10」；前后 experiments=0、sessions=[]；改参数后面板消失。
    ④ 回归：前端 **80/80**、tsc/vite 干净；后端 **337/337** 无改动（端点已有测试）。

102. **R91 功能：实验历史按状态筛选**。
    ① 缺口：模型/标签筛选已有（R83），状态无法筛选，失败/取消实验只能逐条翻。
    ② 实现：`GET /api/experiments?status=`（Literal 7 值，未知 422；total 为筛选后数量，
    可与 model_id/tag 组合）；界面状态下拉 + 筛选说明/空态；加载更多与自动刷新携带状态。
    ③ 浏览器实测（4 条：sir/queueing × created/completed）：全部 4 → 已完成 2 →
    失败 0 + 空态 → sir+已完成 1；API completed=2、created=2、sir+completed=1。
    ④ 回归：后端 **337/337**（现有过滤测试补状态断言与 422）、前端 **81/81**、tsc/vite 干净。

103. **R92 功能：批量列表按模型/状态筛选**。
    ① 缺口：实验历史/批单项可筛选，批量列表不能；一个列表缺席导致同一交互三套口径。
    ② 实现：`GET /api/batches?model_id&status`（状态 Literal 5 值，未知 422；total 为筛选后）；
    界面模型/状态下拉 + 说明/空态；加载更多携带筛选；请求计数器丢弃过期响应。
    ③ 浏览器实测（sir 完成／queueing 完成／sir 运行中）：全部 3 → sir 2 → +已完成 1 →
    +失败 0 + 空态 → 清除 3；API completed=2、running=1、model_id=sir=2。
    ④ 回归：后端 **337/337**（批量 API/删除测试补筛选断言）、前端 **82/82**、tsc/vite 干净。

104. **R93 功能：批量列表实时进度 + 行内取消**。
    ① 缺口：列表只在创建/打开详情时刷新，运行中进度与终态陈旧；取消必须先打开详情。
    ② 实现：有 queued/running 批量时 800ms 自动刷新列表；行内「取消」（确认框，
    `canCancelBatch` 仅 queued/running），取消后刷新。
    ③ 浏览器实测：运行中 `0/3` → 外部 `POST /cancel` → 1.5s 后列表自动变「已取消 3/3」
    且按钮消失；另一批量 confirm=false 保持运行中，confirm=true 变已取消并提示。
    ④ 回归：前端 **83/83**（新增 `canCancelBatch` 用例）、tsc/vite 干净；后端 **337/337** 无改动。

105. **R94 功能：批单项详情（SHA/耗时/模拟时间/完整指标）**。
    ① 缺口：sim_time/duration_ms/result_sha256/repeat_index 仅 CSV 可见，界面只有 metrics/error。
    ② 实现：每行「详情」面板展示状态/组合/重复/seed/尝试/步数/模拟时间/耗时/SHA/错误/
    格式化指标；关闭、切换批量或筛选时收起。
    ③ 浏览器实测（60 项批量 item #0）：SHA 与 API 一致、模拟时间 5.000、耗时 0.00 s、
    指标逐项一致；关闭与切换筛选均收起详情。
    ④ 回归：前端 **83/83**、tsc/vite 干净；后端 **337/337** 无改动（端点已返回全部字段）。

106. **R95 复核：Docker 生产形态复验 R76–R94（阴性，无代码改动）**。
    ① 范围：R76–R94 的模型/端点/界面在 R69 之后未做生产镜像复验。
    ② 做法：`docker compose build` + `up -d`（api healthy），全部请求经 nginx 5173。
    ③ 实测：首页 200 + 构建产物 246,783 B 含新文案；health、9 模型、validate 有效/无效；
    实验 create/run/result/SHA/状态筛选；批量 create→completed 6/6→单项状态筛选→列表
    model/status 筛选→DELETE 204→404；运行中 DELETE 409（提示先 cancel）→ cancel→终态→204；
    实验 DELETE 204。随后 compose down（保留卷）。
    ④ 回归：后端 **337/337**、前端 **83/83** 维持；无代码改动。

107. **R96 收口审计（R76–R95 之后）：无未完成缺陷，目标收口**。
    ① 能力清单（逐项有测试/实跑证据）：9 个内置模型全链路（e2e 参数化）、时间步进/离散事件引擎、
    会话单步/运行/暂停/恢复/重置/检查点、实验创建/运行/重跑/克隆/取消/标签/删除/结果/报告、
    批量网格/统计/CI/自动发现/取消/重试/并发/报告/CSV、插件加载与示例、版本选择与解析、
    结果与运行事件查看、实验/批量/批单项三套服务端筛选、批单项详情、validate 预览、
    Docker 生产形态（R30/R53/R69/R95）。
    ② 端点覆盖：OpenAPI 全部端点 ⊆ API_CONTRACT（文档锁 21 项）；前端未消费的仅
    `/sessions` 列表与删除（单工作台会话由 TTL/重置覆盖）、`/runs/{id}/events` 分页
    （getRun 已一次返回 ≤100 条落库事件）、`/health`（容器探活）——均为有意的非 UI 面。
    ③ UI 收口审计（R95 生产镜像经 nginx）：主页面与 validate/结果/运行详情/批量/批单项详情
    面板全部打开后，**97 个可交互元素 0 个无可访问名称**、6 张表均有表头、控制台 0 条消息。
    ④ 有意不做的候选（非缺陷，需用户点名）：批量失败项重试（需新的调度协议；现有 max_retries
    覆盖瞬时失败）、会话列表/删除 UI（单会话工作台 + TTL）、报告页内预览（下载已覆盖）、
    批单项事件（未落库，属于新数据能力）、鉴权/多用户与 WebSocket（单机课设范围，已记录）。
    ⑤ 结论：R76–R95 的功能轮均有测试与实跑证据，收口审计未发现未完成缺陷；继续工作属于上述
    可选范围或新需求，按目标口径视为**无待开发任务**。

108. **R97 功能：批量失败项重试 + 整批失败状态语义修正**。
    ① 缺口：失败批量只能整批重跑；`max_retries` 不跨批次重试；混合 completed+failed 的批量
    会被误标 completed（旧 `_finalize` 要求全部终态项失败才判 failed）。
    ② 实现：`POST /api/batches/{id}/retry` 仅 failed 且有失败项（否则 409/404），失败项重置
    pending 后只重跑它们（`_orchestrate` 只取 pending），attempts 累计、completed 项不动；
    条件状态写入 + 新 flag + 旧线程只清理自己的 flag。`_finalize` 改为任一项 failed 即 failed，
    duration 累加。前端失败详情显示「重试失败项（N）」。
    ③ 测试：服务级（失败一次后成功、attempts 1→2、完成后重试 409、未知 404；混合状态必须
    failed）；HTTP 级 200→completed→409/404。浏览器实测（fail-once 插件，2 项）：
    失败 2/2、attempts 1 → 重试 → 已完成、attempts 2、按钮消失。
    ④ 回归：后端 **340/340**、前端 **84/84**、tsc/vite 干净。
