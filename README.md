# GalStudy

与知识，怦然相遇。面向学生的课件知识校对与视觉小说学习平台，按 PRD v1.1 分阶段开发。

## 当前可用

- 中文校园风首页与原创 AI 演示背景、角色立绘。
- 邮箱密码注册、登录、退出，Argon2 密码哈希，服务端持久化会话。
- 私有学习项目、PDF/PPTX/DOCX 上传、异步解析、来源原文与位置。
- Demo摘录或可配置云端知识提炼，原文引用、类型、编辑、确认、删除和手工补充。
- 原创双章节演示，以及自有课程确认知识点到Demo或云端双章节剧情的生成流程。
- 两条起始分支、摘录识别题、答案解析、来源原文、两种结局、错题复习、重玩和退出续玩。
- 剧情版本持久化，新版本保留当前存档，重玩进入最新版。删除原文件会清理引用它的剧情版本及关联存档、答题记录。
- 桌面与390px手机浏览器验收脚本、原始样本与测试截图。
- 小栞、遥、凛三名陪学角色，课程内资料检索、流式聊天、会话保存与有界摘录记忆。
- 学习页的悬浮陪学组件，可拖动、收起、选择课程和角色，显示来源与剩余额度。
- 角色工坊的私有参考图、授权确认、模拟审核、订单、Mock付款、一次性权益、生成任务与个人角色库。

默认知识提炼和剧情生成使用明确标示的Demo模板，课程题目采用确认知识点的摘录识别。配置LLM_MODE=cloud后可调用结构化知识提炼和剧情生成适配器，每次剧情支持1至12条确认知识点。自由聊天单独配置云模式。云端协议已用模拟HTTP传输验证，真实模型输出质量仍待验收。角色工坊默认使用Mock支付和演示立绘。支付宝Provider、通知/查询与退款界面已接入并通过本地模拟验收，远程沙箱及真实付款、ComfyUI交付仍待验证，见docs/alipay-integration-verification.md。扫描PDF提供可配置的本地Tesseract OCR，默认关闭，见docs/ocr.md。

现有网站入口包含序章动画与篇章选择，选择后进入 /study 学习页。新陪学组件接入该学习页。

## 陪学与云聊天配置

默认无需任何模型密钥。Demo 回复会根据当前课程的已确认知识点返回相关摘录，不匹配时提示不确定。角色分别使用温柔梳理、证据推理和提问练习的语言风格。每个账号、课程、角色拥有独立会话。删除原文件会清空本课程聊天，以及引用该文件的剧情版本、存档和答题记录。

如需云聊天，在服务端.env设置LLM_CHAT_MODE=cloud、LLM_API_KEY、LLM_BASE_URL和LLM_MODEL。知识点与剧情通过LLM_MODE=cloud单独开启，复用这三个配置。地址、模型和资料处理区域采用服务商及账号的有效配置，模型须支持JSON Object输出。配置齐全后重启API，文件、知识点、剧情与聊天按实际模式显示。缺少必要配置时使用Demo，已经发起的云请求失败会明确报错，用户可显式选择Demo重试。2026-11-23已执行Cloudflare真实调用：Qwen知识提炼与逐字引用通过，剧情格式被拒绝，GLM及本机网关链路出现超时。完整云端验收仍未通过，本机默认保持Demo，详见docs/cloud-live-verification.md。详见docs/cloud-learning.md。[Qwen官方兼容接口](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope)

服务端配置每日用户/全局请求上限、预留token上限、最大512输出token及30秒总超时。预留量按输入UTF-8字节数加输出与协议余量估算，失败请求继续占用预留额度。80%用量显示告警，额度用完返回429。该计数用于调用约束，实际费用以服务商账单及配置的模型价格为准。时区按UTC+8重置每日额度。

知识提炼和剧情共用上述每日请求/token预算，分别限制4096与8192输出token，单次请求默认45秒总超时。长资料按每段最多12000字符分批提炼，任何一批失败都保持整份文件未发布，最多3次人工重试。详细错误、原子发布和并发控制见cloud-learning.md。

