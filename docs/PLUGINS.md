# WorldLab 模型插件接口

WorldLab 的模型库是插件式的：核心引擎、实验管理、API 与前端**不 import 任何模型包**；
模型通过注册表自注册接入。新增一个模型只需要一个新包（内置）或一个外部 Python
模块（外部插件），零核心模块改动。

## 信任边界

模型插件是**随服务端一起安装的可信代码**，运行在服务端进程内（批量实验在 worker
线程池中运行）。平台不支持也不隔离任意不可信模型代码——行为定义走 spec（参数 +
停止条件），而非用户提交的代码。这与立项要求一致：任意模型代码不得在服务器主进程
中执行。

## 插件契约

一个模型插件 = 一个继承 `BaseWorldModel` 子类的类 + 注册。

### 类属性（注册时强校验，缺失即 `RegistryError`）

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| `model_id` | `str` | 全局唯一 ID（同 ID 多版本允许，版本字符串互异） |
| `display_name` | `str` | 界面显示名 |
| `description` | `str` | 非空说明（前端模型选择器展示） |
| `model_type` | `str` | `"time_stepped"` 或 `"discrete_event"`，**必须与基类一致**（注册时校验） |
| `version` | `str` | 语义化版本；同 ID 不同版本可共存，跨版本结果默认不可直接比较 |
| `visualizer` | `dict` | 可视化适配器声明，必须含字符串 `kind`。前端 `SimView` 对以下 kind 有专用视图：`queue`、`cpu_schedule`、`cache`、`ca`、`schelling`、`traffic`、`sir`、`predator_prey`；**其余任意 kind 自动落到通用状态表 `StateTable`**（数据照样能看，只是没有定制图形），所以插件可以先声明新 kind 再接视图。`series` 键只是元数据（内置模型附带曲线名列表），**前端当前不读取它**，不要依赖它自动出图 |
| `param_model` | `type[WorldLabParams]` | Pydantic 参数 Schema（`extra="forbid"`），`model_json_schema()` 驱动前端结构化编辑器 |
| `dt` | `float` | 仅 time-stepped：每步推进的固定 Δt |
| `scenarios` | `list[dict]`（**可选**，缺省 `[]`） | 一键场景库；注册时校验形状（见下） |

### 一键场景（`scenarios`，可选）

每一项是一个 dict：`id`/`title`/`description` 为非空字符串、`params` 为 dict；
`seed` 与 `stop_condition` 可省略——工作台点场景卡时**沿用当前表单值**（表单停止
值非法或未提供时兜底 `steps/1000`，种子留空则 `null`=每次随机）。注册表强校验：
形状不合即 `RegistryError`，同模型内 `id` 不得重复。`GET /api/models` 原样透传
`scenarios`，工作台「模型与参数」区把它们渲染成可点击的场景卡——点卡片即以此
参数建会话并连续运行。首页「一键运行」快捷入口（QUICK_PICKS）是前端为内置模型
精选的固定列表，外部插件的场景出现在其自身模型的详情区，而非首页。

### 实例方法

全部模型必须实现：`initialize(ctx)`、`dump_state()`、`load_state(state)`、
`snapshot()`、`finalize_metrics() -> dict[str, float]`（指标定义）。

- 离散事件模型额外实现 `handle_event(event, ctx)`；用 `ctx.schedule(delay,
  priority, event)` 排未来事件，事件按 `(time, priority, seq)` 全序处理，
  零延迟链有环检测。
- 时间步进模型额外实现 `step()`：一次调用恰好推进 `self.dt`。
- 状态必须 JSON 可序列化（快照与检查点经 API/DB 传输）。
- 私有 RNG：构造器注入 `random.Random(seed)`，禁止全局随机——这是可复现性
  （同模型+参数+seed ⇒ 同结果）的基础。

## 注册方式

### 内置模型

```
app/models/<plugin_id>/
    __init__.py   # registry.register(MyModel)
    params.py     # WorldLabParams 子类
    model.py      # 模型实现
```

