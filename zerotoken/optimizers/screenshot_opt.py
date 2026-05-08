"""截图优化：压缩 / 缩放 / 降质

策略：
- none       : 不返回截图（返回 None）
- raw        : 原始 PNG bytes 不处理
- compressed : JPEG 压缩 + 降分辨率（默认 quality=50, max_width=800）
- thumbnail  : 极小缩略图（默认 200px 宽, quality=30）
"""

from __future__ import annotations

from typing import Optional


def optimize_screenshot(
    raw_bytes: bytes,
    *,
    strategy: str = "compressed",
    max_width: int = 800,
    quality: int = 50,
) -> Optional[bytes]:
    """根据策略优化截图 bytes"""
    if strategy == "none":
        return None
    if strategy == "raw":
        return raw_bytes

    try:
        from PIL import Image
        import io
    except ImportError:
        return raw_bytes

    img = Image.open(io.BytesIO(raw_bytes))

    if strategy == "thumbnail":
        max_width = min(max_width, 200)
        quality = min(quality, 30)

    if img.width > max_width:
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()