模型服务超时、授权失败、余额不足或限流会显示明确错误，用户可显式选择 Demo 重试。没有相关课程证据时使用标示为 Demo 的未知提示，避免把无依据内容当作课程答案。[Qwen 官方流式输出](https://www.alibabacloud.com/help/en/model-studio/stream)

## 本地启动

需要 Node.js 24、Python 3.12。本机默认 SQLite，数据保存在 data/galstudy.db，适合开发验收。

创建项目虚拟环境并安装后端依赖。一键启动脚本会优先使用该虚拟环境。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip==26.3
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

在项目根目录运行启动脚本，前端依赖首次自动安装，API 与网页随后启动。访问 http://localhost:3000，在网页注册自己的测试账号。停止前端时脚本会关闭它启动的 API 进程。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

也可分别运行以下命令。

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

API 健康端点为 http://localhost:8000/api/health，OpenAPI 为 http://localhost:8000/docs。前端 /api 经 Next.js 代理，同源 Cookie 处理认证。未登录用户只能浏览首页和账号弹窗，私有 API 返回401。

## 生产构建与容器配置

```powershell
cd frontend
npm.cmd run build
npm.cmd run start
```

容器运行需要 Docker Compose。复制 .env.example 到 .env，为 POSTGRES_PASSWORD 设置本地数据库密码。密码放入 URL 时须符合 URL 编码要求。当前 Compose 使用私有内部 PostgreSQL 与 API，仅将网页端口绑定本机回环地址。

```powershell
docker compose up --build
```

2026-11-18已在已有Ubuntu WSL完成Docker Compose实际构建、网络、持久卷、重启、完整浏览器流程与备份恢复验收，复跑方式和范围见docs/compose-verification.md。PostgreSQL 17.12已通过原生Windows临时集群执行迁移1至6及完整55项后端回归，复跑脚本和范围见docs/postgresql-verification.md。公网HTTPS、正式服务器、备案与收费接入保留至具备资源和用户授权后。HTTPS环境应设置COOKIE_SECURE=true和正确APP_ORIGIN。

## 自动化验证

测试依赖单独安装，浏览器脚本默认使用本机 Microsoft Edge。设置 E2E_BROWSER=chrome 可切换为已安装的Chrome，E2E_BASE_URL可指定网页地址。

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe scripts/make_samples.py
.\.venv\Scripts\python.exe scripts/benchmark.py
Push-Location frontend
npm.cmd test
npm.cmd run typecheck
Pop-Location
```

浏览器验收需先启动 API 与生产构建或开发网页，再运行以下命令。脚本创建独立的测试账号，上传三种原创样本，并保存桌面/手机截图。测试账号会保留在本地数据库。

```powershell
.\.venv\Scripts\python.exe scripts/e2e.py
```

## 文档与验收证据

- docs/requirements-v1.1.txt 保存完整需求。
- docs/opensource-research.md 记录开源核查、资源实验与待测项目。
- docs/architecture-decisions.md 记录路线比较、数据关系、API 契约与目录。
- docs/licenses.md 登记直接依赖、研究项目与演示素材。
- docs/parser-benchmark.json 保存真实采样结果。
- docs/e2e-result.json 保存浏览器验收检查项。
- docs/migration-result.json 保存旧存档兼容性检查，backend/schemas/story.schema.json 保存故事图 JSON Schema。
- docs/home-desktop.png、home-mobile.png、knowledge-desktop.png、story-desktop.png、story-mobile.png 为实际页面截图。
- docs/course-story-desktop.png 展示由上传资料中的确认知识点生成的 Demo 剧情。
- docs/workshop.md 记录角色工坊、Mock支付、权益、ComfyUI适配和隐私策略。
- docs/workshop-desktop.png、workshop-mobile.png、custom-character-desktop.png、custom-character-mobile.png 保存工坊与人物实际使用截图。
- docs/todo.md 按阶段列出完成项和剩余工作。
- docs/cloud-learning.md 记录云端结构化输出、来源绑定、共享预算与并发发布规则。
- docs/postgresql-verification.md、postgresql-result.json与postgresql-test-result.txt记录真实PostgreSQL迁移、回归及临时服务关闭结果。
- docs/demo-script.md 提供约2分40秒演示脚本及90秒压缩版。
- docs/submission-draft.md 提供参赛介绍、官方赛事入口和待填材料。
- docs/contest-verification.md与contest-sources.json记录最新赛事条款核查、时间差异和真实服务所需资源。
- docs/launch-checklist.md 记录本地验收、上线条件、资源限额与已知限制。
- docs/npm-audit.json、python-audit.json、dependency-inventory.json 记录依赖检查与包级许可元数据。
- docs/performance-result.json 记录本地课程详情及HTML请求采样。
- docs/network-verification.md、network-result.json记录桌面/手机视口固定弱网及断线恢复，复跑脚本为scripts/network_probe.py。
- docs/compose-verification.md、compose-result.json记录实际Linux容器、重启、浏览器流程与备份恢复。

## 当前限制

WebGAL 4.6.7已通过独立Next生产宿主的同源装卸、动态题目桥、409回退、节点续玩与资源实测，复跑方法和边界见docs/webgal-verification.md。生产私有课程桥、原生存档同步与长期资源释放仍待验证。Docling已在独立CPU环境完成五类样本对照，能还原原创跨行表格，当前扫描OCR配置存在中文遗漏。资源和复跑记录见docs/docling-verification.md。普通 PDF 保留页码与文本，复杂表格结构未恢复。DOCX 返回内容块编号，Word 页码依赖排版引擎。

任务由单 API worker 处理，当前应以一个 Uvicorn worker 启动。解析在独立子进程中运行，45秒超时终止，失败任务最多尝试3次。登录每IP每分钟30次、全局120次，认证并发2个，上传并发2个，其他写请求并发16个。请求体在解析前限制，包含无长度头的分块上传，读入最多30秒。账号切换会拒绝旧请求的迟到响应。

图像新任务每天5个/用户、20个/全局，提交生成服务另有15次/用户、60次/全局的每日上限，包含跨日重试和失败提交。默认限额由实施阶段设定，配置项见.env.example，完整规则见launch-checklist.md。内存登录限流按单进程计算，重启会清零。分布式worker租约、邮箱验证、密码找回、对象存储、发布镜像及原生组件许可审查与生产负载测试仍需补齐。

角色与场景素材通过内置 imagegen 生成，工具与提示词记录见 docs/licenses.md。真实模型、GPU、支付与公开部署的条件和待办见阶段清单。


支付宝可按服务端配置选择Mock、沙箱或正式Provider。配置、只读密钥挂载、99项回归及远程验收缺口见docs/alipay-integration-verification.md；当前本机仍为Mock。

内部订单权益与退款状态机及迁移007已通过SQLite/PostgreSQL回归；退款中和已退款订单不会因迟到支付重新授权。现已提供归属校验的付款查询、可信通知、退款申请和退款查询接口，远程联调尚未执行。见docs/alipay-integration-verification.md。

2026-11-24当前镜像已重新完成Compose构建、学习页流程、重启和备份恢复。遇到Docker Hub路径故障时，本轮使用与官方内容摘要相同的Google官方缓存，默认镜像来源未改；依据见docs/container-base-sources.json与docs/compose-verification.md。
