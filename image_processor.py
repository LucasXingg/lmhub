from PIL import Image
import streamlit as st


METHOD_LANCZOS = "Lanczos 缩放"
METHOD_BILINEAR = "Bilinear 缩放"
METHOD_NEAREST = "Nearest 缩放"
METHOD_CENTER_CROP = "居中裁剪"
METHOD_PAD_TO_SQUARE = "填充为正方形"

ALL_METHODS = [
    METHOD_LANCZOS,
    METHOD_BILINEAR,
    METHOD_NEAREST,
    METHOD_CENTER_CROP,
    METHOD_PAD_TO_SQUARE,
]

_INTERPOLATION_MAP = {
    METHOD_LANCZOS: Image.LANCZOS,
    METHOD_BILINEAR: Image.BILINEAR,
    METHOD_NEAREST: Image.NEAREST,
}


def process_image(
    image: Image.Image,
    method: str,
    target_width: int = 512,
    target_height: int = 512,
    keep_aspect_ratio: bool = True,
) -> Image.Image:
    result = image.copy().convert("RGB")

    if method in _INTERPOLATION_MAP:
        interp = _INTERPOLATION_MAP[method]
        result = _resize_image(
            result, target_width, target_height, interp, keep_aspect_ratio
        )
    elif method == METHOD_CENTER_CROP:
        result = _center_crop(result, target_width, target_height)
    elif method == METHOD_PAD_TO_SQUARE:
        result = _pad_to_square(result, target_width)

    return result


def _resize_image(
    image: Image.Image,
    width: int,
    height: int,
    interpolation: int,
    keep_aspect: bool,
) -> Image.Image:
    if keep_aspect:
        image.thumbnail((width, height), interpolation)
        return image
    else:
        return image.resize((width, height), interpolation)


def _center_crop(image: Image.Image, width: int, height: int) -> Image.Image:
    w, h = image.size
    left = max(0, (w - width) // 2)
    top = max(0, (h - height) // 2)
    right = min(w, left + width)
    bottom = min(h, top + height)
    return image.crop((left, top, right, bottom))


def _pad_to_square(image: Image.Image, size: int) -> Image.Image:
    w, h = image.size
    max_side = max(w, h)
    canvas = Image.new("RGB", (max_side, max_side), (0, 0, 0))
    canvas.paste(image, ((max_side - w) // 2, (max_side - h) // 2))
    return canvas.resize((size, size), Image.LANCZOS)


def estimate_image_tokens(width: int, height: int) -> int:
    """Estimate image tokens per OpenAI's tiling formula (approximate)."""
    max_size = 2048
    if width > max_size or height > max_size:
        ratio = max_size / max(width, height)
        width = int(width * ratio)
        height = int(height * ratio)

    tile_size = 512
    w_tiles = max(1, (width + tile_size - 1) // tile_size)
    h_tiles = max(1, (height + tile_size - 1) // tile_size)

    return 85 + 170 * (w_tiles * h_tiles)


def render_settings():
    st.divider()
    st.subheader("🖼️ 图像预处理")

    enabled = st.checkbox("启用预处理", value=True, key="img_proc_enable")
    method = st.selectbox("处理方法", ALL_METHODS, key="img_proc_method")

    col1, col2 = st.columns(2)
    with col1:
        target_w = st.number_input(
            "目标宽度", 64, 4096, 512, 64, key="img_proc_w"
        )
    with col2:
        target_h = st.number_input(
            "目标高度", 64, 4096, 512, 64, key="img_proc_h"
        )

    if method in _INTERPOLATION_MAP:
        keep_aspect = st.checkbox("保持宽高比", value=True, key="img_proc_aspect")
    else:
        st.session_state["img_proc_aspect"] = True

    est_tokens = estimate_image_tokens(
        st.session_state.get("img_proc_w", 512),
        st.session_state.get("img_proc_h", 512),
    )
    st.caption(f"预计每张图片消耗: ~{est_tokens} tokens (OpenAI 标准)")
    st.caption(f"处理后尺寸: {target_w}x{target_h}")

    # Show a comparison of original vs processed
    img_key = "img_proc_original_upload"
    test_file = st.file_uploader(
        "上传测试图片以预览预处理效果",
        type=["png", "jpg", "jpeg", "webp"],
        key=img_key,
        help="仅用于预览，不会影响 Demo 页面上传的图片",
    )
    if test_file:
        try:
            original = Image.open(test_file).convert("RGB")
            processed = process_image(
                original, method, target_w, target_h, keep_aspect
            )

            col_a, col_b = st.columns(2)
            with col_a:
                st.caption(f"原始: {original.size[0]}x{original.size[1]}")
                st.image(original, width="stretch")
            with col_b:
                st.caption(f"处理后: {processed.size[0]}x{processed.size[1]}")
                st.image(processed, width="stretch")
        except Exception as e:
            st.warning(f"预览失败: {e}")
