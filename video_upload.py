"""浏览器选视频后经 WebSocket 分片传到 Python，避开 st.file_uploader 的 HTTP 413。

反向代理（nginx 默认 client_max_body_size=1m）会拦截 /_stcore/upload_file 的 PUT，
1.1MB 的片子就会 Axios 413。分片走 Streamlit 组件的 websocket，不受该限制。
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

CHUNK_SIZE = 256 * 1024

_component = components.declare_component(
    "video_file_upload",
    path=str(Path(__file__).parent / "video_upload_frontend"),
)


@dataclass
class UploadedVideo:
    name: str
    data: bytes
    size: int


def empty_store() -> dict:
    return {
        "name": None,
        "size": 0,
        "total": 0,
        "parts": [],
        "data": None,
        "error": None,
    }


def apply_upload_message(store: dict, msg: dict | None) -> bool:
    """根据组件消息更新 store。返回 True 表示调用方应 st.rerun()。"""
    if not msg or not isinstance(msg, dict):
        return False

    op = msg.get("op")
    if op == "start":
        name = msg.get("name") or "video.bin"
        size = int(msg.get("size") or 0)
        total = max(1, int(msg.get("total") or 1))
        if store.get("name") == name and store.get("size") == size:
            return False
        store.clear()
        store.update(empty_store())
        store["name"] = name
        store["size"] = size
        store["total"] = total
        return True

    if op == "chunk":
        if store.get("data") is not None:
            return False
        idx = int(msg.get("i") or 0)
        if idx != len(store.get("parts") or []):
            return False
        raw = msg.get("data") or ""
        store.setdefault("parts", []).append(base64.b64decode(raw))
        if len(store["parts"]) >= store.get("total", 0):
            store["data"] = b"".join(store["parts"])
            store["parts"] = []
        return True

    if op == "error":
        store["error"] = msg.get("message") or "上传失败"
        return False

    return False


def render_chunked_video_upload(key: str = "chunked_video") -> UploadedVideo | None:
    store_key = f"{key}__store"
    reset_key = f"{key}__reset"
    if store_key not in st.session_state:
        st.session_state[store_key] = empty_store()
    store = st.session_state[store_key]

    want = -1
    if store["data"] is None and store["total"] > 0 and len(store["parts"]) < store["total"]:
        want = len(store["parts"])

    msg = _component(
        want_chunk=want,
        chunk_size=CHUNK_SIZE,
        reset=st.session_state.get(reset_key, 0),
        key=key,
        default=None,
    )
    if apply_upload_message(store, msg):
        st.rerun()

    if store.get("error"):
        st.error(store["error"])
        return None

    if store["data"] is not None:
        return UploadedVideo(name=store["name"], data=store["data"], size=store["size"])

    if store["total"] > 0:
        done = len(store["parts"])
        st.progress(
            done / store["total"],
            text=f"正在接收 {store['name']}（{done}/{store['total']} 片）",
        )
    return None


def clear_chunked_video_upload(key: str = "chunked_video"):
    st.session_state[f"{key}__store"] = empty_store()
    st.session_state[f"{key}__reset"] = st.session_state.get(f"{key}__reset", 0) + 1
