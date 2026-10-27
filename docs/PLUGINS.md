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
| `visualizer` | `dict` | 可视化适配器声明，必须含字符串 `kind`（前端 `SimView` 按 kind 分发；如 `{"kind": "series", "series": [...]}`、`{"kind": "grid"}`、`{"kind": "gantt"}`、`{"kind": "none"}`） |
| `param_model` | `type[WorldLabParams]` | Pydantic 参数 Schema（`extra="forbid"`），`model_json_schema()` 驱动前端结构化编辑器 |
| `dt` | `float` | 仅 time-stepped：每步推进的固定 Δt |

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

```python
# my_plugins/lottery.py
from app.core.engine.models_base import TimeSteppedModel, WorldLabParams

class LotteryParams(WorldLabParams):
    n: int = 10

class LotteryModel(TimeSteppedModel):
    model_id = "lottery"
    display_name = "Lottery"
    description = "Example external plugin."
    model_type = "time_stepped"
    version = "1.0.0"
    visualizer = {"kind": "none"}
    param_model = LotteryParams
    # ... 实现各方法

def register(registry):
    registry.register(LotteryModel)
```

启动时加载（逗号分隔，顺序即加载顺序）：

```
WORLDLAB_PLUGIN_MODULES=my_plugins.lottery,other_pkg.models uvicorn app.main:app --port 8000
```

加载失败（模块不存在 / `register()` 抛异常 / 契约校验不过）会让应用启动失败，
错误信息指明具体插件与原因。

## 注册表 API（`app/core/registry.py`）

- `registry.register(cls)` — 校验并登记；同 ID+同版本重复注册报错。
- `registry.get(model_id, version=None)` — 取类；缺省返回最新版本。
- `registry.versions_of(model_id)` / `registry.list()` — 元数据清单（`/api/models`）。

## 插件质量要求（与内置模型同标准）

每个模型插件应附带：参数校验测试、确定性测试（同 seed 两次运行逐事件一致）、
边界测试（空输入/极端参数/停止条件触达）、可运行示例。参考
`tests/test_queueing.py`、`tests/test_cpu_scheduling.py` 等。
