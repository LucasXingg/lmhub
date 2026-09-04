"""提示词输入：纯文本 / Python 脚本两种模式。

脚本在受限命名空间中 exec，必须赋值 ``prompt`` 字符串，作为发给模型的最终内容。
不引入第三方模板引擎；脚本里可用标准库。异常由调用方展示到页面。
"""

from __future__ import annotations

MODE_STRING = "string"
MODE_SCRIPT = "script"
MODE_OPTIONS = [MODE_STRING, MODE_SCRIPT]
MODE_LABELS = {
    MODE_STRING: "纯文本",
    MODE_SCRIPT: "Python 脚本",
}

SCRIPT_HELP = (
    "脚本必须赋值 `prompt`（str）作为发给模型的最终内容。"
    "可用标准库；只读变量 `context` 提供当前页信息。异常会显示在页面上。"
)


class PromptEvalError(Exception):
    """脚本未产出合法 prompt，或执行过程出错。"""


def normalize_mode(mode) -> str:
    if mode in (MODE_SCRIPT, "Python 脚本", "script"):
        return MODE_SCRIPT
    return MODE_STRING


def evaluate_prompt(source: str, mode: str = MODE_STRING, context: dict | None = None) -> str:
    """把输入解析成最终提示词。脚本模式必须定义 prompt 变量。"""
    mode = normalize_mode(mode)
    source = source if source is not None else ""
    if mode == MODE_STRING:
        return source

    namespace: dict = {"context": dict(context or {})}
    try:
        exec(source, namespace, namespace)
    except Exception as exc:
        raise PromptEvalError(f"脚本执行失败: {exc}") from exc

    if "prompt" not in namespace:
        raise PromptEvalError('脚本必须定义 prompt 变量，例如: prompt = "..."')
    value = namespace["prompt"]
    if not isinstance(value, str):
        raise PromptEvalError(f"prompt 必须是 str，当前为 {type(value).__name__}")
    return value


def resolve_prompt(
    source: str,
    mode: str,
    context: dict | None = None,
    *,
    label: str = "提示词",
) -> str | None:
    """求值提示词；失败时把异常写到 Streamlit 页面并返回 None。"""
    import streamlit as st

    try:
        return evaluate_prompt(source, mode, context)
    except PromptEvalError as exc:
        st.error(f"{label}: {exc}")
        return None


def render_prompt_input(
    label: str,
    text_key: str,
    mode_key: str,
    *,
    height: int = 100,
    help: str | None = None,
    placeholder: str = "",
    default_text: str = "",
    default_mode: str = MODE_STRING,
) -> tuple[str, str]:
    """渲染「纯文本 / Python 脚本」开关 + 文本框，返回 (原文, 模式)。"""
    import streamlit as st

    if text_key not in st.session_state:
        st.session_state[text_key] = default_text
    if mode_key not in st.session_state:
        st.session_state[mode_key] = normalize_mode(default_mode)

    header, switch = st.columns([3, 2])
    with switch:
        st.radio(
            f"{label}输入方式",
            MODE_OPTIONS,
            format_func=lambda m: MODE_LABELS.get(m, m),
            key=mode_key,
            horizontal=True,
            label_visibility="collapsed",
            help=SCRIPT_HELP,
        )
    mode = normalize_mode(st.session_state[mode_key])
    with header:
        suffix = " · Python 脚本" if mode == MODE_SCRIPT else ""
        st.markdown(f"**{label}{suffix}**")

    text = st.text_area(
        label,
        height=height,
        key=text_key,
        help=help or (SCRIPT_HELP if mode == MODE_SCRIPT else None),
        placeholder=placeholder
        or ('prompt = "..."' if mode == MODE_SCRIPT else ""),
        label_visibility="collapsed",
    )
    if mode == MODE_SCRIPT:
        st.caption(SCRIPT_HELP)
    return text, mode
