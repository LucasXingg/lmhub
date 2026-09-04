# LMHub

多供应商 LLM 测试工具，基于 Streamlit。支持同时配置多个 AI 供应商，在统一界面测试、对比不同模型的响应质量、Token 用量和费用。

## 支持的供应商

| 供应商 | 模型系列 |
|--------|---------|
| OpenAI | GPT-4o, GPT-4.1, o1, o3-mini, o4-mini |
| Anthropic | Claude Sonnet 4, Claude 3.5 Sonnet/Haiku, Claude 3 Opus/Haiku |
| 火山方舟 (Ark) | 豆包 Seed 2.0 / 1.6 系列 |
| 智谱AI | GLM-5.2, GLM-4-Plus/Flash/Air, GLM-4V 系列 |
| OpenAI 兼容 | Ollama / vLLM / LM Studio 等 |

## 功能

- **多方案配置** — 同一供应商可新建多组配置（不同 API Key / 模型），快速切换对比
- **统一测试界面** — 输入系统提示词 + 用户消息，一键发送到多个供应商
- **图片支持** — 上传图片发送给视觉模型，支持预处理（缩放 / 裁剪 / 填充）
- **视频抽帧评测** — 上传视频片段，按均匀采样 / 固定间隔 / 场景变化 / 自定义时间点抽帧后送入多模态模型
- **用量统计** — 按文本、图片、音频、缓存细分 Token 消耗
- **费用估算** — 自动根据定价计算每次调用的预估费用
- **提示词模板** — 保存 / 加载常用提示词（含纯文本或 Python 脚本模式）
- **动态提示词** — 每个提示词输入可切换为 Python 脚本，脚本须赋值 `prompt` 变量

## 快速开始

```bash
# 1. 安装依赖
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. 启动
./start.sh
```

浏览器访问 `http://localhost:8501`。

## 使用流程

1. 在侧栏 **⚙️ Providers** 中选择供应商，填写 API Key 等配置并保存
2. 切换到 **🧪 Demo** 页面
3. 选择供应商和配置方案
4. 输入系统提示词和用户消息
5. （可选）上传图片
6. 点击 **发送**，查看回复、Token 用量和费用

### 视频抽帧评测

1. 切换到 **🎬 Video** 页面，选择供应商与配置方案
2. 上传视频片段（mp4 / mov / mkv / webm 等），或填写本机路径。浏览器选文件后按 256KB 经 WebSocket 分片传输，避开反向代理对 `/_stcore/upload_file` 常见的 1MB 限制（Axios 413）。超大文件建议用本机路径
3. 选择抽帧策略并设置时间区间，点击 **提取帧**
4. 在帧预览网格中勾选要发送的帧（可在侧栏开启缩放以节省 token）
5. 填写提示词后点击 **发送**，查看回复与 Token 用量

## 创建新供应商

在 `providers/` 下新建 `<名称>_provider.py`，只需实现 2 个抽象方法：

```python
from providers import BaseProvider, ExtraField, ModelResponse
from config import ProviderConfig

class MyProvider(BaseProvider):
    name = "我的供应商"
    icon = ":material/star:"

    def get_default_config(self) -> ProviderConfig:
        return ProviderConfig(model="my-model", base_url="https://api.example.com/v1")

    def call_model(self, config: ProviderConfig, messages, images=None) -> ModelResponse:
        self.verify_config(config)
        # 调用 API，返回 ModelResponse
        ...
```

启动时自动扫描注册，无需修改其他文件。完整说明见 [CLAUDE.md](CLAUDE.md)。

## 项目结构

```
app.py                  # 入口
config.py               # 配置数据类
providers/              # 供应商实现（自动发现）
pages/demo.py           # 测试界面
pages/multi_turn.py     # 多轮对话界面
pages/video_eval.py     # 视频抽帧评测界面
image_processor.py      # 图片预处理
video_processor.py      # 视频抽帧
prompt_templates.py     # 提示词模板存取与管理组件
usage_view.py           # Token 用量展示组件
configs/                # 持久化配置 (JSON)
```

## 依赖

- Python >= 3.10
- Streamlit >= 1.36
- openai >= 1.0
- anthropic >= 0.30
- Pillow >= 10.0
- requests >= 2.27
- numpy >= 1.24
- opencv-python-headless >= 4.9（视频抽帧；也可换成 av / PyAV）
