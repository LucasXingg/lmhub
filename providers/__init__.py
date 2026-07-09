from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import Any
import re
import sys
from pathlib import Path
import importlib

from config import ProviderConfig, AppConfig


@dataclass
class TokenBreakdown:
    text_tokens: int = 0
    image_tokens: int = 0
    audio_tokens: int = 0
    cached_tokens: int = 0


@dataclass
class ModelResponse:
    text: str
    total_input_tokens: int
    total_output_tokens: int
    input_breakdown: TokenBreakdown = field(default_factory=TokenBreakdown)
    output_breakdown: TokenBreakdown = field(default_factory=TokenBreakdown)
    model: str = ""
    latency_ms: float = 0.0
    finish_reason: str = ""
    cost: float = 0.0
    raw_response: dict = field(default_factory=dict)


@dataclass
class ExtraField:
    key: str
    label: str
    type: str = "text"
    default: Any = None
    help: str = ""
    options: list[str] | None = None
    option_labels: list[str] | None = None
    min_val: float | None = None
    max_val: float | None = None
    step: float = 1.0
    true_value: Any = True
    false_value: Any = False


class BaseProvider(ABC):
    name: str = "Base"
    icon: str = "🔌"
    description: str = ""
    supports_images: bool = True

    @abstractmethod
    def get_default_config(self) -> ProviderConfig:
        """Return default config for this provider (model, endpoint, etc.)."""

    @abstractmethod
    def call_model(self, config: ProviderConfig, messages, images=None) -> ModelResponse:
        """Call the model API using values from config. Returns ModelResponse or raises."""

    def verify_config(self, config: ProviderConfig):
        """Validate config. Raise on missing required fields."""

    def get_config_summary(self, config: ProviderConfig) -> list[tuple[str, str]]:
        """Return (label, value) pairs for display in demo page."""
        return []

    # ------------------------------------------------------------------
    # Hook methods — override in subclass to customize unified config_page
    # ------------------------------------------------------------------

    def get_model_options(self) -> list[str] | None:
        return None

    def get_default_base_url(self) -> str:
        return self.get_default_config().base_url

    def get_api_key_help(self) -> str | None:
        return None

    def get_base_url_help(self) -> str | None:
        return None

    def requires_api_key(self) -> bool:
        return True

    def show_temperature(self) -> bool:
        return True

    def get_temperature_range(self) -> tuple[float, float, float]:
        return (0.0, 2.0, 0.1)

    def get_max_tokens_range(self) -> tuple[int, int, int]:
        return (256, 128000, 256)

    def get_extra_fields(self) -> list[ExtraField]:
        return []

    def render_post_config_info(self, config: ProviderConfig):
        pass

    # ------------------------------------------------------------------
    # Unified config page (template method)
    # ------------------------------------------------------------------

    def config_page(self, _config: ProviderConfig, app_config: AppConfig):
        import streamlit as st

        profile_name, config = self.render_profile_selector(app_config)
        pfx = self.profile_prefix(profile_name)

        st.title(f"{self.name} 配置")
        st.caption(f"当前方案: **{profile_name}**")

        if self.requires_api_key():
            st.text_input(
                "API Key",
                value=config.api_key,
                type="password",
                key=f"{pfx}api_key",
                help=self.get_api_key_help() or None,
            )

        default_url = self.get_default_base_url()
        if default_url:
            st.text_input(
                "Base URL / API Endpoint",
                value=config.base_url or default_url,
                key=f"{pfx}base_url",
                help=self.get_base_url_help() or None,
            )

        models = self.get_model_options()
        if models:
            try:
                idx = models.index(config.model)
            except ValueError:
                idx = models.index(self.get_default_config().model)
            st.selectbox("模型", models, index=idx, key=f"{pfx}model")
        else:
            st.text_input(
                "模型名称",
                value=config.model or self.get_default_config().model,
                key=f"{pfx}model",
            )

        if self.show_temperature():
            col1, col2 = st.columns(2)
            t_min, t_max, t_step = self.get_temperature_range()
            with col1:
                st.slider(
                    "Temperature",
                    t_min,
                    t_max,
                    value=config.temperature,
                    step=t_step,
                    key=f"{pfx}temperature",
                )
            with col2:
                tk_min, tk_max, tk_step = self.get_max_tokens_range()
                st.number_input(
                    "Max Tokens",
                    tk_min,
                    tk_max,
                    value=config.max_tokens,
                    step=tk_step,
                    key=f"{pfx}max_tokens",
                )
        else:
            tk_min, tk_max, tk_step = self.get_max_tokens_range()
            st.number_input(
                "Max Tokens",
                tk_min,
                tk_max,
                value=config.max_tokens,
                step=tk_step,
                key=f"{pfx}max_tokens",
            )

        extra_fields = self.get_extra_fields()
        if extra_fields:
            st.divider()
            st.subheader("高级选项")
            for field in extra_fields:
                session_key = f"{pfx}{field.key}"
                raw = config.extra.get(field.key, field.default)
                if field.type == "checkbox":
                    checked = raw in (field.true_value, True) if field.true_value is not True else bool(raw)
                    st.checkbox(
                        field.label,
                        value=checked,
                        key=session_key,
                        help=field.help or None,
                    )
                elif field.type == "select":
                    try:
                        idx = field.options.index(raw) if field.options else 0
                    except ValueError:
                        idx = 0
                    fmt_func = None
                    if field.option_labels and field.options:
                        label_map = dict(zip(field.options, field.option_labels))
                        fmt_func = lambda v: label_map.get(v, v)
                    st.selectbox(
                        field.label,
                        options=field.options or [],
                        index=idx,
                        format_func=fmt_func,
                        key=session_key,
                        help=field.help or None,
                    )
                elif field.type == "slider":
                    st.slider(
                        field.label,
                        field.min_val or 0,
                        field.max_val or 100,
                        value=raw,
                        step=field.step or 1.0,
                        key=session_key,
                        help=field.help or None,
                    )
                else:
                    st.text_input(
                        field.label,
                        value=str(raw) if raw is not None else "",
                        key=session_key,
                        help=field.help or None,
                    )

        st.divider()

        col_save, col_test = st.columns(2)
        with col_save:
            if st.button("保存配置", key=f"{pfx}save", width="stretch"):
                if self.requires_api_key():
                    config.api_key = st.session_state[f"{pfx}api_key"]
                if default_url:
                    config.base_url = st.session_state[f"{pfx}base_url"]
                config.model = st.session_state[f"{pfx}model"]
                if self.show_temperature():
                    config.temperature = st.session_state[f"{pfx}temperature"]
                config.max_tokens = st.session_state[f"{pfx}max_tokens"]

                for field in extra_fields:
                    session_key = f"{pfx}{field.key}"
                    raw = st.session_state.get(session_key, field.default)
                    if field.type == "checkbox":
                        config.extra[field.key] = field.true_value if raw else field.false_value
                    else:
                        config.extra[field.key] = raw

                app_config.save()
                st.success("配置已保存!")

        with col_test:
            if st.button("测试连接", key=f"{pfx}test_conn", width="stretch"):
                with st.spinner("测试中..."):
                    self.test_connection(config)

        if self.requires_api_key():
            if config.api_key:
                st.success("API Key 已设置")
            else:
                st.warning("请设置 API Key")

        self.render_post_config_info(config)

    # ------------------------------------------------------------------
    # Unified test connection — delegates to call_model
    # ------------------------------------------------------------------

    def test_connection(self, config: ProviderConfig):
        import streamlit as st

        original = config.max_tokens
        try:
            config.max_tokens = 10
            response = self.call_model(config, [{"role": "user", "content": "hi"}])
            st.success(f"连接成功! 模型: {response.model or config.model}")
            total = response.total_input_tokens + response.total_output_tokens
            if total:
                st.caption(f"测试消耗: {total} tokens")
        except Exception as e:
            st.error(f"连接失败: {e}")
        finally:
            config.max_tokens = original

    # ------------------------------------------------------------------
    # Helper utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_key(text: str) -> str:
        return re.sub(r"\W+", "_", text).strip("_").lower()

    def profile_prefix(self, profile_name: str) -> str:
        return f"{self._safe_key(self.name)}_{self._safe_key(profile_name)}_"

    def _profile_session_key(self) -> str:
        return f"profile_{self._safe_key(self.name)}"

    def render_profile_selector(self, app_config: AppConfig) -> tuple[str, ProviderConfig]:
        import streamlit as st

        profiles = app_config.list_profiles(self.name)
        if not profiles:
            profiles = ["默认"]
            app_config.get_profile(self.name, "默认")

        session_key = self._profile_session_key()
        if session_key not in st.session_state:
            st.session_state[session_key] = profiles[0]

        current = st.session_state[session_key]
        if current not in profiles:
            current = profiles[0]
            st.session_state[session_key] = current

        col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
        with col1:
            selected = st.selectbox(
                "配置方案",
                profiles,
                index=profiles.index(current),
                key=f"{session_key}_select",
            )
        with col2:
            st.button("新建", key=f"{session_key}_new_btn", width="stretch")
        with col3:
            st.button("重命名", key=f"{session_key}_rename_btn", width="stretch")
        with col4:
            if len(profiles) > 1:
                st.button("删除", key=f"{session_key}_del_btn", width="stretch")

        if st.session_state.get(f"{session_key}_new_btn"):
            st.session_state[f"{session_key}_creating"] = True

        if st.session_state.get(f"{session_key}_creating"):
            with st.container(border=True):
                new_name = st.text_input(
                    "新方案名称",
                    key=f"{session_key}_new_name",
                    placeholder="输入名称...",
                )
                c1, c2 = st.columns([1, 1])
                with c1:
                    if st.button("确认", key=f"{session_key}_confirm_new"):
                        name = new_name.strip()
                        if not name:
                            st.error("名称不能为空")
                        elif name in profiles:
                            st.error(f"方案「{name}」已存在")
                        else:
                            app_config.clone_profile(self.name, current, name)
                            app_config.save()
                            st.session_state[session_key] = name
                            st.session_state.pop(f"{session_key}_creating")
                            st.rerun()
                with c2:
                    if st.button("取消", key=f"{session_key}_cancel_new"):
                        st.session_state.pop(f"{session_key}_creating")
                        st.rerun()

        if st.session_state.get(f"{session_key}_rename_btn"):
            st.session_state[f"{session_key}_renaming"] = True

        if st.session_state.get(f"{session_key}_renaming"):
            with st.container(border=True):
                new_name = st.text_input(
                    "新名称",
                    value=current,
                    key=f"{session_key}_rename_name",
                )
                r1, r2 = st.columns([1, 1])
                with r1:
                    if st.button("确认", key=f"{session_key}_confirm_rename"):
                        name = new_name.strip()
                        if not name:
                            st.error("名称不能为空")
                        elif name == current:
                            st.session_state.pop(f"{session_key}_renaming")
                            st.rerun()
                        elif name in profiles:
                            st.error(f"方案「{name}」已存在")
                        else:
                            app_config.rename_profile(self.name, current, name)
                            app_config.save()
                            st.session_state[session_key] = name
                            st.session_state.pop(f"{session_key}_renaming")
                            st.rerun()
                with r2:
                    if st.button("取消", key=f"{session_key}_cancel_rename"):
                        st.session_state.pop(f"{session_key}_renaming")
                        st.rerun()

        if st.session_state.get(f"{session_key}_del_btn"):
            st.session_state[f"{session_key}_deleting"] = True

        if st.session_state.get(f"{session_key}_deleting"):
            with st.container(border=True):
                st.warning(f"确定删除方案「{current}」？此操作不可撤销。")
                d1, d2 = st.columns([1, 1])
                with d1:
                    if st.button("确认删除", key=f"{session_key}_confirm_del"):
                        app_config.delete_profile(self.name, current)
                        app_config.save()
                        remaining = app_config.list_profiles(self.name)
                        st.session_state[session_key] = (
                            remaining[0] if remaining else "默认"
                        )
                        st.session_state.pop(f"{session_key}_deleting")
                        st.rerun()
                with d2:
                    if st.button("取消", key=f"{session_key}_cancel_del"):
                        st.session_state.pop(f"{session_key}_deleting")
                        st.rerun()

        if selected != current:
            st.session_state[session_key] = selected
            st.rerun()

        config = app_config.get_profile(self.name, current)
        return current, config


PROVIDER_REGISTRY: dict[str, BaseProvider] = {}


def discover_providers() -> dict[str, BaseProvider]:
    """Scan providers/ directory for *_provider.py files, import and register them."""
    PROVIDER_REGISTRY.clear()
    providers_dir = Path(__file__).parent

    for file in sorted(providers_dir.glob("*_provider.py")):
        module_name = f"providers.{file.stem}"
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])
        try:
            module = importlib.import_module(module_name)
        except ImportError as e:
            import streamlit as st
            st.sidebar.warning(f"无法加载供应商模块 {file.stem}: {e}")
            continue

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseProvider)
                and attr != BaseProvider
            ):
                instance = attr()
                PROVIDER_REGISTRY[instance.name] = instance

    return PROVIDER_REGISTRY
