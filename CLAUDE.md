# LMHub

Streamlit 多供应商 LLM 测试工具。支持同时在侧栏配置多个 AI 供应商，在 Demo 页统一测试、对比模型的响应、Token 用量和费用。

## 命令

```bash
./start.sh          # 启动 Streamlit 开发服务器
streamlit run app.py  # 等效
```

视频页不用 `st.file_uploader`：反向代理（nginx 默认 `client_max_body_size=1m`）会把
`/_stcore/upload_file` 的 PUT 直接打成 Axios 413，1MB 出头的片子就会中招。
`video_upload.py` 用自定义组件把文件按 256KB 经 WebSocket 分片传到 Python。
超大文件也可填本机路径，解码器直接读磁盘。

## 架构

```
app.py                  # 入口：注册 providers、生成配置页、启动导航
config.py               # AppConfig / ProviderConfig 数据类（JSON 持久化到 configs/）
providers/__init__.py   # BaseProvider 基类 + ExtraField + discover_providers() 自动发现
providers/*_provider.py # 各供应商实现（启动时自动扫描注册）
pages/demo.py           # 主测试页：选择供应商 → 输入消息 → 查看结果/用量/费用
pages/multi_turn.py     # 多轮对话页：上下文由供应商内部维护
pages/video_eval.py     # 视频抽帧评测页：上传视频 → 抽帧 → 连同提示词发送
image_processor.py      # 图片预处理工具（缩放/裁剪/填充）
video_processor.py      # 视频抽帧工具（策略计算 + av/cv2 双解码后端）
video_upload.py         # 浏览器视频分片上传（WebSocket，避开 HTTP 413）
prompt_input.py         # 提示词输入：纯文本 / Python 脚本，脚本须赋值 prompt
prompt_templates.py     # 提示词模板持久化与选择/管理组件（各页共用，含输入模式）
usage_view.py           # Token 用量 / 费用汇总展示组件（各页共用）
```

- 供应商通过文件名模式 `*_provider.py` 自动发现，无需手动注册。
- 配置以"方案(profile)"组织，每个供应商可有多组配置（如不同模型/API Key）。
- `app.py` 每次启动自动生成 `pages/configs/config_*.py` 每供应商配置页。
- 配置页面由 `BaseProvider.config_page()` 统一渲染，子类通过钩子方法自定义字段和行为。

## 创建新供应商

在 `providers/` 下新建 `<供应商名>_provider.py`，定义继承 `BaseProvider` 的类。

### 文件命名

必须以 `_provider.py` 结尾，`discover_providers()` 通过 `glob("*_provider.py")` 扫描。

### 必须实现的抽象方法（仅 2 个）

| 方法 | 签名 | 用途 |
|------|------|------|
| `get_default_config` | `() -> ProviderConfig` | 返回默认配置（model、base_url、temperature 等） |
| `call_model` | `(config: ProviderConfig, messages, images=None) -> ModelResponse` | 调用 API，返回统一的 `ModelResponse` |

### 可选重写的钩子方法

| 方法 | 签名 | 默认值 | 用途 |
|------|------|--------|------|
| `verify_config` | `(config: ProviderConfig)` | 空 | 校验必填字段，抛出 Exception 即可 |
| `get_config_summary` | `(config: ProviderConfig) -> list[tuple[str, str]]` | `[]` | Demo 页显示当前配置摘要 |
| `get_model_options` | `() -> list[str] \| None` | `None` | 返回模型列表显示 selectbox；返回 `None` 则为自由文本输入 |
| `get_default_base_url` | `() -> str` | `get_default_config().base_url` | Base URL 默认值 |
| `get_api_key_help` | `() -> str \| None` | `None` | API Key 输入框的帮助文本 |
| `get_base_url_help` | `() -> str \| None` | `None` | Base URL 输入框的帮助文本 |
| `requires_api_key` | `() -> bool` | `True` | API Key 是否必填。返回 `False` 时隐藏该字段 |
| `show_temperature` | `() -> bool` | `True` | 是否显示 Temperature 滑块 |
| `get_temperature_range` | `() -> tuple[float, float, float]` | `(0.0, 2.0, 0.1)` | Temperature 的 (min, max, step) |
| `get_max_tokens_range` | `() -> tuple[int, int, int]` | `(256, 128000, 256)` | Max Tokens 的 (min, max, step) |
| `get_extra_fields` | `() -> list[ExtraField]` | `[]` | 供应商独有的配置字段声明 |
| `render_post_config_info` | `(config: ProviderConfig)` | 空 | 在配置页底部显示定价、提示等额外信息 |

