import streamlit as st
import time
import base64
import io
from config import ProviderConfig, AppConfig
from providers import BaseProvider, ModelResponse, TokenBreakdown
from openai import OpenAI


class OpenAICompatibleProvider(BaseProvider):
    name = "OpenAI 兼容"
    icon = ":material/hub:"
    description = "Ollama / vLLM / LM Studio 等 OpenAI 兼容 API"
    supports_images = False

    def get_default_config(self) -> ProviderConfig:
        return ProviderConfig(
            base_url="http://localhost:11434/v1",
            api_key="ollama",
            model="llama3",
            temperature=0.7,
            max_tokens=4096,
        )

    def requires_api_key(self) -> bool:
        return False

    def get_default_base_url(self) -> str:
        return "http://localhost:11434/v1"

    def get_base_url_help(self) -> str | None:
        return "Ollama: http://localhost:11434/v1\nvLLM: http://localhost:8000/v1"

    def verify_config(self, config: ProviderConfig):
        if not config.base_url:
            raise Exception(
                "OpenAI 兼容 API Base URL 未设置。请在侧栏配置页填写后点击保存"
            )

    def get_config_summary(self, config: ProviderConfig):
        return [
            ("Base URL", config.base_url),
            ("Model", config.model),
        ]

    def render_post_config_info(self, config: ProviderConfig):
        st.caption(f"端点: {config.base_url or self.get_default_base_url()}")
        st.info("该供应商仅支持纯文本消息")

    def call_model(self, config: ProviderConfig, messages, images=None) -> ModelResponse:
        self.verify_config(config)

        client = OpenAI(api_key=config.api_key, base_url=config.base_url)

        api_messages = [
            {"role": msg["role"], "content": msg["content"]} for msg in messages
        ]

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

        return ModelResponse(
            text=response.choices[0].message.content or "",
            total_input_tokens=prompt_tokens,
            total_output_tokens=completion_tokens,
            input_breakdown=TokenBreakdown(text_tokens=prompt_tokens),
            output_breakdown=TokenBreakdown(text_tokens=completion_tokens),
            model=response.model or config.model,
            latency_ms=latency,
            finish_reason=getattr(response.choices[0], "finish_reason", "") or "",
            cost=0.0,
            raw_response=response.model_dump(),
        )
