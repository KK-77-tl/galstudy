"""Read-only embed experiment against the official WebGAL online example."""

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page()
    result = {
        "url": "https://demo.openwebgal.com",
        "dynamic_story": "未测试",
        "question_event_bridge": "未测试",
        "server_save_bridge": "未测试",
    }
    page.route(
        "http://localhost:3000/research-webgal",
        lambda route: route.fulfill(
            content_type="text/html",
            body='<html><body><iframe title="WebGAL probe" src="https://demo.openwebgal.com" style="width:100%;height:720px"></iframe></body></html>',
        ),
    )
    try:
        page.goto(
            "http://localhost:3000/research-webgal",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        frame = page.frame_locator("iframe")
        frame.locator("body").wait_for(timeout=30000)
        result["iframe_loaded"] = True
        result["iframe_text_sample"] = frame.locator("body").inner_text(timeout=10000)[
            :120
        ]
        result["direct_access"] = page.evaluate(
            """() => {try {return document.querySelector('iframe').contentWindow.document.title} catch(e) {return e.name}}"""
        )
        page.locator("iframe").evaluate("(element) => element.remove()")
        result["unmount_removed_frame"] = page.locator("iframe").count() == 0
        result["note"] = (
            "官方示例跨域，直接读取状态被同源策略限制。需要受控的同源构建或双方消息桥才能处理业务题目与存档。资源释放与完整动态脚本未验证。"
        )
    except Exception as error:
        result["error"] = str(error)[:400]
    Path("docs/webgal-probe.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    browser.close()