### 类属性

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | `str` | `"Base"` | 显示名，作为 `PROVIDER_REGISTRY` 的 key |
| `icon` | `str` | `"🔌"` | Streamlit material 图标（如 `:material/robot_2:`） |
| `description` | `str` | `""` | 供应商描述 |
| `supports_images` | `bool` | `True` | 是否支持图片输入。为 `False` 时 Demo 页隐藏上传控件 |

### BaseProvider 已统一处理的功能

以下功能由 `BaseProvider.config_page()` 模板方法统一实现，**子类无需、也不应重写**：

- 配置方案选择 / 新建 / 重命名 / 删除
- API Key 输入框（可通过 `requires_api_key` 控制显隐）
- Base URL 输入框
- 模型选择（selectbox 或 text_input，由 `get_model_options` 决定）
- Temperature 滑块（可通过 `show_temperature` 控制显隐）
- Max Tokens 数字输入
- 高级选项区域（由 `get_extra_fields` 声明，自动渲染）
- "保存配置"按钮（自动从 session_state 读取所有字段值并保存）
- "测试连接"按钮（自动调用 `test_connection` → 委托 `call_model("hi")`）
- API Key 状态提示

## ExtraField 声明式字段

```python
from providers import ExtraField

@dataclass
class ExtraField:
    key: str                           # 存储在 config.extra 的键
    label: str                         # 界面显示的标签
    type: str = "text"                 # "checkbox" | "select" | "text" | "number" | "slider"
    default: Any = None                # 默认值
    help: str = ""
    options: list[str] | None = None   # select 的候选项列表
    option_labels: list[str] | None = None  # select 的显示标签（与 options 一一对应）
    min_val: float | None = None       # number/slider 的最小值
    max_val: float | None = None
    step: float = 1.0
    true_value: Any = True             # checkbox 勾选时保存的值
    false_value: Any = False           # checkbox 取消时保存的值
```

使用示例（火山方舟）：

```python
def get_extra_fields(self) -> list[ExtraField]:
    return [
        ExtraField(
            key="thinking",
            label="启用深度思考 (Thinking)",
            type="checkbox",
            true_value="enabled",
            false_value="disabled",
            help="模型在回答前会进行内部推理",
        ),
        ExtraField(
            key="image_detail",
            label="图片理解精细度",
            type="select",
            options=["low", "high", "xhigh"],
            option_labels=["低 (low)", "中 (high)", "高 (xhigh)"],
            default="high",
        ),
    ]
```

字段值自动保存到 `config.extra[key]`，在 `call_model` 中通过 `config.extra.get("key", default)` 读取。

## 编写 call_model 的规范

```python
def call_model(self, config: ProviderConfig, messages, images=None) -> ModelResponse:
    self.verify_config(config)

    # messages 是 list[dict]，格式为 [{"role": "user"/"system"/"assistant", "content": "..."}]
    # images 是 list[PIL.Image.Image] 或 None，仅最后一条 user 消息附带图片

    # 1. 构建 API 请求（按供应商格式转换 messages + images）
    # 2. 计时：start = time.time(); ... ; latency = (time.time() - start) * 1000
    # 3. 调用 API
    # 4. 解析响应 → 填充 TokenBreakdown → 计算 cost → 返回 ModelResponse

    # test_connection 会以 max_tokens=10 调用本方法发送 "hi"，行为无差异
```

### ProviderConfig 结构

```python
@dataclass
class ProviderConfig:
    api_key: str = ""          # API 密钥
    base_url: str = ""         # API 端点地址
    model: str = ""            # 模型名称
    temperature: float = 0.7
    max_tokens: int = 4096
    extra: dict = {}           # 自定义扩展字段（通过 ExtraField 声明式管理）
```

### ModelResponse 结构

```python
@dataclass
class ModelResponse:
    text: str                              # 模型回复文本
    total_input_tokens: int
    total_output_tokens: int
    input_breakdown: TokenBreakdown        # 按模态细分（text/image/audio/cached）
    output_breakdown: TokenBreakdown
    model: str = ""
    latency_ms: float = 0.0                # 调用延迟（毫秒）
    finish_reason: str = ""
    cost: float = 0.0                      # 预估费用（USD）
    raw_response: dict = {}                # API 原始响应（用于 Debug 展示）
```

