"""Tests for adaptive fingerprint extraction and similarity."""

import pytest

from zerotoken.adaptive import extract_fingerprint, similarity_score, relocate

# Minimal HTML for fingerprint extraction
SAMPLE_HTML = """
<!DOCTYPE html>
<html><body>
<div class="container">
  <section class="products">
    <article class="product" id="p1" data-id="1">
      <h3>Product 1</h3>
      <p class="description">Description 1</p>
    </article>
  </section>
</div>
</body></html>
"""


@pytest.mark.asyncio
async def test_extract_fingerprint_structure():
    """Extract fingerprint from a real element and assert structure."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(SAMPLE_HTML)
        el = await page.query_selector("#p1")
        assert el is not None

        fp = await extract_fingerprint(el, page)
        await browser.close()

    assert fp is not None
    assert "parent" in fp
    assert "self" in fp
    assert fp["parent"]["tag"] == "section"
    assert fp["self"]["tag"] == "article"
    assert fp["self"]["attrs"].get("id") == "p1"
    assert "Product 1" in (fp["self"]["text"] or "")
    assert isinstance(fp["self"]["siblings"], list)
    assert isinstance(fp["self"]["path"], list)
    assert "article" in fp["self"]["path"]


def test_similarity_score_identical():
    fp = {
        "parent": {"tag": "div", "attrs": {"class": "x"}, "text": "a"},
        "self": {
            "tag": "a",
            "attrs": {"id": "i1"},
            "text": "Link",
            "siblings": ["span"],
            "path": ["div", "a"],
        },
    }
    assert similarity_score(fp, fp) == 1.0


def test_similarity_score_different_tag():
    fp1 = {
        "parent": {"tag": "div", "attrs": {}, "text": ""},
        "self": {"tag": "a", "attrs": {}, "text": "x", "siblings": [], "path": ["a"]},
    }
    fp2 = {
        "parent": {"tag": "div", "attrs": {}, "text": ""},
        "self": {"tag": "button", "attrs": {}, "text": "x", "siblings": [], "path": ["button"]},
    }
    s = similarity_score(fp1, fp2)
    assert 0 <= s < 1.0


def test_similarity_score_same_tag_and_text():
    fp1 = {
        "parent": {"tag": "div", "attrs": {}, "text": ""},
        "self": {
            "tag": "a",
            "attrs": {"href": "#"},
            "text": "Click",
            "siblings": [],
            "path": ["div", "a"],
        },
    }
    fp2 = {
        "parent": {"tag": "div", "attrs": {}, "text": ""},
        "self": {
            "tag": "a",
            "attrs": {"href": "#"},
            "text": "Click",
            "siblings": [],
            "path": ["div", "a"],
        },
    }
    assert similarity_score(fp1, fp2) >= 0.8


@pytest.mark.asyncio
async def test_relocate_no_stored_returns_none(tmp_path):
    from zerotoken.storage_sqlite import SQLiteStorage

    storage = SQLiteStorage(db_path=str(tmp_path / "t.db"))
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content("<body><a href='#'>X</a></body>")
        handle = await relocate(page, "example.com", "#missing", storage)
        await browser.close()
    assert handle is None


@pytest.mark.asyncio
async def test_relocate_finds_element_when_stored(tmp_path):
    from zerotoken.storage_sqlite import SQLiteStorage

    storage = SQLiteStorage(db_path=str(tmp_path / "t.db"))
    SAMPLE = """
    <!DOCTYPE html><html><body>
    <div><a id="link1" href="#">Product 1</a></div>
    </body></html>
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(SAMPLE)
        el = await page.query_selector("#link1")
        assert el is not None
        fp = await extract_fingerprint(el, page)
        assert fp is not None
        storage.fingerprint_save("example.com", "#link1", fp)
        await browser.close()

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content("<body><div><a class='new' data-id='1'>Product 1</a></div></body>")
        handle = await relocate(page, "example.com", "#link1", storage, threshold=0.3)
        await browser.close()
    assert handle is not None


@pytest.mark.asyncio
async def test_controller_adaptive_flow(tmp_path):
    """Integration: Controller click with auto_save then adaptive after HTML change."""
    from zerotoken.controller import BrowserController
    from zerotoken.storage_sqlite import SQLiteStorage

    storage = SQLiteStorage(db_path=str(tmp_path / "ctrl.db"))
    controller = BrowserController()
    controller._config["enable_adaptive"] = True
    controller.set_adaptive_store(storage)

    await controller.start(headless=True)
    try:
        await controller._page.set_content(
            "<!DOCTYPE html><html><body><button id='submit'>Submit</button></body></html>"
        )
        record1 = await controller.click("#submit", auto_save=True)
        assert record1.result.get("success") is True
        domain = "default"
        assert storage.fingerprint_load(domain, "#submit") is not None

        await controller._page.set_content(
            "<!DOCTYPE html><html><body><button class='btn-primary' data-action='submit'>Submit</button></body></html>"
        )
        record2 = await controller.click("#submit", adaptive=True)
        assert record2.result.get("success") is True
        assert record2.result.get("adaptive_used") is True
    finally:
        await controller.stop()
