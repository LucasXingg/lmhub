import streamlit as st
import time
import base64
import io
from config import ProviderConfig, AppConfig
from providers import BaseProvider, ModelResponse, TokenBreakdown
from anthropic import Anthropic


ANTHROPIC_MODELS = [
    "claude-sonnet-4-20250514",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
    "claude-3-haiku-20240307",
]

PRICING = {
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    "claude-3-opus-20240229": (15.00, 75.00),
    "claude-3-haiku-20240307": (0.25, 1.25),
}

DEFAULT_MODEL = "claude-sonnet-4-20250514"


class AnthropicProvider(BaseProvider):
    name = "Anthropic"
    icon = ":material/psychology:"
    description = "Anthropic Claude 系列模型"

    def get_default_config(self) -> ProviderConfig:
        return ProviderConfig(
            model=DEFAULT_MODEL,
            temperature=1.0,
            max_tokens=4096,
        )

    def get_model_options(self) -> list[str] | None:
        return ANTHROPIC_MODELS

    def get_default_base_url(self) -> str:
        return ""

    def get_api_key_help(self) -> str | None:
        return "在 https://console.anthropic.com/ 创建"

    def get_base_url_help(self) -> str | None:
        return "可选，用于自定义代理地址"

    def verify_config(self, config: ProviderConfig):
        if not config.api_key:
            raise Exception(
                "Anthropic API Key 未设置。请在侧栏「Anthropic」配置页填写后点击保存"
            )

    def get_config_summary(self, config: ProviderConfig):
        return [
            ("API Key", (config.api_key[:8] + "...") if config.api_key else "未设置"),
            ("Model", config.model),
        ]

    def render_post_config_info(self, config: ProviderConfig):
        price = PRICING.get(config.model, (3.00, 15.00))
        st.caption(f"参考价格 (每百万 tokens): 输入 ${price[0]}, 输出 ${price[1]}")
        st.info("Anthropic 不提供按模态细分的 token 数据")

    def call_model(self, config: ProviderConfig, messages, images=None) -> ModelResponse:
        self.verify_config(config)

        client_kwargs = {"api_key": config.api_key}
        if config.base_url:
            client_kwargs["base_url"] = config.base_url
        client = Anthropic(**client_kwargs)

        system_prompt = ""
        anthropic_messages = []
        for msg in messages[:-1]:
            if msg["role"] == "system":
                system_prompt += msg["content"] + "\n"
            else:
                anthropic_messages.append(
                    {"role": msg["role"], "content": msg["content"]}
                )

        if images and len(images) > 0:
            content = []
            for img in images:
                buf = io.BytesIO()
                img.save(buf, format="PNG", optimize=True)
                b64 = base64.b64encode(buf.getvalue()).decode()
                content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    }
                )
            content.append({"type": "text", "text": messages[-1]["content"]})
            anthropic_messages.append({"role": "user", "content": content})
        else:
            anthropic_messages.append(
                {"role": messages[-1]["role"], "content": messages[-1]["content"]}
            )

        api_kwargs = {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "messages": anthropic_messages,
        }
        if system_prompt.strip():
            api_kwargs["system"] = system_prompt.strip()

        start = time.time()
        response = client.messages.create(**api_kwargs)
        latency = (time.time() - start) * 1000

        usage = response.usage
        input_tokens = usage.input_tokens if usage else 0
        output_tokens = usage.output_tokens if usage else 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

        input_breakdown = TokenBreakdown(
            text_tokens=input_tokens - cache_read,
            cached_tokens=cache_read,
        )
        output_breakdown = TokenBreakdown(text_tokens=output_tokens)

        text_content = ""
        for block in response.content:
            if block.type == "text":
                text_content += block.text

        input_price, output_price = PRICING.get(config.model, (3.00, 15.00))
        cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000

        return ModelResponse(
            text=text_content,
            total_input_tokens=input_tokens,
            total_output_tokens=output_tokens,
            input_breakdown=input_breakdown,
            output_breakdown=output_breakdown,
            model=response.model,
            latency_ms=latency,
            finish_reason=getattr(response, "stop_reason", "") or "",
            cost=cost,
            raw_response=response.model_dump(),
        )
