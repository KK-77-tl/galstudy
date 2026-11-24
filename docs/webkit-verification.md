# WebKit兼容性检查 · 2026-11-23

在Windows上使用Playwright 1.58.0和官方WebKit 26.0（构建2248）执行现有学习页回归。全程Demo/Mock，无真实模型、生图或付款。独立SQLite库和Next生产服务由scripts/browser_engine_check.py创建并关闭，不访问个人浏览器会话。

结果见[WebKit流程记录](webkit/e2e-result.json)及[运行与清理记录](webkit/runner-result.json)。桌面1440×1000、手机视口390×844通过三格式上传、知识点校对、双分支剧情、服务器判分、错题、重玩、退出登录续玩、角色切换、聊天引用与未知提示、流式失败后的显式Demo重试、手机悬浮拖动、Mock订单权益和角色交付。页面错误列表为空，横向溢出检查通过；临时API和Next均已关闭。

测试直接进入/study，不覆盖序章或篇章选择。手机是桌面WebKit的视口模拟，未验证触屏、iOS系统交互、Safari品牌浏览器、Android真机或真实移动网络。[Playwright说明其WebKit版本与Safari的关系](https://playwright.dev/python/docs/browsers)。因此真机验收继续开放。

首次运行在全部页面交互后因WebKit不支持page.pdf而失败。该操作只生成原创中英教材，现改为独立Edge打印实例，学习页全程仍由WebKit运行。重跑完整通过，失败日志保存在test-results/webkit-cddaac69cec440d7a1427b2d55eb6d48/e2e.log。当前通过记录的测试目录见runner-result.json。

官方浏览器及FFmpeg、Winldd安装到忽略的data/playwright-browsers，不加入生产镜像。下载时首个CDN有TLS重置，Playwright自动使用官方备用下载源后成功。现有Edge/Chrome报告未覆盖。桌面聊天与手机专属角色截图已人工检查。

## 复跑

需要现有frontend生产构建和后端开发依赖，并在项目根目录执行：

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PWD 'data/playwright-browsers'
.\.venv\Scripts\python.exe -m playwright install webkit
.\.venv\Scripts\python.exe scripts/browser_engine_check.py webkit
```

运行器将模式固定为Demo/Mock，使用新数据库，不会读取模型凭证发起云请求。截图和报告单独保存于docs/webkit，原始测试库和日志保留于test-results。本轮只改测试工具，未改网页或业务代码。
