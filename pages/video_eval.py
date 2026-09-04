import tempfile
from pathlib import Path

import streamlit as st

from config import AppConfig
from image_processor import (
    ALL_METHODS,
    estimate_image_tokens,
    process_image,
    render_settings,
)
from prompt_templates import render_template_bar
from providers import discover_providers
from usage_view import render_usage
from video_upload import render_chunked_video_upload
import video_processor as vp

FRAME_KEY_PREFIX = "video_frame_sel_"
MAX_FRAMES = 64


@st.cache_data(show_spinner=False)
def persist_upload(data: bytes, filename: str) -> str:
    suffix = Path(filename).suffix or ".mp4"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(data)
    tmp.close()
    return tmp.name


@st.cache_data(show_spinner=False)
def probe(path: str) -> vp.VideoInfo:
    return vp.probe_video(path)


def preprocess(image):
    """按侧栏「图像预处理」设置缩放帧，与 Demo 页保持一致。"""
    if not st.session_state.get("img_proc_enable", False):
        return image.convert("RGB")
    return process_image(
        image,
        st.session_state.get("img_proc_method", ALL_METHODS[0]),
        st.session_state.get("img_proc_w", 512),
        st.session_state.get("img_proc_h", 512),
        st.session_state.get("img_proc_aspect", True),
    )


def clear_frames():
    for key in list(st.session_state.keys()):
        if key.startswith(FRAME_KEY_PREFIX):
            del st.session_state[key]
    st.session_state.pop("video_frames", None)
    st.session_state.pop("video_result_response", None)


st.set_page_config(page_title="LMHub Video", page_icon="🎬", layout="wide")

providers = discover_providers()
if not providers:
    st.error("未发现任何供应商，请在 providers/ 目录下添加供应商文件")
    st.stop()

app_config = AppConfig.load()
provider_names = list(providers.keys())

with st.sidebar:
    render_settings()

st.title("🎬 视频抽帧评测")
st.caption("上传视频片段 → 按策略抽取关键帧 → 连同提示词发送给多模态模型")

selected_name = st.selectbox(
    "选择供应商",
    provider_names,
    key="video_selected_provider",
    help="在侧栏「Providers」中配置各供应商的 API Key",
)
selected = providers[selected_name]

profiles = app_config.list_profiles(selected.name)
if not profiles:
    profiles = ["默认"]
    app_config.get_profile(selected.name, "默认")
selected_profile = st.selectbox(
    "配置方案",
    profiles,
    key=f"video_profile_{selected.name}",
)
config = app_config.get_profile(selected.name, selected_profile)

with st.expander(f"📋 {selected_name} / {selected_profile} 当前配置", expanded=False):
    summary = selected.get_config_summary(config)
    if summary:
        for label, value in summary:
            st.write(f"**{label}**:", value)
    else:
        st.info("自定义供应商")

if not selected.supports_images:
    st.warning(f"{selected_name} 不支持图片输入，无法用于视频抽帧评测，请选择其他供应商")
    st.stop()

if vp.available_backend() is None:
    st.error(
        "缺少视频解码依赖。请执行 `pip install -r requirements.txt` "
        "安装 opencv-python-headless（或 av）后重试。"
    )
    st.stop()

st.divider()
st.subheader("1️⃣ 上传视频")

source_mode = st.radio(
    "视频来源",
    ["上传文件", "本地路径"],
    key="video_source_mode",
    horizontal=True,
    help=(
        "浏览器选文件后按 256KB 经 WebSocket 分片传输，"
        "不走 st.file_uploader /_stcore/upload_file，"
        "可避开反向代理默认 1MB 导致的 Axios 413。"
        "超大文件也可改用本机路径，解码器直接读磁盘。"
    ),
)

if source_mode == "上传文件":
    uploaded = render_chunked_video_upload("video_bytes")
    if not uploaded:
        st.info(
            "请选择一个视频片段（mp4 / mov / mkv / webm 等）。"
            "若之前用文件选择器出现 Axios 413，刷新后应已消失："
            "那是反向代理把超过 1MB 的 HTTP 上传拦下了，与 Streamlit 200MB 上限无关。"
        )
        st.stop()
    video_path = persist_upload(uploaded.data, uploaded.name)
    source_name = uploaded.name
else:
    local_path = st.text_input(
        "本机视频路径",
        key="video_local_path",
        placeholder="/data/clips/example.mp4",
        help="填写运行 Streamlit 的机器上的绝对路径，适合超过上传上限的大文件",
    )
    if not local_path.strip():
        st.info("请输入本机上的视频文件路径，或切换回「上传文件」")
        st.stop()
    video_path = local_path.strip()
    path_obj = Path(video_path)
    if not path_obj.is_file():
        st.error(f"文件不存在: {video_path}")
        st.stop()
    source_name = str(path_obj.resolve())

if st.session_state.get("video_source_name") != source_name:
    st.session_state["video_source_name"] = source_name
    # 时间区间与新视频的时长绑定，换片时必须复位，否则会超出 number_input 上限
    st.session_state.pop("video_start", None)
    st.session_state.pop("video_end", None)
    clear_frames()

