"""Run against configured local services. Creates synthetic test accounts."""

import json
import os
import re
import time
import sys
from pathlib import Path
from uuid import uuid4
from playwright.sync_api import sync_playwright, expect
from make_samples import make_samples

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
ARTIFACTS = Path(os.getenv("E2E_ARTIFACTS_DIR", str(ROOT / "docs")))
ARTIFACTS.mkdir(parents=True, exist_ok=True)
BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:3000").rstrip("/")
BROWSER = os.getenv("E2E_BROWSER", "msedge")
samples = make_samples(ROOT / "tests/samples")


def register(page, email):
    page.get_by_role("button", name="登录 / 注册").click()
    page.get_by_role("button", name="第一次来？创建账号").click()
    page.get_by_role("textbox", name="邮箱").fill(email)
    page.get_by_label("密码", exact=True).fill("GalStudy-test-pass-2026")
    page.get_by_role("button", name="创建账号", exact=True).click()
    expect(page.get_by_role("heading", name="我的课程", exact=True)).to_be_visible()


def check_overflow(page):
    assert page.evaluate(
        "document.documentElement.scrollWidth <= window.innerWidth"
    ), "Horizontal overflow"


def enter_study(page):
    if os.getenv("E2E_DIRECT_STUDY") == "1":
        page.goto(BASE_URL + "/study")
        return
    page.goto(BASE_URL)
    page.get_by_role("button", name="跳过", exact=False).click()
    expect(page.get_by_role("heading", name="选择你的心动篇章")).to_be_visible()
    page.get_by_role("link").filter(has_text="男性向").click()
    expect(page).to_have_url(BASE_URL + "/study")


def exercise_companion(page, mobile=False):
    page.get_by_role("button", name="打开陪学伙伴", exact=True).click()
    question = page.get_by_label("向陪学伙伴提问", exact=True)
    expect(question).to_be_enabled()
    transcript = page.get_by_label("聊天记录", exact=True)
    if not mobile:
        question.fill("检索练习是什么？")
        page.get_by_role("button", name="发送陪学消息").click()
        expect(transcript).to_contain_text("人工校对后的检索练习知识点")
        expect(page.get_by_role("button", name="刷新会话")).to_be_enabled()
        page.get_by_role("button", name="刷新会话").click()
        expect(transcript).to_contain_text("人工校对后的检索练习知识点")
    with page.expect_response(
        lambda response: "/chat/sessions/" in response.url
        and response.request.method == "GET"
    ):
        page.get_by_label("陪学角色", exact=True).select_option(
            "rin" if mobile else "haruka"
        )
    expect(question).to_be_enabled()
    question.fill("未提供的天文学知识" if mobile else "检索练习")
    page.get_by_role("button", name="发送陪学消息").click()
    expect(transcript).to_contain_text("不能确定" if mobile else "先找依据")
    expect(page.get_by_role("button", name="刷新会话")).to_be_enabled()
    if not mobile:
        page.route(
            "**/api/chat/sessions/*/messages",
            lambda route: route.fulfill(
                status=200,
                content_type="text/event-stream",
                body='data: {"type":"error","message":"模型额度不足，请使用 Demo。"}\n\n',
            ),
            times=1,
        )
        question.fill("检索练习")
        page.get_by_role("button", name="发送陪学消息").click()
        expect(
            page.get_by_role("alert").filter(has_text="模型额度不足")
        ).to_be_visible()
        with page.expect_request(
            lambda request: "/messages" in request.url and request.method == "POST"
        ) as retry:
            page.get_by_role("button", name="使用 Demo 重试").click()
        assert retry.value.post_data_json["use_demo"] is True
        expect(page.get_by_role("button", name="刷新会话")).to_be_enabled()
        expect(
            page.get_by_role("alert").filter(has_text="模型额度不足")
        ).not_to_be_visible()
    page.screenshot(
        path=str(
            ARTIFACTS / ("companion-mobile.png" if mobile else "companion-desktop.png")
        ),
        full_page=True,
    )
    check_overflow(page)
    page.get_by_role("button", name="收起陪学", exact=True).click()
    if mobile:
        handle = page.get_by_role("button", name="拖动陪学伙伴")
        before = handle.bounding_box()
        page.mouse.move(before["x"] + 5, before["y"] + 5)
        page.mouse.down()
        page.mouse.move(20, 130, steps=8)
        page.mouse.up()
        assert handle.bounding_box()["x"] < before["x"]


