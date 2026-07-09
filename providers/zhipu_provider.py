import streamlit as st
import time
import base64
import io
from config import ProviderConfig, AppConfig
from providers import BaseProvider, ModelResponse, TokenBreakdown
from openai import OpenAI


PRICING_CNY = {
    "glm-5.2": (50.0, 50.0),
    "glm-4-plus": (50.0, 50.0),
    "glm-4-flash": (0, 0),
    "glm-4-air": (1.0, 1.0),
    "glm-4-airx": (1.0, 1.0),
    "glm-4v-plus": (50.0, 50.0),
    "glm-4v-flash": (0, 0),
    "glm-zero-preview": (50.0, 50.0),
}

CNY_TO_USD = 0.14
DEFAULT_MODEL = "glm-5.2"
DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"


class ZhipuProvider(BaseProvider):
    name = "智谱AI"
    icon = ":material/globe_asia:"
    description = "智谱AI GLM 系列模型"

    def get_default_config(self) -> ProviderConfig:
        return ProviderConfig(
            model=DEFAULT_MODEL,
            base_url=DEFAULT_BASE_URL,
            temperature=0.7,
            max_tokens=4096,
        )

    def get_default_base_url(self) -> str:
        return DEFAULT_BASE_URL

    def get_api_key_help(self) -> str | None:
        return "在 https://open.bigmodel.cn 创建"

    def verify_config(self, config: ProviderConfig):
        if not config.api_key:
            raise Exception(
                "智谱AI API Key 未设置。请在侧栏「智谱AI」配置页填写后点击保存"
            )

    def get_config_summary(self, config: ProviderConfig):
        return [
            ("API Key", (config.api_key[:8] + "...") if config.api_key else "未设置"),
            ("Model", config.model),
            ("Base URL", config.base_url),
        ]

    def render_post_config_info(self, config: ProviderConfig):
        price = PRICING_CNY.get(config.model, None)
        if price:
            st.caption(
                f"参考价格 (每百万 tokens): 输入 ¥{price[0]}, 输出 ¥{price[1]} "
                f"(约 ${price[0] * CNY_TO_USD:.1f} / ${price[1] * CNY_TO_USD:.1f})"
            )
        else:
            st.caption("未匹配到已知模型的价格信息")
        st.info("该供应商与 OpenAI API 格式兼容，支持视觉模型（GLM-4V 系列）")

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

        price = PRICING_CNY.get(config.model)
        if price:
            input_price, output_price = price
            cost_cny = (
                prompt_tokens * input_price + completion_tokens * output_price
            ) / 1_000_000
            cost = cost_cny * CNY_TO_USD
        else:
            cost = 0.0

        finish_reason = ""
        if response.choices and response.choices[0].finish_reason:
            finish_reason = response.choices[0].finish_reason

        return ModelResponse(
            text=response.choices[0].message.content or "",
            total_input_tokens=prompt_tokens,
            total_output_tokens=completion_tokens,
            input_breakdown=input_breakdown,
            output_breakdown=output_breakdown,
            model=response.model or config.model,
            latency_ms=latency,
            finish_reason=finish_reason,
            cost=cost,
            raw_response=response.model_dump(),
        )
