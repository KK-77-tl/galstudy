"""Verify source-image alignment and the male naming flow in a real browser."""
import json
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "test-results" / "male-name"
OUT.mkdir(parents=True, exist_ok=True)
URL = "http://localhost:3003/male/name"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1672, "height": 941})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL)
    expect(page.locator("[data-phase=editing]")).to_be_visible()
    page.wait_for_timeout(1600)
    expect(page.get_by_role("status")).to_have_text("初次见面……可以告诉我，你的名字吗？")
    page.screenshot(path=str(OUT / "initial.png"))
    source = Image.open(ROOT / "frontend/public/assets/naming/galstudy_male_name.png").convert("RGB")
    actual = Image.open(OUT / "initial.png").convert("RGB")
    delta = ImageChops.difference(source, actual)
    mask = ImageDraw.Draw(delta)
    mask.rectangle((1108, 435, 1592, 505), fill=0)
    mask.rectangle((125, 820, 1070, 910), fill=0)
    assert delta.getbbox() is None, delta.getbbox()
    field = page.get_by_role("textbox", name="玩家姓名")
    bounds = field.bounding_box()
    assert abs(bounds["x"] - 1115) < 2 and abs(bounds["y"] - 442) < 2, bounds
    page.get_by_role("button", name="开始故事").click()
    expect(page.locator("#name-error")).to_have_text("请先告诉我，你的名字。")
    field.fill("  林初夏  ")
    field.blur()
    page.screenshot(path=str(OUT / "entered.png"))
    button = page.get_by_role("button", name="开始故事")
    button.hover()
    assert button.evaluate("e => getComputedStyle(e).backgroundColor") != "rgba(0, 0, 0, 0)"
    field.focus()
    page.keyboard.press("Tab")
    assert button.evaluate("e => getComputedStyle(e).outlineStyle") == "solid"
    field.press("Enter")
    expect(page.get_by_role("status")).to_have_text("原来是林初夏啊。")
    expect(button).to_be_disabled()
    page.wait_for_timeout(700)
    page.screenshot(path=str(OUT / "reply.png"))
    expect(page.get_by_role("status")).to_have_text("那就请多指教啦！", timeout=4000)
    page.wait_for_url("**/male", timeout=10000)
    assert page.evaluate("localStorage.getItem('galstudy.playerName.male')") == "林初夏"

    # Storage failures remain recoverable and retain the typed name.
    page.goto(URL)
    expect(page.locator("[data-phase=editing]")).to_be_visible()
    page.evaluate("() => { Storage.prototype.setItem = () => { throw new Error('storage unavailable'); }; }")
    page.get_by_role("textbox", name="玩家姓名").fill("小雨")
    page.get_by_role("button", name="开始故事").click()
    expect(page.locator("#name-error")).to_contain_text("姓名暂时无法保存", timeout=7000)
    expect(page.get_by_role("textbox", name="玩家姓名")).to_have_value("小雨")
    expect(page.get_by_role("button", name="开始故事")).to_be_enabled()

    mobile = browser.new_page(viewport={"width": 844, "height": 390}, reduced_motion="reduce")
    mobile.goto(URL)
    expect(mobile.locator("[data-phase=editing]")).to_be_visible()
    mobile.wait_for_timeout(300)
    assert mobile.evaluate("document.documentElement.scrollWidth <= innerWidth")
    mobile.get_by_role("textbox", name="玩家姓名").fill("悠")
    mobile.screenshot(path=str(OUT / "mobile-landscape.png"))
    mobile.get_by_role("button", name="开始故事").click()
    mobile.wait_for_url("**/male", timeout=10000)
    assert not errors, errors
    result = {"source_size": [1672, 941], "unchanged_pixels_outside_interactive_regions": True,
              "checks": ["proportional alignment", "initial dialogue", "empty-name validation",
                         "real input", "hover and focus", "Enter submission", "both reply lines",
                         "name persistence", "fade-out navigation", "storage failure recovery",
                         "mobile landscape", "reduced motion"], "browser_errors": errors}
    (OUT / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    browser.close()