然后在 `app/models/__init__.py` 加一行 `from . import <plugin_id>`——这是唯一
需要触碰的文件，且它不属于任何核心模块。

### 外部插件

插件包定义 `register(registry)` 钩子：

下面是一个**完整可运行**的最小插件（R55 起由
`tests/test_plugins.py::test_documented_plugin_example_is_runnable` 直接从本文档抽取并运行，
示例与代码不会再各走一路）：

```python
# my_plugins/lottery.py
from app.core.engine.models_base import TimeSteppedModel, WorldLabParams


class LotteryParams(WorldLabParams):
    n: int = 10          # 每步投掷的硬币数


class LotteryModel(TimeSteppedModel):
    model_id = "lottery"
    display_name = "投硬币（示例插件）"
    description = "每步投 n 枚硬币，统计正面比例。"
    version = "1.0.0"
    param_model = LotteryParams
    dt = 1.0
    visualizer = {"kind": "none"}   # 未知 kind 会让前端回落到通用状态表

    def initialize(self, ctx=None):
        self.heads = 0
        self.total = 0

    def step(self):
        for _ in range(self.params.n):
            if self.rng.random() < 0.5:
                self.heads += 1
        self.total += self.params.n
        self.emit(float(self.total), "tick", f"正面 {self.heads}/{self.total}")

    def dump_state(self):
        return {"heads": self.heads, "total": self.total}

    def load_state(self, state):
        self.heads = int(state["heads"])
        self.total = int(state["total"])

    def snapshot(self):
        ratio = self.heads / self.total if self.total else 0.0
        return {"heads": self.heads, "total": self.total, "ratio": ratio}

    def finalize_metrics(self):
        ratio = self.heads / self.total if self.total else 0.0
        return {"heads": float(self.heads), "ratio": ratio}


def register(registry):
    registry.register(LotteryModel)
```

五个必须实现的方法决定了两类契约：`step()`（固定 Δt 推进）、`snapshot()`（前端视图）、
`dump_state()`/`load_state()`（检查点与恢复）、`finalize_metrics()`（结果指标）；
`initialize()` 可选。所有状态必须 JSON 安全。

启动时加载（逗号分隔，顺序即加载顺序）：

```
WORLDLAB_PLUGIN_MODULES=my_plugins.lottery,other_pkg.models uvicorn app.main:app --port 8000
```

加载失败（模块不存在 / `register()` 抛异常 / 契约校验不过）会让应用启动失败，
错误信息指明具体插件与原因。

容器部署时，插件模块必须对 `api` 容器内可导入：要么构建进镜像，要么挂载目录并设置
`PYTHONPATH`，再设 `WORLDLAB_PLUGIN_MODULES`；该变量只负责按名导入，不搬运代码（R58 成文）。

## 注册表 API（`app/core/registry.py`）

- `registry.register(cls)` — 校验并登记；同 ID+同版本重复注册报错。
- `registry.get(model_id, version=None)` — 取类；缺省返回**数值上最新**的版本
  （版本号按点/横线/加号分割的数字组分比较，`10.0.0 > 2.0.0`；非数字段视作 0，R32）。
- `registry.versions_of(model_id)` / `registry.list()` — 元数据清单（同 ID 内版本升序；
  `GET /api/models` 在此基础上**每个 model_id 只出一条**并附 `versions` 列表）。
- `registry.builtin_ids()` — 内置模型 id（注册类来自 `app.models.*`）；插件模型不在列。
  **这是内置清单的唯一事实源**，基准脚本、端到端测试与文档一致性测试都由它派生。

## 插件质量要求（与内置模型同标准）

每个模型插件应附带：参数校验测试、确定性测试（同 seed 两次运行逐事件一致）、
边界测试（空输入/极端参数/停止条件触达）、可运行示例。参考
`tests/test_queueing.py`、`tests/test_cpu_scheduling.py` 等。