## 图片处理

不同 API 对图片的格式要求不同：

- **OpenAI**: `{"type": "image_url", "image_url": {"url": "data:image/png;base64,<b64>"}}`
- **Anthropic**: `{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "<b64>"}}`
- **火山方舟**: `{"type": "input_image", "image_url": "data:image/png;base64,<b64>"}`

统一做法：将 PIL Image 转为 PNG bytes → base64 编码 → 拼入 API 请求。
图片只附在最后一条 user 消息中，前面的消息仅保留纯文本。

侧栏图像预处理默认关闭；`img_proc_enable` 为 True 时才缩放/裁剪。

## 动态提示词

所有系统/用户提示词输入框都带「纯文本 / Python 脚本」开关。脚本模式用 `exec` 运行，**必须赋值 `prompt`（str）** 作为发给模型的最终内容，不引入额外依赖。异常直接显示在页面上。只读变量 `context` 由各页注入（如视频帧时间戳、多轮历史）。

模板 JSON 额外保存 `content_mode` / `user_mode`（`string` | `script`），旧模板缺省视为纯文本。

## 视频抽帧

`video_processor.py` 把视频拆成 PIL Image 列表，之后完全复用图片链路（`call_model` 的 `images` 参数），
因此 **供应商无需为视频做任何适配**，只要 `supports_images = True` 即可用于视频评测。

- 解码后端按 `av` (PyAV) → `cv2` (OpenCV) 顺序自动选择，两者任一可用即可；`available_backend()` 返回当前后端。
- 抽帧策略只负责算出时间点列表，再统一交给 `extract_frames(path, timestamps)`：
  - `uniform_timestamps(count, start, end)` — 均匀采样
  - `interval_timestamps(step, start, end, max_frames)` — 固定间隔
  - `parse_timestamps(text)` — 自定义时间点，支持 `12.5` / `01:03.5` 写法
  - `detect_scene_timestamps(...)` — 顺序扫描，保留与上一张保留帧差异超过阈值的时间点
- `clamp_range(info, start, end)` 会为末尾留出一帧余量，避免读取视频结尾时解码失败。

## 精简示例

```python
# providers/my_provider.py
from providers import BaseProvider, ExtraField, ModelResponse, TokenBreakdown
from config import ProviderConfig

class MyProvider(BaseProvider):
    name = "我的供应商"
    icon = ":material/star:"

    def get_default_config(self) -> ProviderConfig:
        return ProviderConfig(model="my-model", base_url="https://api.example.com/v1")

    def get_model_options(self) -> list[str] | None:
        return ["my-model", "my-model-2"]

    def get_extra_fields(self) -> list[ExtraField]:
        return [ExtraField(key="custom_opt", label="自定义选项", type="checkbox")]

    def verify_config(self, config):
        if not config.api_key:
            raise Exception("API Key 未设置")

    def call_model(self, config, messages, images=None) -> ModelResponse:
        self.verify_config(config)
        # ... 构建请求、调用 API、解析响应 ...
        return ModelResponse(text="...", total_input_tokens=0, total_output_tokens=0)
```

## 注意事项

1. **新增供应商无需修改任何其他文件**：`discover_providers()` 会自动扫描注册，`app.py` 会自动生成配置页。
2. **`verify_config` 抛出 Exception 会被上层捕获并显示为错误**：不需要返回错误码。
3. **费用计算单位是 USD / 百万 tokens**：`cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000`。
4. **`extra` 字段统一通过 `ExtraField` 声明**：BaseProvider 自动渲染并保存到 `config.extra`，在 `call_model` 中用 `config.extra.get("key", default)` 读取。
5. **`raw_response` 必须是可 JSON 序列化的 dict**：Demo 页的 Debug 面板会尝试 `json.dumps` 展示。
6. **`supports_images = False` 时，Demo 页不显示图片上传区域**，`call_model` 的 `images` 参数始终为 `None`。
7. **`test_connection` 已由 BaseProvider 统一实现**：子类无需重写，它会调用 `self.call_model(config, [{"role": "user", "content": "hi"}])` 并显示结果。
8. **定价表建议用模块级常量**：参考现有 providers 中的 `PRICING` / `PRICING_CNY` 字典模式。
