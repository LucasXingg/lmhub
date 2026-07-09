import streamlit as st
import json
from pathlib import Path
from PIL import Image
from config import AppConfig
from providers import discover_providers
from image_processor import process_image, render_settings, ALL_METHODS

TEMPLATES_PATH = Path("configs/prompt_templates.json")


def load_templates():
    if TEMPLATES_PATH.exists():
        try:
            data = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
            return data.get("templates", [])
        except (json.JSONDecodeError, KeyError):
            return []
    return []


def save_templates(templates):
    TEMPLATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATES_PATH.write_text(
        json.dumps({"templates": templates}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


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

templates = load_templates()

if "demo_system" not in st.session_state:
    st.session_state["demo_system"] = "你是一个有帮助的 AI 助手。"
if "demo_user" not in st.session_state:
    st.session_state["demo_user"] = "你好，请介绍一下你自己。"

template_names = ["不使用模板"] + [t["name"] for t in templates]
col_t1, col_t2, col_t3, col_t4 = st.columns([7, 1, 1, 1])
with col_t1:
    selected_template_name = st.selectbox(
        "提示词模板",
        template_names,
        key="demo_template_select",
        help="选择已保存的模板，点击右侧按钮应用或管理",
    )
with col_t2:
    apply_btn = st.button("应用模板", key="demo_apply_btn", width="stretch")
with col_t3:
    manage_btn = st.button("管理模板", key="demo_manage_btn", width="stretch")
with col_t4:
    save_btn = st.button("💾 保存为模板", key="demo_save_btn", width="stretch")

if apply_btn:
    if selected_template_name == "不使用模板":
        st.warning("请先选择一个提示词模板")
    else:
        for t in templates:
            if t["name"] == selected_template_name:
                st.session_state["demo_system"] = t.get("content", "")
                st.session_state["demo_user"] = t.get("user_message", "")
                st.rerun()
                break

if manage_btn:
    st.session_state["demo_show_manage"] = (
        not st.session_state.get("demo_show_manage", False)
    )

if st.session_state.get("demo_show_manage", False):
    with st.container(border=True):
        st.caption("模板管理")
        if not templates:
            st.info("暂无已保存的模板")
        else:
            for idx, t in enumerate(templates):
                col_m1, col_m2 = st.columns([11, 1])
                with col_m1:
                    content_preview = (
                        t.get("content", "")[:50] + "..."
                        if len(t.get("content", "")) > 50
                        else t.get("content", "")
                    )
                    user_preview = (
                        t.get("user_message", "")[:40] + "..."
                        if len(t.get("user_message", "")) > 40
                        else t.get("user_message", "")
                    )
                    st.caption(
                        f"**{t['name']}**  |  系统: {content_preview}  |  用户: {user_preview}"
                    )
                with col_m2:
                    if st.button(
                        "🗑️",
                        key=f"demo_delete_tpl_{idx}",
                        help=f"删除模板「{t['name']}」",
                    ):
                        del templates[idx]
                        save_templates(templates)
                        st.rerun()
        col_mc1, col_mc2 = st.columns([1, 1])
        with col_mc1:
            if st.button("关闭", key="demo_close_manage", width="stretch"):
                st.session_state["demo_show_manage"] = False
                st.rerun()

if save_btn:
    st.session_state["demo_show_save"] = True

if st.session_state.get("demo_show_save", False):
    with st.container(border=True):
        template_name = st.text_input(
            "模板名称",
            placeholder="输入模板名称...",
            key="demo_template_name",
        )
        sys_full = st.session_state.get("demo_system", "")
        usr_full = st.session_state.get("demo_user", "")
        sys_preview = sys_full[:80] + "..." if len(sys_full) > 80 else sys_full
        usr_preview = usr_full[:80] + "..." if len(usr_full) > 80 else usr_full
        st.caption(f"系统提示词: {sys_preview if sys_preview else '(空)'}")
        st.caption(f"用户消息: {usr_preview if usr_preview else '(空)'}")
        col_s1, col_s2 = st.columns([1, 1])
        with col_s1:
            if st.button("确认保存", key="demo_confirm_save"):
                name = template_name.strip()
                if not name:
                    st.error("请输入模板名称")
                elif any(t["name"] == name for t in templates):
                    st.error(f"模板「{name}」已存在，请使用其他名称")
                else:
                    templates.append(
                        {
                            "name": name,
                            "content": st.session_state.get("demo_system", ""),
                            "user_message": st.session_state.get("demo_user", ""),
                        }
                    )
                    save_templates(templates)
                    st.session_state["demo_show_save"] = False
                    st.success(f"模板「{name}」已保存")
                    st.rerun()
        with col_s2:
            if st.button("取消", key="demo_cancel_save"):
                st.session_state["demo_show_save"] = False
                st.rerun()

system_prompt = st.text_area(
    "系统提示词 (System Prompt)",
    height=100,
    key="demo_system",
)

user_message = st.text_area(
    "用户消息",
    height=100,
    key="demo_user",
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

st.divider()
st.subheader("📊 用量与元信息")

col_a, col_b, col_c, col_d = st.columns(4)
with col_a:
    st.metric("模型", response.model)
with col_b:
    st.metric("⏱️ 延迟", f"{response.latency_ms:.0f} ms")
with col_c:
    st.metric("🏁 结束原因", response.finish_reason or "N/A")
with col_d:
    st.metric("💰 预估费用", f"${response.cost:.6f}" if response.cost else "N/A")

st.divider()
st.subheader("🔢 Token 用量")

col_in, col_out, col_total = st.columns(3)
with col_in:
    st.metric("📥 输入 Total", f"{response.total_input_tokens:,}")
with col_out:
    st.metric("📤 输出 Total", f"{response.total_output_tokens:,}")
with col_total:
    total = response.total_input_tokens + response.total_output_tokens
    st.metric("🔢 合计", f"{total:,}")

ib = response.input_breakdown
ob = response.output_breakdown

has_breakdown = any(
    [
        ib.text_tokens > 0 or ib.cached_tokens > 0,
        ib.image_tokens > 0,
        ib.audio_tokens > 0,
        ob.text_tokens > 0,
        ob.audio_tokens > 0,
    ]
)

if has_breakdown:
    st.markdown("**按模态细分**")

    header_cols = st.columns(5)
    header_cols[0].markdown("**模态**")
    header_cols[1].markdown("**输入**")
    header_cols[2].markdown("**输出**")
    header_cols[3].markdown("**合计**")
    header_cols[4].markdown("")

    rows = []
    if ib.text_tokens > 0 or ob.text_tokens > 0:
        rows.append(("📝 文本", ib.text_tokens, ob.text_tokens))
    if ib.image_tokens > 0 or ob.image_tokens > 0:
        rows.append(("🖼️ 图片", ib.image_tokens, ob.image_tokens))
    if ib.audio_tokens > 0 or ob.audio_tokens > 0:
        rows.append(("🎵 音频", ib.audio_tokens, ob.audio_tokens))
    if ib.cached_tokens > 0:
        rows.append(("⚡ 缓存", ib.cached_tokens, 0))

    for label, inp, outp in rows:
        cols = st.columns(5)
        cols[0].markdown(label)
        cols[1].markdown(f"{inp:,}" if inp else "0")
        cols[2].markdown(f"{outp:,}" if outp else "0")
        cols[3].markdown(f"{inp + outp:,}")
        ratio = (
            f"{inp / response.total_input_tokens * 100:.1f}%"
            if response.total_input_tokens > 0 and inp > 0
            else ""
        )
        cols[4].markdown(ratio)

    st.divider()
    sum_cols = st.columns(5)
    sum_cols[0].markdown("**合计**")
    sum_cols[1].markdown(f"**{response.total_input_tokens:,}**")
    sum_cols[2].markdown(f"**{response.total_output_tokens:,}**")
    sum_cols[3].markdown(f"**{total:,}**")
    sum_cols[4].markdown("100%")
else:
    st.info("该供应商不返回按模态细分的 Token 数据")

if response.raw_response:
    with st.expander("📄 原始 JSON 响应数据", expanded=False):
        st.code(
            json.dumps(response.raw_response, indent=2, ensure_ascii=False),
            language="json",
        )