try:
    info = probe(video_path)
except vp.VideoBackendError as e:
    st.error(f"读取视频失败: {e}")
    st.stop()

col_video, col_meta = st.columns([2, 1])
with col_video:
    st.video(video_path)
with col_meta:
    st.metric("⏱️ 时长", f"{info.duration:.2f} s" if info.duration else "未知")
    st.metric("🎞️ 帧率", f"{info.fps:.2f} fps" if info.fps else "未知")
    st.metric("📐 分辨率", f"{info.width} × {info.height}")
    st.caption(f"总帧数: {info.frame_count or '未知'} | 解码后端: {vp.available_backend()}")

st.divider()
st.subheader("2️⃣ 抽帧设置")

# 某些容器读不出时长，此时放开区间上限交给用户自己指定
duration = info.duration if info.duration > 0 else 0.0
range_limit = duration if duration > 0 else 3600.0

strategy = st.radio(
    "抽帧策略",
    vp.ALL_STRATEGIES,
    key="video_strategy",
    horizontal=True,
    help=(
        "均匀采样：在区间内等距取 N 帧；固定间隔：每隔 X 秒取一帧；"
        "场景变化检测：按画面差异挑选关键帧；自定义时间点：手动指定秒数或 mm:ss"
    ),
)

col_start, col_end = st.columns(2)
with col_start:
    start_time = st.number_input(
        "起始时间 (秒)",
        min_value=0.0,
        max_value=range_limit,
        value=0.0,
        step=0.5,
        key="video_start",
    )
with col_end:
    end_time = st.number_input(
        "结束时间 (秒)",
        min_value=0.0,
        max_value=range_limit,
        value=duration if duration > 0 else 10.0,
        step=0.5,
        key="video_end",
    )

start_time, end_time = vp.clamp_range(info, start_time, end_time)

if strategy == vp.STRATEGY_UNIFORM:
    frame_count = st.slider("抽取帧数", 1, MAX_FRAMES, 8, key="video_uniform_count")
    timestamps = vp.uniform_timestamps(frame_count, start_time, end_time)
elif strategy == vp.STRATEGY_INTERVAL:
    col_step, col_max = st.columns(2)
    with col_step:
        step = st.number_input(
            "间隔 (秒)", 0.1, 600.0, 1.0, 0.1, key="video_interval_step"
        )
    with col_max:
        limit = st.number_input(
            "最多帧数", 1, MAX_FRAMES, 16, 1, key="video_interval_max"
        )
    timestamps = vp.interval_timestamps(step, start_time, end_time, int(limit))
elif strategy == vp.STRATEGY_SCENE:
    col_step, col_thr, col_max = st.columns(3)
    with col_step:
        scene_step = st.number_input(
            "扫描步长 (秒)", 0.1, 10.0, 0.5, 0.1, key="video_scene_step"
        )
    with col_thr:
        threshold = st.slider(
            "差异阈值", 0.01, 0.60, 0.12, 0.01, key="video_scene_threshold",
            help="相邻采样点的平均像素差异超过该值时保留为关键帧，值越小抽出的帧越多",
        )
    with col_max:
        scene_max = st.number_input(
            "最多帧数", 1, MAX_FRAMES, 12, 1, key="video_scene_max"
        )
    timestamps = None
else:
    custom_text = st.text_area(
        "时间点列表",
        value="0, 1, 2.5",
        height=68,
        key="video_custom_times",
        help="用逗号或空格分隔，支持 12.5 或 01:03.5 形式",
    )
    try:
        timestamps = [
            t for t in vp.parse_timestamps(custom_text) if start_time <= t <= end_time
        ][:MAX_FRAMES]
    except ValueError as e:
        st.error(str(e))
        timestamps = []

if strategy == vp.STRATEGY_SCENE:
    st.caption(f"将在 {start_time:.2f}s ~ {end_time:.2f}s 内扫描并挑选关键帧")
else:
    st.caption(
        f"预计抽取 **{len(timestamps)}** 帧: "
        + ", ".join(vp.format_timestamp(t) for t in timestamps[:12])
        + (" ..." if len(timestamps) > 12 else "")
    )

col_extract, col_clear, _ = st.columns([1, 1, 6])
with col_extract:
    extract_btn = st.button("提取帧", type="primary", width="stretch")
with col_clear:
    if st.button("清空帧", width="stretch"):
        clear_frames()
        st.rerun()

if extract_btn:
    if strategy != vp.STRATEGY_SCENE and not timestamps:
        st.warning("没有可抽取的时间点，请调整时间区间或策略")
        st.stop()

    clear_frames()
    progress_bar = st.progress(0.0, text="正在抽帧...")
    try:
        if strategy == vp.STRATEGY_SCENE:
            picked = vp.detect_scene_timestamps(
                video_path,
                start_time,
                end_time,
                scene_step,
                threshold,
                int(scene_max),
                progress=lambda p: progress_bar.progress(
                    min(p, 1.0), text="正在扫描场景变化..."
                ),
            )
            frames = vp.extract_frames(
                video_path,
                picked,
                progress=lambda p: progress_bar.progress(
                    min(p, 1.0), text="正在抽帧..."
                ),
            )
        else:
            frames = vp.extract_frames(
                video_path,
                timestamps,
                progress=lambda p: progress_bar.progress(
                    min(p, 1.0), text="正在抽帧..."
                ),
            )
    except (vp.VideoBackendError, ValueError) as e:
        progress_bar.empty()
        st.error(f"抽帧失败: {e}")
        st.stop()
    progress_bar.empty()

    if not frames:
        st.warning("未能抽取到任何帧，请调整时间区间或策略后重试")
    else:
        st.session_state["video_frames"] = frames
        st.rerun()

