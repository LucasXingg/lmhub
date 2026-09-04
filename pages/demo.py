import streamlit as st
from PIL import Image
from config import AppConfig
from prompt_input import render_prompt_input, resolve_prompt
from prompt_templates import render_template_bar
from providers import discover_providers
from image_processor import process_image, render_settings, ALL_METHODS
from usage_view import render_usage

st.set_page_config(page_title="LMHub Demo", page_icon="🧪", layout="wide")

providers = discover_providers()
if not providers:
    st.error("未发现任何供应商，请在 providers/ 目录下添加供应商文件")
    st.stop()

app_config = AppConfig.load()
provider_names = list(providers.keys())

with st.sidebar:
    render_settings()

selected_name = st.selectbox(
    "选择供应商",
    provider_names,
    key="demo_selected_provider",
    help="在侧栏「Providers」中配置各供应商的 API Key",
)
selected = providers[selected_name]

profiles = app_config.list_profiles(selected.name)
if not profiles:
    profiles = ["默认"]
    app_config.get_profile(selected.name, "默认")
profile_key = f"demo_profile_{selected.name}"
selected_profile = st.selectbox(
    "配置方案",
    profiles,
    key=profile_key,
)
config = app_config.get_profile(selected.name, selected_profile)

with st.expander(f"📋 {selected_name} / {selected_profile} 当前配置", expanded=False):
    summary = selected.get_config_summary(config)
    if summary:
        for label, value in summary:
            st.write(f"**{label}**:", value)
    else:
        st.info("自定义供应商")

render_template_bar(
    "demo",
    "demo_system",
    "demo_user",
    "demo_system_mode",
    "demo_user_mode",
)

system_raw, system_mode = render_prompt_input(
    "系统提示词 (System Prompt)",
    "demo_system",
    "demo_system_mode",
    height=100,
    default_text="你是一个有帮助的 AI 助手。",
)
user_raw, user_mode = render_prompt_input(
    "用户消息",
    "demo_user",
    "demo_user_mode",
    height=100,
    default_text="你好，请介绍一下你自己。",
)

if selected.supports_images:
    uploaded_files = st.file_uploader(
        "上传图片",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key="demo_images",
    )
else:
    uploaded_files = None
    st.caption(f"ℹ️ {selected_name} 不支持图片输入")

col1, col2, col3 = st.columns([1, 1, 6])
with col1:
    send_btn = st.button("发送", type="primary", width="stretch")
with col2:
    clear_btn = st.button("清空结果", width="stretch")

if clear_btn:
    for key in list(st.session_state.keys()):
        if key.startswith("demo_result_"):
            del st.session_state[key]

if uploaded_files:
    with st.expander(f"📷 已上传 {len(uploaded_files)} 张图片", expanded=True):
        cols = st.columns(min(len(uploaded_files), 6))
        for i, file in enumerate(uploaded_files[:6]):
            with cols[i]:
                img = Image.open(file)
                st.image(img, width="stretch")
                w, h = img.size
                st.caption(f"{w} × {h}")
        if len(uploaded_files) > 6:
            st.caption(f"... 还有 {len(uploaded_files) - 6} 张图片")

if send_btn:
    image_count = len(uploaded_files) if uploaded_files else 0
    prompt_context = {"image_count": image_count}
    system_prompt = resolve_prompt(
        system_raw, system_mode, prompt_context, label="系统提示词"
    )
    user_message = resolve_prompt(
        user_raw, user_mode, prompt_context, label="用户消息"
    )
    if system_prompt is None or user_message is None:
        st.stop()
    if not user_message.strip():
        st.warning("请输入消息内容")
        st.stop()

    messages = []
    if system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt.strip()})
    messages.append({"role": "user", "content": user_message.strip()})

    images = []
    if uploaded_files and selected.supports_images:
        for file in uploaded_files:
            img = Image.open(file)
            proc_enabled = st.session_state.get("img_proc_enable", False)
            if proc_enabled:
                method = st.session_state.get("img_proc_method", ALL_METHODS[0])
                w = st.session_state.get("img_proc_w", 512)
                h = st.session_state.get("img_proc_h", 512)
                keep_aspect = st.session_state.get("img_proc_aspect", True)
                img = process_image(img, method, w, h, keep_aspect)
            else:
                img = img.convert("RGB")
            images.append(img)

    with st.spinner(f"正在调用 {selected_name} / {selected_profile} ..."):
        try:
            config = app_config.get_profile(selected.name, selected_profile)
            response = selected.call_model(
                config, messages, images if images else None
            )
        except Exception as e:
            st.error(f"调用失败: {str(e)}")
            st.stop()

    st.session_state["demo_result_text"] = response.text
    st.session_state["demo_result_response"] = response

if "demo_result_response" not in st.session_state:
    st.stop()

response = st.session_state["demo_result_response"]
text = st.session_state["demo_result_text"]

st.divider()
st.subheader("📤 模型回复")
st.markdown(text)

render_usage(response)
