"""截图优化测试"""
import pytest


def _make_png_bytes(width: int = 100, height: int = 100) -> bytes:
    try:
        from PIL import Image
        import io
        img = Image.new("RGB", (width, height), color=(255, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        pytest.skip("Pillow not installed")


def test_strategy_none():
    from zerotoken.optimizers.screenshot_opt import optimize_screenshot
    raw = _make_png_bytes()
    result = optimize_screenshot(raw, strategy="none")
    assert result is None


def test_strategy_compressed():
    from zerotoken.optimizers.screenshot_opt import optimize_screenshot
    raw = _make_png_bytes(800, 600)
    result = optimize_screenshot(raw, strategy="compressed", max_width=400, quality=50)
    assert result is not None
    assert len(result) < len(raw)


def test_strategy_thumbnail():
    from zerotoken.optimizers.screenshot_opt import optimize_screenshot
    raw = _make_png_bytes(1920, 1080)
    result = optimize_screenshot(raw, strategy="thumbnail", max_width=200, quality=30)
    assert result is not None
    assert len(result) < len(raw)


def test_strategy_raw():
    from zerotoken.optimizers.screenshot_opt import optimize_screenshot
    raw = _make_png_bytes()
    result = optimize_screenshot(raw, strategy="raw")
    assert result == raw