frames = st.session_state.get("video_frames", [])
if not frames:
    st.stop()

st.divider()
st.subheader(f"3️⃣ 已抽取 {len(frames)} 帧")

col_all, col_none, _ = st.columns([1, 1, 6])
with col_all:
    if st.button("全选", width="stretch"):
        for frame in frames:
            st.session_state[f"{FRAME_KEY_PREFIX}{frame.index}"] = True
        st.rerun()
with col_none:
    if st.button("全不选", width="stretch"):
        for frame in frames:
            st.session_state[f"{FRAME_KEY_PREFIX}{frame.index}"] = False
        st.rerun()

columns_per_row = 4
for row_start in range(0, len(frames), columns_per_row):
    row = frames[row_start : row_start + columns_per_row]
    cols = st.columns(columns_per_row)
    for col, frame in zip(cols, row):
        with col:
            frame_key = f"{FRAME_KEY_PREFIX}{frame.index}"
            st.session_state.setdefault(frame_key, True)
            st.image(frame.image, width="stretch")
            st.checkbox(f"#{frame.index} · {frame.label}", key=frame_key)

selected_frames = [
    frame
    for frame in frames
    if st.session_state.get(f"{FRAME_KEY_PREFIX}{frame.index}", True)
]

proc_enabled = st.session_state.get("img_proc_enable", False)
if proc_enabled:
    st.caption(
        f"已启用侧栏图像预处理: {st.session_state.get('img_proc_method', ALL_METHODS[0])} "
        f"→ {st.session_state.get('img_proc_w', 512)}×{st.session_state.get('img_proc_h', 512)}"
    )
else:
    st.caption("未启用图像预处理，将按原始分辨率发送（可在侧栏开启缩放以节省 token）")

if selected_frames:
    sample_size = preprocess(selected_frames[0].image).size
    per_frame_tokens = estimate_image_tokens(*sample_size)
    st.caption(
        f"已选中 **{len(selected_frames)}** 帧 (发送尺寸 {sample_size[0]}×{sample_size[1]})，"
        f"预计图片输入约 **{len(selected_frames) * per_frame_tokens:,}** tokens (OpenAI 估算)"
    )
else:
    st.caption("未选中任何帧")

st.divider()
st.subheader("4️⃣ 提示词")

if "video_system" not in st.session_state:
    st.session_state["video_system"] = "你是一个专业的视频内容分析助手。"
if "video_user" not in st.session_state:
    st.session_state["video_user"] = (
        "以下是从同一段视频中按时间顺序抽取的若干帧，请描述视频中发生了什么。"
    )

render_template_bar("video", "video_system", "video_user")

system_prompt = st.text_area(
    "系统提示词 (System Prompt)",
    height=100,
    key="video_system",
)
user_message = st.text_area(
    "用户消息",
    height=100,
    key="video_user",
)

include_timeline = st.checkbox(
    "在用户消息中附加帧时间戳说明",
    value=True,
    key="video_include_timeline",
    help="把每一帧对应的时间点写进提示词，便于模型理解帧之间的先后顺序",
)

col_send, col_clear_result, _ = st.columns([1, 1, 6])
with col_send:
    send_btn = st.button("发送", type="primary", width="stretch")
with col_clear_result:
    if st.button("清空结果", width="stretch"):
        st.session_state.pop("video_result_response", None)
        st.rerun()

if send_btn:
    if not selected_frames:
        st.warning("请至少选择一帧")
        st.stop()
    if not user_message.strip():
        st.warning("请输入消息内容")
        st.stop()

    content = user_message.strip()
    if include_timeline:
        timeline = ", ".join(f"#{f.index} {f.label}" for f in selected_frames)
        content = (
            f"以下 {len(selected_frames)} 张图片是同一段视频按时间顺序抽取的帧"
            f"（时间点依次为: {timeline}）。\n\n{content}"
        )

    messages = []
    if system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt.strip()})
    messages.append({"role": "user", "content": content})

    images = [preprocess(frame.image) for frame in selected_frames]

    with st.spinner(f"正在调用 {selected_name} / {selected_profile} ..."):
        try:
            config = app_config.get_profile(selected.name, selected_profile)
            response = selected.call_model(config, messages, images)
        except Exception as e:
            st.error(f"调用失败: {str(e)}")
            st.stop()

    st.session_state["video_result_response"] = response

response = st.session_state.get("video_result_response")
if response is None:
    st.stop()

st.divider()
st.subheader("📤 模型回复")
st.markdown(response.text)

render_usage(response)
