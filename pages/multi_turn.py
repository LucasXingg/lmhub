import streamlit as st
import json
from pathlib import Path
from config import AppConfig
from providers import discover_providers, MultiTurnContext
from image_processor import render_settings

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


def _apply_template():
    selected = st.session_state.get("mt_template_select", "不使用模板")
    if selected == "不使用模板":
        return
    templates = load_templates()
    for t in templates:
        if t["name"] == selected:
            st.session_state["mt_system"] = t.get("content", "")
            break


def _clear_context():
    st.session_state["mt_context"] = MultiTurnContext()
    st.session_state["mt_system"] = ""


st.set_page_config(page_title="LMHub Multi-Turn", page_icon="🔄", layout="wide")

providers = discover_providers()
if not providers:
    st.error("未发现任何供应商，请在 providers/ 目录下添加供应商文件")
    st.stop()

app_config = AppConfig.load()
provider_names = list(providers.keys())

with st.sidebar:
    render_settings()

ark_name = "火山方舟 (Ark)"
default_idx = 0
try:
    default_idx = provider_names.index(ark_name)
except ValueError:
    default_idx = 0

selected_name = st.selectbox(
    "选择供应商",
    provider_names,
    index=default_idx,
    key="mt_selected_provider",
    help="多轮对话的上下文由供应商内部维护，页面仅负责展示",
)
selected = providers[selected_name]

if not selected.supports_multi_turn():
    st.warning(f"{selected_name} 暂不支持多轮对话管理，请选择其他供应商")
    st.stop()

profiles = app_config.list_profiles(selected.name)
if not profiles:
    profiles = ["默认"]
    app_config.get_profile(selected.name, "默认")
profile_key = f"mt_profile_{selected.name}"
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

if "mt_context" not in st.session_state:
    st.session_state["mt_context"] = MultiTurnContext()
if "mt_raw_rounds" not in st.session_state:
    st.session_state["mt_raw_rounds"] = set()
if "mt_system" not in st.session_state:
    st.session_state["mt_system"] = ""

context = st.session_state["mt_context"]

system_prompt = st.text_area(
    "系统提示词 (可选，仅首轮生效)",
    height=68,
    key="mt_system",
    value=context.system_prompt,
    help="系统提示词仅在首轮对话中发送；后续轮次由供应商内部维护上下文",
)

templates = load_templates()
template_names = ["不使用模板"] + [t["name"] for t in templates]
col_t1, col_t2, col_t3, col_t4 = st.columns([7, 1, 1, 1])
with col_t1:
    selected_template_name = st.selectbox(
        "提示词模板",
        template_names,
        key="mt_template_select",
        help="选择已保存的模板，点击右侧按钮应用或管理",
    )
with col_t2:
    apply_btn = st.button("应用模板", key="mt_apply_btn", width="stretch", on_click=_apply_template)
with col_t3:
    manage_btn = st.button("管理模板", key="mt_manage_btn", width="stretch")
with col_t4:
    save_btn = st.button("💾 保存为模板", key="mt_save_btn", width="stretch")

if apply_btn:
    if selected_template_name == "不使用模板":
        st.warning("请先选择一个提示词模板")

if manage_btn:
    st.session_state["mt_show_manage"] = (
        not st.session_state.get("mt_show_manage", False)
    )

if st.session_state.get("mt_show_manage", False):
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
                    st.caption(f"**{t['name']}**  |  系统提示词: {content_preview}")
                with col_m2:
                    if st.button(
                        "🗑️",
                        key=f"mt_delete_tpl_{idx}",
                        help=f"删除模板「{t['name']}」",
                    ):
                        del templates[idx]
                        save_templates(templates)
                        st.rerun()
        col_mc1, col_mc2 = st.columns([1, 1])
        with col_mc1:
            if st.button("关闭", key="mt_close_manage", width="stretch"):
                st.session_state["mt_show_manage"] = False
                st.rerun()

if save_btn:
    st.session_state["mt_show_save"] = True

if st.session_state.get("mt_show_save", False):
    with st.container(border=True):
        template_name = st.text_input(
            "模板名称",
            placeholder="输入模板名称...",
            key="mt_template_name",
        )
        sys_full = st.session_state.get("mt_system", "")
        sys_preview = sys_full[:80] + "..." if len(sys_full) > 80 else sys_full
        st.caption(f"系统提示词: {sys_preview if sys_preview else '(空)'}")
        col_s1, col_s2 = st.columns([1, 1])
        with col_s1:
            if st.button("确认保存", key="mt_confirm_save"):
                name = template_name.strip()
                if not name:
                    st.error("请输入模板名称")
                elif any(t["name"] == name for t in templates):
                    st.error(f"模板「{name}」已存在，请使用其他名称")
                else:
                    templates.append(
                        {
                            "name": name,
                            "content": st.session_state.get("mt_system", ""),
                            "user_message": "",
                        }
                    )
                    save_templates(templates)
                    st.session_state["mt_show_save"] = False
                    st.success(f"模板「{name}」已保存")
                    st.rerun()
        with col_s2:
            if st.button("取消", key="mt_cancel_save"):
                st.session_state["mt_show_save"] = False
                st.rerun()

