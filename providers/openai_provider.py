import streamlit as st
import time
import base64
import io
from config import ProviderConfig, AppConfig
from providers import BaseProvider, ModelResponse, TokenBreakdown
from openai import OpenAI


OPENAI_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4-turbo",
    "gpt-3.5-turbo",
    "o1",
    "o3-mini",
    "o4-mini",
]

PRICING = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "o1": (15.00, 60.00),
    "o3-mini": (1.10, 4.40),
    "o4-mini": (1.10, 4.40),
}

DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIProvider(BaseProvider):
    name = "OpenAI"
    icon = ":material/robot_2:"
    description = "OpenAI GPT-4o, o1, o3 系列模型"

    def get_default_config(self) -> ProviderConfig:
        return ProviderConfig(
            model=DEFAULT_MODEL,
            base_url="https://api.openai.com/v1",
            temperature=0.7,
            max_tokens=4096,
        )

    def get_model_options(self) -> list[str] | None:
        return OPENAI_MODELS

    def get_default_base_url(self) -> str:
        return "https://api.openai.com/v1"

    def get_api_key_help(self) -> str | None:
        return "在 https://platform.openai.com/api-keys 创建"

    def verify_config(self, config: ProviderConfig):
        if not config.api_key:
            raise Exception(
                "OpenAI API Key 未设置。请在侧栏「OpenAI」配置页填写后点击保存"
            )

    def get_config_summary(self, config: ProviderConfig):
        return [
            ("API Key", (config.api_key[:8] + "...") if config.api_key else "未设置"),
            ("Model", config.model),
            ("Base URL", config.base_url),
        ]

    def render_post_config_info(self, config: ProviderConfig):
        price = PRICING.get(config.model, (2.50, 10.00))
        st.caption(f"参考价格 (每百万 tokens): 输入 ${price[0]}, 输出 ${price[1]}")

    def call_model(self, config: ProviderConfig, messages, images=None) -> ModelResponse:
        self.verify_config(config)

        client = OpenAI(api_key=config.api_key, base_url=config.base_url)

        api_messages = []
        for msg in messages[:-1]:
            api_messages.append({"role": msg["role"], "content": msg["content"]})

        if images and len(images) > 0:
            content = []
            for img in images:
                buf = io.BytesIO()
                img.save(buf, format="PNG", optimize=True)
                b64 = base64.b64encode(buf.getvalue()).decode()
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    }
                )
            content.append({"type": "text", "text": messages[-1]["content"]})
            api_messages.append({"role": "user", "content": content})
        else:
            api_messages.append(
                {"role": messages[-1]["role"], "content": messages[-1]["content"]}
            )

        start = time.time()
        response = client.chat.completions.create(
            model=config.model,
            messages=api_messages,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
        latency = (time.time() - start) * 1000

        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0

        in_detail = getattr(usage, "prompt_tokens_details", None)
        input_breakdown = TokenBreakdown()
        if in_detail:
            input_breakdown = TokenBreakdown(
                text_tokens=getattr(in_detail, "text_tokens", 0) or 0,
                image_tokens=getattr(in_detail, "image_tokens", 0) or 0,
                audio_tokens=getattr(in_detail, "audio_tokens", 0) or 0,
                cached_tokens=getattr(in_detail, "cached_tokens", 0) or 0,
            )

        out_detail = getattr(usage, "completion_tokens_details", None)
        output_breakdown = TokenBreakdown()
        if out_detail:
            output_breakdown = TokenBreakdown(
                text_tokens=getattr(out_detail, "text_tokens", 0) or 0,
                audio_tokens=getattr(out_detail, "audio_tokens", 0) or 0,
            )

        input_price, output_price = PRICING.get(config.model, (2.50, 10.00))
        cost = (
            prompt_tokens * input_price + completion_tokens * output_price
        ) / 1_000_000

        finish_reason = ""
        if response.choices and response.choices[0].finish_reason:
            finish_reason = response.choices[0].finish_reason

        return ModelResponse(
            text=response.choices[0].message.content or "",
            total_input_tokens=prompt_tokens,
            total_output_tokens=completion_tokens,
            input_breakdown=input_breakdown,
            output_breakdown=output_breakdown,
            model=response.model,
            latency_ms=latency,
            finish_reason=finish_reason,
            cost=cost,
            raw_response=response.model_dump(),
        )
