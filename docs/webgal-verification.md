# WebGAL 同源运行与引擎路线对照

验证日期为2026-11-17。WebGAL官方发布版4.6.7在独立Next.js 16.4.6生产构建中运行，React及React DOM为19.3.1，浏览器为Edge 157.0.4341.60。实验宿主与课程API仅监听本机回环地址，数据库和账号均为本轮自动生成的测试数据。[官方发布页](https://github.com/OpenWebGAL/WebGAL/releases/tag/4.6.7)

## 复跑

在项目根目录执行以下PowerShell命令。首次准备会下载固定版本归档和官方许可证，归档与引擎位于已忽略的data目录。

```powershell
.\.venv\Scripts\python.exe scripts\prepare_webgal.py
.\.venv\Scripts\python.exe scripts\webgal_probe.py
```

脚本依赖现有frontend/node_modules、项目虚拟环境、Playwright和Edge。每轮在test-results/webgal-*创建独立Next项目，链接已有依赖，构建并启动临时宿主。/custom直接导入当前学习页与样式，通过真实课程API运行同一原创Demo。测试代理共享一个合成账号的TestClient会话。该会话代理只用于本机隔离实验。

本次报告为webgal-same-origin-result.json，记录status=passed、next_stopped=true、fixture_stopped=true及api_context_closed=true。图像提示词和生成来源保存于assets.json。

## 动态脚本、业务事件与续玩

1. 原创图包含教室与图书馆、小栞与遥、concept/practice两条分支、检索练习题，以及success/review两个结局。WebGAL按请求从服务端取得转换后的.txt脚本。小栞开心及遥温柔状态使用新增的独立PNG表情变体。
2. React客户端组件以条件渲染装载iframe，useEffect安装同源点击监听并在卸载时移除监听、取消待处理fetch。实验共执行三次装载和卸载，卸载后iframe数量为0，CDP报告Frames恢复为1。
3. WebGAL在用户点击前请求两个起始分支。GET只构造和返回脚本，预取结束时服务端仍为start、version=0。
4. 捕获题目选项点击后，桥接层先读取当前公开节点，再POST choice/version。FastAPI完成版本条件更新、判分和存档提交。只有成功响应才重新派发一次引擎原生点击。
5. 一次故意使用过期版本的提交返回409，网页显示冲突，服务端节点和版本保持原值，原选项仍可点击。再次提交成功后正常进入concept。
6. 首条路径到达quiz时version=2，卸载并重新装载后仍为quiz、version=2，网页显示原题两个选项。答对到达success、score=1，响应含解析。
7. 显式重玩后选择practice，再答错到达review、score=0，响应含解析，错题API返回1条记录。WebGAL收到6次成功业务推进，含两次题目评分。
8. 当前自有播放器通过同一课程完成concept→quiz→success，分数为1，并验证立绘src切换为shiori-happy.png。两个页面的pageerror均为空。

题目截图为webgal-quiz.png与engine-custom-quiz.png，结局截图为webgal-success.png、webgal-review.png及engine-custom-success.png。

## 资源测量

下表来自同一次本机浏览器实验，窗口1440×1000。Resource Timing的decodedBodySize按实际请求累加，包含脚本、样式、字体、图片、配置和API响应，重复请求会重复计量。两条路线各自使用新的浏览器上下文，测量终点均为同一原创题目。WebGAL列包含宿主和iframe，当前播放器列包含应用首页到题目的完整页面资源。两者初始界面及资源策略不同。

| 指标 | WebGAL与React宿主 | 当前自有播放器 |
| --- | --- | --- |
| 到题目累计响应正文 | 56,842,865字节 | 5,455,685字节 |
| JavaScript正文 | 2,025,440字节 | 588,887字节 |
| CSS正文 | 47,833字节 | 31,629字节 |
| TTF字体正文 | 37,829,416字节 | 0字节 |
| 显式GC后的JS堆 | 10.42MiB | 4.58MiB |

WebGAL发布归档为52,842,728字节，SHA256为7baf45d78e5c5924a08fcd1974e776452b71b5477d8a6449e4e967c845b95578，与官方Release资产digest一致。归档包含默认游戏资源，准备脚本提取时跳过game/，实验使用项目原创场景、角色和脚本。其余引擎文件共26个、39,819,705字节，其中三个字体共37,829,416字节。

CDP的JSHeapUsedSize在空宿主为1.97MiB，三次卸载后分别为3.73、3.79、3.83MiB。采样覆盖JavaScript堆，原生内存、字体解码、GPU资源及浏览器总RSS尚未测量。三次采样只能证明本轮装卸和帧移除，长期泄漏结论仍需持续测试。原始CPU计数从各页面启用Performance域时累计，交互路径也不同，CPU跨路线基准保持未测试。

## 集成范围与技术决定

WebGAL发布构建在本次浏览器中只暴露__WEBGAL_DEVICE_INFO__，window.WebGAL不存在。源码中的单例属于模块内部。当前桥依赖4.6.7的选项DOM类名与原生点击行为，升级引擎需要回归。[固定版本入口源码](https://github.com/OpenWebGAL/WebGAL/blob/4.6.7/packages/webgal/src/main.tsx)

续玩通过应用的服务端节点重新生成start.txt。原生引擎快速存档、读档、回想、跳行位置、镜头、音频和变量快照尚未接入业务存档。实时AI私有课程脚本、断线恢复及多人并发状态桥保持未验证。公开原创Demo的预取允许浏览器读取未来分支和结局，正式私有题目的脚本发布策略需要另行实现。

官方归档引用的两个可选Live2D脚本缺失，本次各次装载均产生相应404。静态立绘路径正常，Live2D功能保持未验证。另一个409来自故意注入的版本冲突用例。

当前继续采用自有JSON状态机。它已通过应用正常入口验证资料、评分、来源与持久化事务。WebGAL在复杂演出方面可作为后续候选，当前接入需要维护版本相关的事件桥、预取发布策略和双存档协调。未来迭代成本尚无工时基准。

上游引擎、字体、UI图标和声音仅保存在忽略的研究目录。正式分发前需按实际使用文件完成MPL-2.0及各素材声明复核，登记见licenses.md。[固定版本许可证](https://github.com/OpenWebGAL/WebGAL/blob/4.6.7/LICENSE)