st.divider()

st.subheader("💬 对话历史")

if context.turns:
    for turn in context.turns:
        with st.chat_message("user"):
            st.markdown(turn.user_message)
        with st.chat_message("assistant"):
            raw_mode = turn.round_num in st.session_state["mt_raw_rounds"]
            col_text, col_btn = st.columns([14, 1])
            with col_text:
                if raw_mode:
                    st.code(turn.assistant_text, language="markdown")
                else:
                    st.markdown(turn.assistant_text)
            with col_btn:
                label = "📝" if raw_mode else "📄"
                tip = "切换 Markdown 渲染" if raw_mode else "切换原始文本"
                if st.button(label, key=f"mt_toggle_raw_{turn.round_num}", help=tip):
                    if raw_mode:
                        st.session_state["mt_raw_rounds"].discard(turn.round_num)
                    else:
                        st.session_state["mt_raw_rounds"].add(turn.round_num)
                    st.rerun()
            col_s1, col_s2, col_s3, col_s4, col_s5 = st.columns(5)
            with col_s1:
                st.metric("📥 输入", f"{turn.input_tokens:,}")
            with col_s2:
                st.metric("⚡ 缓存命中", f"{turn.cached_tokens:,}")
            with col_s3:
                st.metric("🆕 未命中", f"{turn.uncached_tokens:,}")
            with col_s4:
                st.metric("📤 输出", f"{turn.output_tokens:,}")
            with col_s5:
                st.metric("💰 费用", f"${turn.cost:.6f}")
        st.divider()
else:
    st.info("发送第一条消息开始多轮对话")

with st.form(key="mt_input_form", clear_on_submit=True, border=False):
    col_input, col_btn = st.columns([8, 1])
    with col_input:
        user_message = st.text_area(
            "输入消息",
            height=80,
            key="mt_user_input",
            placeholder="输入您的消息...",
            label_visibility="collapsed",
        )
    with col_btn:
        send_btn = st.form_submit_button("发送", type="primary", width="stretch")

clear_btn = st.button("清空", key="mt_clear", width="stretch", on_click=_clear_context)

if send_btn:
    msg = user_message.strip()
    if not msg:
        st.warning("请输入消息内容")
        st.stop()

    context.system_prompt = system_prompt.strip()

    with st.spinner(f"正在调用 {selected_name} / {selected_profile} ..."):
        try:
            context = selected.multi_turn_call(config, context, msg)
        except Exception as e:
            st.error(f"调用失败: {str(e)}")
            st.stop()

    st.session_state["mt_context"] = context
    st.rerun()

if context.turns:
    st.divider()
    st.subheader("📈 累计统计")

    total_input = sum(t.input_tokens for t in context.turns)
    total_cached = sum(t.cached_tokens for t in context.turns)
    total_uncached = sum(t.uncached_tokens for t in context.turns)
    total_output = sum(t.output_tokens for t in context.turns)
    total_cost = sum(t.cost for t in context.turns)
    total_rounds = len(context.turns)

    st.caption(f"共 **{total_rounds}** 轮对话")

    header_cols = st.columns(6)
    header_cols[0].markdown("**轮次**")
    header_cols[1].markdown("**📥 输入**")
    header_cols[2].markdown("**⚡ 缓存命中**")
    header_cols[3].markdown("**🆕 未命中**")
    header_cols[4].markdown("**📤 输出**")
    header_cols[5].markdown("**💰 费用**")

    for turn in context.turns:
        row_cols = st.columns(6)
        row_cols[0].markdown(f"第 {turn.round_num} 轮")
        row_cols[1].markdown(f"{turn.input_tokens:,}")
        row_cols[2].markdown(f"{turn.cached_tokens:,}")
        row_cols[3].markdown(f"{turn.uncached_tokens:,}")
        row_cols[4].markdown(f"{turn.output_tokens:,}")
        row_cols[5].markdown(f"${turn.cost:.6f}")

    st.markdown("---")
    sum_cols = st.columns(6)
    sum_cols[0].markdown("**合计**")
    sum_cols[1].markdown(f"**{total_input:,}**")
    sum_cols[2].markdown(f"**{total_cached:,}**")
    sum_cols[3].markdown(f"**{total_uncached:,}**")
    sum_cols[4].markdown(f"**{total_output:,}**")
    sum_cols[5].markdown(f"**${total_cost:.6f}**")

    if total_input > 0:
        cached_ratio = total_cached / (total_input + total_output) * 100 if (total_input + total_output) > 0 else 0
        st.caption(
            f"缓存命中率: **{total_cached:,}** / **{total_input + total_output:,}** "
            f"= **{cached_ratio:.1f}%** "
            f"| 累计费用: **${total_cost:.6f}**"
        )
