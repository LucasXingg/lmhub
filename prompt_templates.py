"""提示词模板的持久化与选择/管理组件，供各评测页面共用。"""

import json
from pathlib import Path

import streamlit as st

from prompt_input import MODE_LABELS, MODE_STRING, normalize_mode

TEMPLATES_PATH = Path("configs/prompt_templates.json")
NO_TEMPLATE = "不使用模板"


def load_templates() -> list[dict]:
    if TEMPLATES_PATH.exists():
        try:
            data = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
            return data.get("templates", [])
        except (json.JSONDecodeError, KeyError):
            return []
    return []


def save_templates(templates: list[dict]):
    TEMPLATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATES_PATH.write_text(
        json.dumps({"templates": templates}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def template_record(
    name: str,
    content: str,
    user_message: str = "",
    content_mode: str = MODE_STRING,
    user_mode: str = MODE_STRING,
) -> dict:
    return {
        "name": name,
        "content": content,
        "content_mode": normalize_mode(content_mode),
        "user_message": user_message,
        "user_mode": normalize_mode(user_mode),
    }


def apply_template(
    template: dict,
    system_key: str,
    user_key: str | None = None,
    system_mode_key: str | None = None,
    user_mode_key: str | None = None,
):
    st.session_state[system_key] = template.get("content", "")
    if system_mode_key:
        st.session_state[system_mode_key] = normalize_mode(
            template.get("content_mode", MODE_STRING)
        )
    if user_key:
        st.session_state[user_key] = template.get("user_message", "")
    if user_mode_key:
        st.session_state[user_mode_key] = normalize_mode(
            template.get("user_mode", MODE_STRING)
        )


def render_template_bar(
    prefix: str,
    system_key: str,
    user_key: str | None = None,
    system_mode_key: str | None = None,
    user_mode_key: str | None = None,
):
    """渲染模板下拉框 + 应用/管理/保存按钮。

    应用模板时把正文和「纯文本 / 脚本」选择写回对应 session_state，
    因此需要在提示词输入控件之前调用。
    """
    templates = load_templates()
    template_names = [NO_TEMPLATE] + [t["name"] for t in templates]

    col_select, col_apply, col_manage, col_save = st.columns([7, 1, 1, 1])
    with col_select:
        selected_name = st.selectbox(
            "提示词模板",
            template_names,
            key=f"{prefix}_template_select",
            help="选择已保存的模板，点击右侧按钮应用或管理",
        )
    with col_apply:
        apply_btn = st.button("应用模板", key=f"{prefix}_apply_btn", width="stretch")
    with col_manage:
        manage_btn = st.button("管理模板", key=f"{prefix}_manage_btn", width="stretch")
    with col_save:
        save_btn = st.button("💾 保存为模板", key=f"{prefix}_save_btn", width="stretch")

    if apply_btn:
        if selected_name == NO_TEMPLATE:
            st.warning("请先选择一个提示词模板")
        else:
            for t in templates:
                if t["name"] == selected_name:
                    apply_template(
                        t, system_key, user_key, system_mode_key, user_mode_key
                    )
                    st.rerun()
                    break

    if manage_btn:
        st.session_state[f"{prefix}_show_manage"] = not st.session_state.get(
            f"{prefix}_show_manage", False
        )

    if st.session_state.get(f"{prefix}_show_manage", False):
        _render_manage(prefix, templates)

    if save_btn:
        st.session_state[f"{prefix}_show_save"] = True

    if st.session_state.get(f"{prefix}_show_save", False):
        _render_save(
            prefix, templates, system_key, user_key, system_mode_key, user_mode_key
        )


def _mode_tag(mode) -> str:
    return MODE_LABELS.get(normalize_mode(mode), "纯文本")


def _render_manage(prefix: str, templates: list[dict]):
    with st.container(border=True):
        st.caption("模板管理")
        if not templates:
            st.info("暂无已保存的模板")
        else:
            for idx, t in enumerate(templates):
                col_info, col_delete = st.columns([11, 1])
                with col_info:
                    content_preview = _preview(t.get("content", ""), 50)
                    user_preview = _preview(t.get("user_message", ""), 40)
                    sys_mode = _mode_tag(t.get("content_mode"))
                    usr_mode = _mode_tag(t.get("user_mode"))
                    st.caption(
                        f"**{t['name']}**  |  系统[{sys_mode}]: {content_preview}"
                        f"  |  用户[{usr_mode}]: {user_preview}"
                    )
                with col_delete:
                    if st.button(
                        "🗑️",
                        key=f"{prefix}_delete_tpl_{idx}",
                        help=f"删除模板「{t['name']}」",
                    ):
                        del templates[idx]
                        save_templates(templates)
                        st.rerun()
        col_close, _ = st.columns([1, 1])
        with col_close:
            if st.button("关闭", key=f"{prefix}_close_manage", width="stretch"):
                st.session_state[f"{prefix}_show_manage"] = False
                st.rerun()


def _render_save(
    prefix: str,
    templates: list[dict],
    system_key: str,
    user_key: str | None,
    system_mode_key: str | None,
    user_mode_key: str | None,
):
    with st.container(border=True):
        template_name = st.text_input(
            "模板名称",
            placeholder="输入模板名称...",
            key=f"{prefix}_template_name",
        )
        sys_mode = normalize_mode(
            st.session_state.get(system_mode_key, MODE_STRING) if system_mode_key else MODE_STRING
        )
        usr_mode = normalize_mode(
            st.session_state.get(user_mode_key, MODE_STRING) if user_mode_key else MODE_STRING
        )
        st.caption(
            f"系统提示词[{_mode_tag(sys_mode)}]: "
            f"{_preview(st.session_state.get(system_key, ''), 80) or '(空)'}"
        )
        if user_key:
            st.caption(
                f"用户消息[{_mode_tag(usr_mode)}]: "
                f"{_preview(st.session_state.get(user_key, ''), 80) or '(空)'}"
            )
        col_confirm, col_cancel = st.columns([1, 1])
        with col_confirm:
            if st.button("确认保存", key=f"{prefix}_confirm_save"):
                name = template_name.strip()
                if not name:
                    st.error("请输入模板名称")
                elif any(t["name"] == name for t in templates):
                    st.error(f"模板「{name}」已存在，请使用其他名称")
                else:
                    templates.append(
                        template_record(
                            name=name,
                            content=st.session_state.get(system_key, ""),
                            user_message=(
                                st.session_state.get(user_key, "") if user_key else ""
                            ),
                            content_mode=sys_mode,
                            user_mode=usr_mode,
                        )
                    )
                    save_templates(templates)
                    st.session_state[f"{prefix}_show_save"] = False
                    st.success(f"模板「{name}」已保存")
                    st.rerun()
        with col_cancel:
            if st.button("取消", key=f"{prefix}_cancel_save"):
                st.session_state[f"{prefix}_show_save"] = False
                st.rerun()


def _preview(text: str, limit: int) -> str:
    return text[:limit] + "..." if len(text) > limit else text
