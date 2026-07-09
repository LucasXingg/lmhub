import streamlit as st
import time
import base64
import io
import json
import requests
from config import ProviderConfig, AppConfig
from providers import BaseProvider, ExtraField, ModelResponse, TokenBreakdown


PRICING_CNY = {
    "doubao-seed-2-0-mini-260428": (0.8, 2.0),
    "doubao-seed-2-0-pro-260428": (4.0, 16.0),
    "doubao-seed-2-0-260428": (4.0, 16.0),
    "doubao-seed-1-6-250615": (4.0, 16.0),
    "doubao-seed-1-6-lite-250615": (0.8, 2.0),
    "doubao-seed-1-6-flash-250615": (0.3, 0.6),
}

CNY_TO_USD = 0.14
DEFAULT_MODEL = "doubao-seed-2-0-mini-260428"
DEFAULT_ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/responses"


class ArkProvider(BaseProvider):
    name = "火山方舟 (Ark)"
    icon = ":material/volcano:"
    description = "字节跳动豆包大模型 (volcengine ark)"

    def get_default_config(self) -> ProviderConfig:
        return ProviderConfig(
            model=DEFAULT_MODEL,
            base_url=DEFAULT_ENDPOINT,
            temperature=0.7,
            max_tokens=4096,
            extra={
                "thinking": "disabled",
                "structured_output": False,
                "image_detail": "high",
            },
        )

    def get_default_base_url(self) -> str:
        return DEFAULT_ENDPOINT

    def get_api_key_help(self) -> str | None:
        return "https://console.volcengine.com/ark/ → API Key 管理"

    def get_temperature_range(self) -> tuple[float, float, float]:
        return (0.0, 1.0, 0.1)

    def get_max_tokens_range(self) -> tuple[int, int, int]:
        return (256, 32768, 256)

    def get_extra_fields(self) -> list[ExtraField]:
        return [
            ExtraField(
                key="thinking",
                label="启用深度思考 (Thinking)",
                type="checkbox",
                default=False,
                true_value="enabled",
                false_value="disabled",
                help="模型在回答前会进行内部推理；禁用可减少延迟和 token 消耗",
            ),
            ExtraField(
                key="structured_output",
                label="结构化输出 (JSON Object)",
                type="checkbox",
                default=False,
                help="强制模型以 JSON 格式返回（提示词中需包含格式要求）",
            ),
            ExtraField(
                key="image_detail",
                label="图片理解精细度",
                type="select",
                options=["low", "high", "xhigh"],
                option_labels=["低 (low)", "中 (high)", "高 (xhigh)"],
                default="high",
                help="控制模型理解图片的精细程度：低=快速省 token，高=更细致的图片理解",
            ),
        ]

    def verify_config(self, config: ProviderConfig):
        if not config.api_key:
            raise Exception(
                "火山方舟 API Key 未设置。请在侧栏「火山方舟 (Ark)」配置页填写后点击保存"
            )

    def get_config_summary(self, config: ProviderConfig):
        return [
            ("API Key", (config.api_key[:8] + "...") if config.api_key else "未设置"),
            ("Model", config.model),
            ("Thinking", "启用" if config.extra.get("thinking") == "enabled" else "禁用"),
            ("结构化输出", "启用" if config.extra.get("structured_output") else "禁用"),
            ("图片精细度", {"low": "低", "high": "中", "xhigh": "高"}.get(config.extra.get("image_detail", ""), "")),
        ]

    def render_post_config_info(self, config: ProviderConfig):
        price = PRICING_CNY.get(config.model, (4.0, 16.0))
        st.caption(
            f"参考价格 (每百万 tokens): 输入 ¥{price[0]}, 输出 ¥{price[1]} "
            f"(约 ${price[0] * CNY_TO_USD:.1f} / ${price[1] * CNY_TO_USD:.1f})"
        )

    def call_model(self, config: ProviderConfig, messages, images=None) -> ModelResponse:
        self.verify_config(config)

        payload = {
            "model": config.model,
            "input": self._build_input(
                messages, images, config.extra.get("image_detail", "high")
            ),
            "max_output_tokens": config.max_tokens,
            "temperature": config.temperature,
        }

        if config.extra.get("thinking", "disabled") == "enabled":
            payload["thinking"] = {"type": "enabled"}
        else:
            payload["thinking"] = {"type": "disabled"}

        if config.extra.get("structured_output", False):
            payload["text"] = {"format": {"type": "json_object"}}

        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }

        start = time.time()
        resp = requests.post(config.base_url, json=payload, headers=headers, timeout=120)
        latency = (time.time() - start) * 1000

        if not resp.ok:
            try:
                detail = resp.json()
            except (json.JSONDecodeError, ValueError):
                detail = resp.text
            raise Exception(f"API 错误 ({resp.status_code}): {detail}")

        data = resp.json()
        return self._parse_response(data, config.model, latency)

    def _build_input(self, messages, images, image_detail="high"):
        input_list = []
        for i, msg in enumerate(messages):
            role = msg["role"]
            content = msg["content"]
            is_last = i == len(messages) - 1
            has_images = images and role == "user" and is_last
            if has_images:
                parts = []
                for img in images:
                    buf = io.BytesIO()
                    img.save(buf, format="PNG", optimize=True)
                    b64 = base64.b64encode(buf.getvalue()).decode()
                    parts.append(
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{b64}",
                            "detail": image_detail,
                        }
                    )
                parts.append({"type": "input_text", "text": content})
                input_list.append({"role": role, "content": parts})
            else:
                input_list.append({"role": role, "content": content})
        return input_list

    def _parse_response(self, data, model, latency):
        text = ""
        output_list = data.get("output", [])
        for item in output_list:
            if item.get("type") == "message":
                for block in item.get("content", []):
                    if block.get("type") == "output_text":
                        text += block.get("text", "")

        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        in_detail = usage.get("input_tokens_details") or {}
        out_detail = usage.get("output_tokens_details") or {}

        input_breakdown = TokenBreakdown(
            text_tokens=in_detail.get("text_tokens", 0) or 0,
            image_tokens=in_detail.get("image_tokens", 0) or 0,
            audio_tokens=in_detail.get("audio_tokens", 0) or 0,
            cached_tokens=in_detail.get("cached_tokens", 0) or 0,
        )
        output_breakdown = TokenBreakdown(
            text_tokens=out_detail.get("text_tokens", 0) or 0,
            audio_tokens=out_detail.get("audio_tokens", 0) or 0,
        )

        input_price, output_price = PRICING_CNY.get(model, (4.0, 16.0))
        cost_cny = (
            input_tokens * input_price + output_tokens * output_price
        ) / 1_000_000
        cost_usd = cost_cny * CNY_TO_USD

        finish_reason = ""
        if output_list:
            last_item = output_list[-1]
            finish_reason = last_item.get("status", "")

        return ModelResponse(
            text=text,
            total_input_tokens=input_tokens,
            total_output_tokens=output_tokens,
            input_breakdown=input_breakdown,
            output_breakdown=output_breakdown,
            model=data.get("model", model),
            latency_ms=latency,
            finish_reason=finish_reason,
            cost=cost_usd,
            raw_response=data,
        )
