"""Print an original bilingual, two-column and merged-table parser fixture."""

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "tests/samples"
HTML = """<!doctype html><meta charset="utf-8">
<style>
@page { size: A4; margin: 18mm; }
body { font-family: Arial, "Microsoft YaHei", sans-serif; font-size: 13px; line-height: 1.7; color: #111; }
h1 { font-size: 24px; } h2 { font-size: 17px; margin-top: 0; }
.columns { display: grid; grid-template-columns: 1fr 1fr; gap: 28px; }
table { width: 100%; border-collapse: collapse; margin-top: 14px; }
th, td { border: 1px solid #222; padding: 8px; text-align: left; }
caption { text-align: left; font-weight: bold; margin: 12px 0; }
</style>
<h1>学习笔记 Study notes</h1>
<div class="columns">
<section><h2>概念 Concepts</h2>
<p>检索练习是主动回忆已经学过的信息。合上书，复述要点，再用原文检查遗漏。</p>
<p>Retrieval practice uses active recall. Close the book, explain the key ideas, then check the source.</p>
</section>
<section><h2>练习 Practice</h2>
<p>间隔复习把练习安排在不同日期。再次复习时仍需要主动回忆。</p>
<p>Spaced practice separates study sessions. Use active recall again before checking your notes.</p>
</section></div>
<table><caption>表1 原创复习计划 Review plan</caption>
<tr><th>类别 Category</th><th>方法 Method</th><th>间隔 Interval</th><th>行动 Action</th></tr>
<tr><td rowspan="2">复习策略</td><td>检索练习</td><td>1天</td><td>合上书复述</td></tr>
<tr><td>间隔复习</td><td>3天</td><td>再次主动回忆</td></tr>
</table>
<h2>评分示例 Score example</h2>
<p>score = correct / total</p>
<p>答对3题，共4题，得分为0.75。Three correct answers out of four give a score of 0.75.</p>
<p>来源 Source · 本项目原创测试内容。</p>
"""


def main():
    SAMPLES.mkdir(exist_ok=True)
    target = SAMPLES / "original-layout.pdf"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page()
        page.set_content(HTML)
        page.pdf(path=str(target), prefer_css_page_size=True, print_background=True)
        browser.close()
    expected = {
        "headings": ["学习笔记", "概念", "练习", "评分示例"],
        "phrases": ["Retrieval practice", "Spaced practice", "score = correct / total", "0.75"],
        "table_cells": ["复习策略", "检索练习", "间隔复习", "1天", "3天", "合上书复述", "再次主动回忆"],
        "table_rows": 3, "table_columns": 4, "rowspan_cell": "复习策略",
        "source": "Original GalStudy HTML printed with local Edge, system fonts",
    }
    (SAMPLES / "original-layout.expected.json").write_text(json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
