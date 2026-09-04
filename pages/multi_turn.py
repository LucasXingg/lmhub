import streamlit as st
from config import AppConfig
from prompt_input import render_prompt_input, resolve_prompt
from prompt_templates import render_template_bar
from providers import discover_providers, MultiTurnContext
from image_processor import render_settings


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
context = st.session_state["mt_context"]

render_template_bar(
    "mt",
    "mt_system",
    "mt_user_input",
    "mt_system_mode",
    "mt_user_mode",
)

system_raw, system_mode = render_prompt_input(
    "系统提示词 (可选，仅首轮生效)",
    "mt_system",
    "mt_system_mode",
    height=68,
    default_text=context.system_prompt,
    help="系统提示词仅在首轮对话中发送；后续轮次由供应商内部维护上下文",
)

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

user_raw, user_mode = render_prompt_input(
    "输入消息",
    "mt_user_input",
    "mt_user_mode",
    height=80,
    placeholder="输入您的消息...",
)

col_send, col_clear = st.columns([1, 1])
with col_send:
    send_btn = st.button("发送", type="primary", width="stretch", key="mt_send")
with col_clear:
    clear_btn = st.button("清空", key="mt_clear", width="stretch", on_click=_clear_context)

if send_btn:
    prompt_context = {
        "round": len(context.turns) + 1,
        "history": [
            {"user": t.user_message, "assistant": t.assistant_text}
            for t in context.turns
        ],
    }
    system_prompt = resolve_prompt(
        system_raw, system_mode, prompt_context, label="系统提示词"
    )
    user_message = resolve_prompt(
        user_raw, user_mode, prompt_context, label="用户消息"
    )
    if system_prompt is None or user_message is None:
        st.stop()
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
