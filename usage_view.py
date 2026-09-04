"""模型响应的用量展示组件，供 Demo / 视频评测等页面共用。"""

import json

import streamlit as st


def render_usage(response):
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