def exercise_workshop(page, mobile=False):
    if mobile:
        page.get_by_role("button", name="打开导航").click()
    page.get_by_role("button", name="角色工坊", exact=True).click()
    expect(page.get_by_role("heading", name="你的专属陪学伙伴")).to_be_visible()
    page.get_by_label("角色参考图片", exact=True).set_input_files(
        str(ROOT / "frontend/public/assets/shiori.png")
    )
    page.get_by_role("checkbox").first.check()
    page.get_by_role("button", name="上传参考图", exact=True).click()
    page.get_by_role("button", name="模拟审核通过", exact=True).click()
    page.get_by_role("button", name="创建模拟订单", exact=True).click()
    page.get_by_role("button", name="模拟付款失败", exact=True).click()
    expect(page.get_by_role("button", name="开始生成角色包")).to_be_disabled()
    page.get_by_role("button", name="模拟付款成功", exact=True).click()
    name = "青禾" if mobile else "星野"
    page.get_by_label("角色名字", exact=True).fill(name)
    page.get_by_label("角色人设", exact=True).fill(
        "耐心、清晰，喜欢通过提问陪同学一起回忆知识。"
    )
    page.get_by_label("对你的称呼", exact=True).fill("同学")
    page.get_by_label("外观偏好", exact=True).fill("校园风开衫")
    page.get_by_role("button", name="开始生成角色包", exact=True).click()
    expect(page.get_by_role("img", name=name, exact=True)).to_be_visible(timeout=25000)
    page.screenshot(
        path=str(
            ARTIFACTS / ("workshop-mobile.png" if mobile else "workshop-desktop.png")
        ),
        full_page=True,
    )
    page.get_by_role("button", name="设为陪学角色", exact=True).click()
    expect(page.get_by_role("button", name="当前陪学角色", exact=True)).to_be_disabled()
    if mobile:
        page.get_by_role("button", name="打开导航").click()
    page.get_by_role("button", name="学习首页", exact=True).click()
    page.get_by_role("button", name="先体验一段原创故事").click()
    expect(page.locator(".player-sprite")).to_have_attribute(
        "src", re.compile(r"^/api/workshop/assets/")
    )
    expect(page.locator(".speaker")).to_contain_text(name)
    page.locator(".player-sprite").evaluate("(image)=>image.decode()")
    page.screenshot(
        path=str(
            ARTIFACTS
            / (
                "custom-character-mobile.png"
                if mobile
                else "custom-character-desktop.png"
            )
        ),
        full_page=True,
    )
    page.get_by_role("button", name="打开陪学伙伴", exact=True).click()
    expect(page.get_by_label("陪学角色", exact=True)).to_have_value(
        re.compile(r"^[0-9a-f-]{36}$")
    )
    question = page.get_by_label("向陪学伙伴提问", exact=True)
    expect(question).to_be_enabled()
    question.fill("检索练习")
    page.get_by_role("button", name="发送陪学消息").click()
    expect(page.get_by_label("聊天记录", exact=True)).to_contain_text("我是" + name)
    expect(page.get_by_role("button", name="刷新会话")).to_be_enabled()
    page.get_by_role("button", name="收起陪学", exact=True).click()
    check_overflow(page)


