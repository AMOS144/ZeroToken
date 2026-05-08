"""文件操作动作：upload, download"""

from __future__ import annotations

import os
from typing import Any


async def upload_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """上传文件：通过 file input 元素的 set_input_files"""
    path = params.get("path", "")
    if isinstance(path, list):
        await element.set_input_files(path)
        return {"uploaded": path}
    else:
        await element.set_input_files(path)
        return {"uploaded": [path]}


async def download_action(page: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """触发下载：点击元素并捕获下载事件

    注意：page 参数这里实际是 Page（非 frame），因为 expect_download 是 Page 级 API。
    """
    selector = params.get("selector", "")
    save_dir = params.get("save_dir")
    timeout = params.get("timeout", 30000)

    async with page.expect_download(timeout=timeout) as download_info:
        if element:
            await element.click()
        elif selector:
            await page.click(selector)

    # Playwright：下载对象在 download_info.value（协程）中
    download = await download_info.value

    suggested = download.suggested_filename
    download_url = download.url

    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, suggested)
        await download.save_as(save_path)
    else:
        save_path = await download.path()

    return {
        "filename": suggested,
        "path": str(save_path) if save_path else None,
        "url": download_url,
    }
