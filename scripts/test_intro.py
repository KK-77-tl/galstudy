"""Browser regression checks for the entrance, against a running Next.js server."""
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3003"
OUT = Path(__file__).resolve().parents[1] / "test-results" / "intro"
OUT.mkdir(parents=True, exist_ok=True)


def start(page):
    page.goto(BASE)
    expect(page.locator("[data-state=playing]")).to_be_visible()
    assert page.locator("section img").evaluate_all(
        "images => images.every(image => image.complete && image.naturalWidth > 0)"
    )


def sample(page):
    return page.locator("section[aria-label='GalStudy 入场动画']").evaluate("""root => {
      const [scene, title] = root.querySelectorAll(':scope > div');
      return {
        elapsed: title.getAnimations()[0].currentTime,
        scene: Number(getComputedStyle(scene).opacity),
        title: Number(getComputedStyle(title).opacity),
        transform: getComputedStyle(scene.firstElementChild).transform,
        background: getComputedStyle(root).backgroundColor,
        overflow: document.documentElement.scrollWidth > innerWidth,
      };
    }""")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    errors = []
    context.on("weberror", lambda error: errors.append(str(error.error)))
    page = context.new_page()
    start(page)
    started = time.monotonic() - sample(page)["elapsed"] / 1000
    samples = []
    for at in [0, 2, 4.2, 6.6, 7.8, 9.4]:
        page.wait_for_timeout(max(0, (started + at - time.monotonic()) * 1000))
        samples.append(sample(page))
        if at in [2, 6.6, 9.4]:
            page.screenshot(path=str(OUT / f"desktop-{at}.png"))
    assert samples[1]["scene"] == 1 and samples[1]["title"] == 0
    assert 0 < samples[2]["scene"] < 1
    assert samples[3]["scene"] == samples[3]["title"] == 0, samples
    assert 0 < samples[4]["title"] < 1
    assert samples[5]["title"] == 1
    assert all(s["background"] == "rgb(0, 0, 0)" and not s["overflow"] for s in samples)
    page.wait_for_url("**/select")
    elapsed = time.monotonic() - started
    assert 9.8 < elapsed < 11, elapsed
    expect(page.get_by_role("heading", name="选择你的心动篇章")).to_be_visible()
    page.screenshot(path=str(OUT / "selection-desktop.png"))

    # Mouse skip and the selection's existing-app destination.
    start(page)
    skipped = time.monotonic()
    page.get_by_role("button", name="跳过").click()
    page.wait_for_url("**/select")
    assert time.monotonic() - skipped < 2
    page.get_by_role("link", name="放学后的约定").click()
    page.wait_for_url("**/study")
    assert page.evaluate("localStorage.getItem('galstudy.audience')") == "male"
    expect(page.get_by_role("heading", name="今天，也一起向前一点吧")).to_be_visible()

    # Mobile portrait keeps both entire source images and a 44px touch target.
    mobile = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    phone = mobile.new_page()
    start(phone)
    phone.wait_for_timeout(2000)
    assert not sample(phone)["overflow"]
    assert phone.locator("section img").first.evaluate("e => getComputedStyle(e).objectFit") == "contain"
    assert phone.get_by_role("button", name="跳过").bounding_box()["height"] >= 44
    phone.screenshot(path=str(OUT / "mobile-classroom.png"))
    phone.get_by_role("button", name="跳过").tap()
    phone.wait_for_url("**/select")
    phone.screenshot(path=str(OUT / "selection-mobile.png"), full_page=True)
    phone.get_by_role("link", name="书页间的邂逅").tap()
    phone.wait_for_url("**/study")
    assert phone.evaluate("localStorage.getItem('galstudy.audience')") == "female"

    # Reduced motion preserves the 10s sequence and removes all camera movement.
    reduced = browser.new_context(reduced_motion="reduce")
    quiet = reduced.new_page()
    start(quiet)
    quiet.wait_for_timeout(2000)
    assert sample(quiet)["transform"] == "none"
    quiet.wait_for_url("**/select", timeout=12000)

    # Keyboard skipping works even while assets are still downloading.
    loading = context.new_page()
    loading.route("**/assets/intro/*.png", lambda route: route.abort())
    loading.goto(BASE)
    expect(loading.locator("[data-state=error]")).to_be_visible()
    loading.get_by_role("button", name="跳过").focus()
    loading.keyboard.press("Enter")
    loading.wait_for_url("**/select")

    # Hold image responses to verify that the sequence waits on actual assets.
    slow = context.new_page()
    pending = []
    slow.route("**/assets/intro/*.png", lambda route: pending.append(route))
    slow.goto(BASE, wait_until="domcontentloaded")
    expect(slow.locator("[data-state=loading]")).to_be_visible()
    slow.wait_for_timeout(800)
    assert slow.locator("[data-state=loading]").count() == 1
    assert slow.locator("section").evaluate("e => getComputedStyle(e).backgroundColor") == "rgb(0, 0, 0)"
    for route in pending:
        route.continue_()
    expect(slow.locator("[data-state=playing]")).to_be_visible()
    assert sample(slow)["elapsed"] < 500
    slow.get_by_role("button", name="跳过").click()
    slow.wait_for_url("**/select")
    assert not errors, errors
    result = {"full_playback_seconds": round(elapsed, 3), "samples": samples,
              "passed": ["desktop full playback", "mouse skip", "mobile touch skip",
                         "male/female selection", "mobile image framing", "reduced motion full playback",
                         "asset failure keyboard skip", "delayed image preload"], "browser_errors": errors}
    (OUT / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    browser.close()