with sync_playwright() as p:
    browser = (
        getattr(p, BROWSER).launch(headless=True)
        if BROWSER in {"webkit", "firefox", "chromium"}
        else p.chromium.launch(channel=BROWSER, headless=True)
    )
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    enter_study(page)
    expect(page.get_by_role("heading", name="今天，也一起向前一点吧")).to_be_visible()
    page.screenshot(path=str(ARTIFACTS / "home-desktop.png"), full_page=True)
    email = "e2e-" + uuid4().hex[:10] + "@example.com"
    register(page, email)
    page.get_by_role("button", name="新建学习项目").click()
    page.get_by_label("课程名称").fill("原创上传测试")
    page.get_by_role("button", name="创建学习项目", exact=True).click()
    expect(page.get_by_role("heading", name="原创上传测试")).to_be_visible()
    for ext in ["pdf", "pptx", "docx"]:
        page.locator("input[type=file]").set_input_files(
            str(samples / ("original." + ext))
        )
        expect(page.get_by_text("original." + ext, exact=True)).to_be_visible()
        expect(page.get_by_text("解析完成", exact=True)).to_have_count(
            ["pdf", "pptx", "docx"].index(ext) + 1, timeout=20000
        )
    point = page.get_by_role("textbox", name="知识点内容").first
    point.fill("人工校对后的检索练习知识点")
    page.get_by_role("button", name="确认知识点").first.click()
    expect(page.get_by_text("已确认", exact=True)).to_be_visible()
    exercise_companion(page)
    page.screenshot(path=str(ARTIFACTS / "knowledge-desktop.png"), full_page=True)

    def delayed_restore(route):
        time.sleep(0.5)
        route.continue_()

    page.route("**/api/auth/me", delayed_restore, times=1)
    page.reload(wait_until="domcontentloaded")
    # The app starts on home after reload, persisted project data is reloaded from the API.
    page.get_by_role("button", name="我的课程", exact=True).click()
    page.get_by_role("button", name="进入项目").click()
    expect(page.get_by_role("textbox", name="知识点内容").first).to_have_value(
        "人工校对后的检索练习知识点"
    )
    page.get_by_role("button", name="生成 Demo 剧情", exact=True).click()
    page.get_by_role("button", name="先和小栞梳理笔记").click()
    expect(page.locator(".dialogue")).to_contain_text("人工校对后的检索练习知识点")
    page.get_by_role("button", name="带上笔记，去图书馆").click()
    expect(page.locator(".player-bg")).to_have_attribute("src", "/assets/library.webp")
    expect(page.locator(".player-sprite")).to_have_attribute(
        "src", "/assets/haruka.png"
    )
    page.locator(".player-bg").evaluate("(image) => image.decode()")
    page.locator(".player-sprite").evaluate("(image) => image.decode()")
    page.screenshot(path=str(ARTIFACTS / "course-story-desktop.png"), full_page=True)
    page.get_by_role(
        "button", name="只要记住课程名称，就能推断资料中的所有结论。"
    ).click()
    expect(page.get_by_label("知识来源")).to_contain_text("original.")
    page.get_by_role("button", name="查看错题手记").click()
    card = page.locator(".wrong-item").filter(has_text="书页里的线索")
    card.get_by_role("button", name="开始复习").click()
    card.get_by_role("radio", name="人工校对后的检索练习知识点", exact=True).check()
    card.get_by_role("button", name="提交复习答案").click()
    expect(card.get_by_text("已复习", exact=True)).to_be_visible()
    page.get_by_role("button", name="我的课程", exact=True).click()
    page.get_by_role("button", name="进入项目").click()
    page.get_by_role("button", name="继续剧情").click()
    page.get_by_role("button", name="重玩最新版本").click()
    page.get_by_role("button", name="跟遥来一次回忆练习").click()
    page.get_by_role("button", name="准备好了，开始资料挑战").click()
    page.get_by_role("button", name="人工校对后的检索练习知识点", exact=True).click()
    expect(page.get_by_text("结局 · 书签上的星光", exact=False)).to_be_visible()
    page.get_by_role("button", name="学习首页", exact=True).click()
    page.get_by_role("button", name="先体验一段原创故事").click()
    page.get_by_role("button", name="请遥带我做一个实验").click()
    page.get_by_role("button", name="准备好了，开始挑战").click()
    expect(page.locator(".player-bg")).to_have_attribute("src", "/assets/library.webp")
    page.locator(".player-bg").evaluate("(image) => image.decode()")
    page.locator(".player-sprite").evaluate("(image) => image.decode()")
    page.screenshot(path=str(ARTIFACTS / "story-desktop.png"), full_page=True)
    page.get_by_role("button", name="一直看着书重复阅读").click()
    expect(page.get_by_text("结局 · 明天再试一次", exact=False)).to_be_visible()
    page.get_by_role("button", name="查看错题手记").click()
    expect(
        page.get_by_role("heading", name="第二章 · 记忆的回声", exact=False)
    ).to_be_visible()
    page.get_by_role("button", name="退出登录").click()
    page.get_by_role("button", name="登录 / 注册").click()
    page.get_by_label("邮箱", exact=True).fill(email)
    page.get_by_label("密码", exact=True).fill("GalStudy-test-pass-2026")
    page.get_by_role("button", name="登录，继续旅程").click()
    expect(page.get_by_role("heading", name="我的课程", exact=True)).to_be_visible()
    page.get_by_role("button", name="学习首页", exact=True).click()
    page.get_by_role("button", name="先体验一段原创故事").click()
    expect(page.get_by_text("结局 · 明天再试一次", exact=False)).to_be_visible()
    check_overflow(page)
    mobile = browser.new_context(
        viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
    )
    phone = mobile.new_page()
    enter_study(phone)
    phone.screenshot(path=str(ARTIFACTS / "home-mobile.png"), full_page=True)
    check_overflow(phone)
    register(phone, "e2e-phone-" + uuid4().hex[:10] + "@example.com")
    phone.get_by_role("button", name="打开导航").click()
    phone.get_by_role("button", name="学习首页", exact=True).click()
    expect(phone.locator(".sidebar.shown")).to_have_count(0)
    phone.get_by_role("button", name="先体验一段原创故事").click()
    phone.get_by_role("button", name="和小栞一起理解概念").click()
    phone.get_by_role("button", name="我明白了，去图书馆试试").click()
    expect(phone.locator(".player-bg")).to_have_attribute("src", "/assets/library.webp")
    expect(phone.locator(".player-sprite")).to_have_attribute(
        "src", "/assets/haruka.png"
    )
    phone.locator(".player-bg").evaluate("(image) => image.decode()")
    phone.locator(".player-sprite").evaluate("(image) => image.decode()")
    phone.screenshot(path=str(ARTIFACTS / "story-mobile.png"), full_page=True)
    check_overflow(phone)
    phone.get_by_role("button", name="合上书，凭记忆复述要点").click()
    expect(phone.get_by_text("结局 · 一起向前", exact=False)).to_be_visible()
    phone.get_by_role("button", name="打开导航").click()
    phone.get_by_role("button", name="我的课程", exact=True).click()
    phone.get_by_role("button", name="新建学习项目").click()
    phone.get_by_label("课程名称").fill("LongCourse" * 12)
    phone.get_by_role("button", name="创建学习项目", exact=True).click()
    phone.get_by_role("button", name="补充", exact=True).click()
    phone.get_by_role("textbox", name="知识点内容").fill("学" * 5000)
    phone.get_by_role("button", name="确认知识点").click()
    phone.get_by_role("button", name="生成 Demo 剧情", exact=True).click()
    phone.get_by_role("button", name="先和小栞梳理笔记").click()
    expect(phone.locator(".dialogue")).to_contain_text("学" * 5000)
    check_overflow(phone)
    phone.get_by_role("button", name="带上笔记，去图书馆").click()
    expect(phone.locator(".choices")).to_contain_text("学" * 600)
    check_overflow(phone)
    phone.get_by_role("button", name="学" * 600, exact=True).click()
    expect(phone.get_by_text("结局 · 书签上的星光", exact=False)).to_be_visible()
    exercise_companion(phone, mobile=True)
    exercise_workshop(page)
    exercise_workshop(phone, mobile=True)
    # Chromium prints Chinese text with a ToUnicode map, a reproducible mixed-language PDF fixture.
    printer = p.chromium.launch(channel="msedge", headless=True) if BROWSER in {"webkit", "firefox"} else None
    try:
        document = printer.new_page() if printer else context.new_page()
        document.set_content(
            '<meta charset="utf-8"><h1>学习方法 Study methods</h1><p>检索练习 Retrieval practice 是主动回忆。</p><table><tr><td>方法 Method</td><td>示例 Example</td></tr><tr><td>Recall</td><td>合上书复述</td></tr></table>'
        )
        document.pdf(path=str(samples / "original-chinese.pdf"))
    finally:
        if printer:
            printer.close()
    from backend.parsers import parse_document

    chunks = parse_document(
        "original-chinese.pdf", (samples / "original-chinese.pdf").read_bytes()
    )
    assert "学习方法" in chunks[0][1] and "Study methods" in chunks[0][1]
    assert not errors, errors
    (ARTIFACTS / "e2e-result.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "browser": BROWSER,
                "browser_version": browser.version,
                "desktop": [1440, 1000],
                "mobile": [390, 844],
                "checks": [
                    "registration",
                    "three uploads",
                    "edit and confirm",
                    "reload persistence",
                    "delayed session restoration before course navigation",
                    "confirmed knowledge to course story",
                    "course source references",
                    "wrong answer review",
                    "replay latest story",
                    "wrong branch",
                    "wrong notebook",
                    "logout and login resume",
                    "correct branch on mobile",
                    "mobile max-length course title and knowledge",
                    "overflow",
                    "mixed Chinese PDF",
                    "direct learning entry" if os.getenv("E2E_DIRECT_STUDY") == "1" else "intro and selection entry preserved",
                    "course companion retrieval and character switching",
                    "chat persistence and mobile unknown answer",
                    "mobile companion dragging and collapse",
                    "model failure shown and explicit Demo retry",
                    "reference upload and simulated review",
                    "failed and successful Mock payment",
                    "entitlement to job and character delivery",
                    "custom character in story and companion on desktop and mobile",
                ],
                "page_errors": errors,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    browser.close()
    print("E2E passed, screenshots saved to docs/", flush=True)
