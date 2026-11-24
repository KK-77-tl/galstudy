# GalStudy 技术决策

记录日期为 2026-11-16。需求基线保存在 requirements-v1.1.txt。

## ADR 001 · 采用应用自有 JSON 剧情状态机

采用 FastAPI/Pydantic 校验图结构与目标节点，Next.js/Zod 校验返回的节点。所有选择由服务端推进，服务端记录答题、分数、存档版本。使用带版本条件的 UPDATE，冲突返回 409。前端只提交 choice 和 version。

WebGAL 4.6.7的模块单例与内部store、舞台和画布关联，发布构建未向window暴露该实例。已在独立Next生产宿主完成同源iframe装卸、服务端动态脚本、显式选择事件桥、409回退及节点续玩。预取分支期间存档保持不变，浏览器资源与JS堆实测见webgal-verification.md。生产私有脚本发布、原生存档同步和长期资源释放保持待验证。[官方入口](https://github.com/OpenWebGAL/WebGAL/blob/main/packages/webgal/src/Core/WebGAL.ts) [官方存档实现](https://github.com/OpenWebGAL/WebGAL/blob/main/packages/webgal/src/Core/controller/storage/saveGame.ts)

| 维度 | 直接集成 WebGAL | 自有 JSON 状态机 |
| --- | --- | --- |
| 演出能力 | 支持成熟演出与脚本生态 | 当前完成背景、立绘、对话、选择和结局 |
| 动态课程故事 | 需图到脚本转换与业务事件桥 | 图节点直接接应用模型 |
| 存档一致性 | 节点重建续玩已实测，原生引擎存档仍需协调 | 一个服务端事务更新 |
| 集成成本 | 高于当前 PoC，工程推断，未测工时 | PoC 已运行，具备回归测试 |
| 长期维护 | 跟随上游并维护适配层 | 应用自行维护状态机与演出组件 |
| 加载与JS堆 | 本轮累计正文56,842,865字节，题目JS堆10.42MiB | 同课程累计正文5,455,685字节，题目JS堆4.58MiB，范围见webgal-verification.md |
| 许可证 | MPL-2.0，涉及分发的相关文件义务需审查 | 独立编写，依赖登记见 licenses.md |
| 测试性 | 需同时驱动引擎和业务 | API 可遍历分支，浏览器可复现 |

当前选定自有状态机作为阶段2路线。未来需要复杂镜头与动画时再评估 WebGAL 演出层。当前 PoC 为原创固定课程，自有资料的剧情生成归入阶段2。

## ADR 002 · 轻量解析与可选 OCR

普通文本 PDF 使用 pypdf。DOCX 使用 python-docx，保留文档顺序、内容块编号、段落样式与表格文字。Word 页码依赖排版环境，当前返回内容块位置。PPTX 使用 python-pptx，保留幻灯片编号与文字、表格行。PDF 保留页码与提取文本，复杂表格结构尚未恢复。

PyMuPDF 的 AGPL/商业许可增加商业化许可评估事项，本次改用 BSD-3-Clause 的 pypdf。Docling已在独立CPU环境完成普通文件、双栏表格和扫描件实测，PDF路径内存较高且扫描件中文存在遗漏，保留为独立复杂版面worker候选。当前扫描件可选Tesseract路径已通过原始中英扫描样本，配置缺失或识别失败时返回明确错误。[PyMuPDF 许可证](https://github.com/pymupdf/PyMuPDF/blob/main/COPYING) [pypdf 许可证](https://github.com/py-pdf/pypdf/blob/main/LICENSE)

## ADR 003 · 本地 SQLite 与部署 PostgreSQL

开发默认SQLite，数据持久化到data/galstudy.db。PostgreSQL 17.12原生Windows回归及迁移1至6已通过。2026-11-18在已有Ubuntu WSL完成Docker Compose构建、PostgreSQL内部网络、持久卷、网页全流程、停止重启和备份恢复验收，范围见compose-verification.md。backend/migrations 中固化了两个方言的初始 SQL，backend.db 按编号依次应用并登记 schema_migrations，后续变更增加新的编号文件。

当前私有文件以数据库二进制保存，文件读取经过课程归属校验。对象存储适配、带时限下载链接归入后续扩展，当前限制单文件10MB、单账号20份、单文件100页或幻灯片、解压50MB、提取30万字。

## 目录与阶段0文件

```text
frontend/app/           首页、账号、课程、校对、剧场、错题界面
frontend/public/assets 原创演示美术
backend/db.py          数据模型与初始迁移
backend/main.py        认证、课程、上传、任务、知识点、剧情 API
backend/parsers.py     三种格式的轻量解析
backend/story.py       原创剧情与图校验
scripts/               启动、样本、调研、基准与浏览器验收
tests/                 API 与解析回归测试
docs/                  需求、研究、决策、许可证与实际截图
compose.yaml           PostgreSQL、API、Web 本地容器编排
.env.example           配置示例
```

## 数据关系

users 一对多 courses、sessions。courses 一对多 source_files、knowledge_points、saves、attempts。source_files 一对多 source_chunks。knowledge_points 可引用 source_chunks，也允许人工补充。saves 对 user/course 组合唯一。各私有 API 首先核实 Course.user_id，再读取课程下的数据。attempts 的用户条件由当前会话决定。

stories 表已持久化版本化剧情。节点、选择、题目、答案与来源映射作为经过 Pydantic 验证的完整 JSON 图存入同一版本，避免分批写入时产生半张图。角色、人设、聊天、订单、支付事件、权益和图像任务仍待后续阶段增加。

## API 契约

完整 OpenAPI 在本机 API 的 /docs。所有私有端点使用 HttpOnly、SameSite=Lax 会话 Cookie。写入请求校验 Origin。密码使用 Argon2，Cookie 内只有随机令牌，数据库保存令牌摘要。登录错误统一响应。当前尚未实现邮箱验证、找回密码与登录频率限制，公开部署前需要补齐。

| 方法 | 路径 | 输入与输出 |
| --- | --- | --- |
| GET | /api/health | 数据库状态与 Demo/OCR 状态 |
| POST | /api/auth/register 或 login | email/password，返回账号并设置 Cookie |
| GET/POST | /api/auth/me 或 logout | 会话信息或撤销当前会话 |
| GET/POST | /api/courses | 列表或创建 title/demo |
| GET | /api/courses/{id} | 文件状态、知识点、原文与出处 |
| POST | /api/courses/{id}/files | multipart file，返回202及队列任务ID |
| GET/DELETE | /api/courses/{id}/files/{file} | 私有下载或删除原文及关联提取数据 |
| POST | /api/courses/{id}/points | 手工增加 text/confirmed |
| PUT/DELETE | /api/courses/{id}/points/{point} | 修改确认或删除 |
| GET/POST | /api/courses/{id}/play | 读存档或按 choice/version 推进 |
| GET | /api/wrong-answers | 当前账号答错记录与解析 |
| POST | /api/courses/{id}/story | expected_revision，生成独立的 Demo 剧情版本 |
| POST | /api/courses/{id}/play/restart | version，重玩最新剧情，递增存档版本 |
| GET/POST | /api/wrong-answers/{attempt}/review | 获取复习选项或提交 choice 并标记复习结果 |

当前任务由 API 进程内的单 worker 读取数据库队列。进程重启恢复 processing 任务为 queued。领取任务使用状态条件更新，提取结果与任务完成在同一事务提交。解析运行在子进程，45秒超时终止，失败任务可重试且最多尝试3次。上线前需补充分布式 worker 租约与操作系统级内存限额。

## ADR 004 · 不可变剧情版本与原文删除

每次生成读取1至12条已确认知识点，DemoProvider 生成两章校园故事、不同起始路径和摘录识别题。题目与知识原文保留引用，人工确认的编辑文本与原文件摘录分别记录。前端显示模板化 Demo 状态。云模型真实生成后续接入同一 Provider。

生成结果保存为新的 stories 记录，版本号在课程内唯一。存档通过 story_id 绑定原版本，继续学习沿用原图。显式重玩切换到最新版并清零本次分数，错题历史继续保存。版本号条件更新防止重复操作或旧标签页覆盖新进度。

当前故事图要求有限无环、所有节点可达、每个分支能通往结局、题目有有效正确答案与解析。API 返回题目时隐藏正确答案和来源摘录，评分后返回解析与引用。评分和答题记录在同一事务提交。

文件删除会清理引用该文件的所有剧情版本及关联存档、答题记录。课程级写入锁将生成与原文删除、知识点修改串行化，SQLite 使用 BEGIN IMMEDIATE，PostgreSQL 使用行锁。SQLite 迁移也显式开启事务，使新增迁移的 DDL 与版本登记共同提交。

## ADR 005 · 课程陪学与有界上下文

chat_sessions 对 user/course/character 组合唯一，chat_messages 按会话保存用户消息、回复状态、实际模式与引用。request_id 在会话和角色类型内唯一，重复提交返回409。课程写入锁与 processing 状态阻止同一会话并发生成。重启时将未完成回复标记失败，清空会话会删除消息和记忆。

检索在数据库中强制按课程及已确认状态过滤，取至多24个英文词或中文二元词组，限制40个候选并返回前三条。每条证据最多1500字符，附带原文件或人工补充出处。当前为词面检索，语义召回和更复杂排序仍待评估。上下文只包含同一会话最近8条完整消息与最多1200字符的摘录记忆。

流式回复采用SSE的meta/delta/done/error事件。生成前以事务预留用户与全局每日请求、token额度，失败后保留预留量，避免自动重试扩大调用成本。模型输出上限512token，应用回复上限6000字符，整体30秒超时。云端失败返回可读错误，由用户选择Demo重试。没有课程证据时使用Demo未知提示。真实云服务尚未测试。

文件删除同步清空本课程所有会话，以清理历史回复和摘要中的来源派生内容。正在输出但已被删除的会话不会重新写入数据库。聊天组件放在当前 /study 学习页，现有序章与选择页继续承担网站入口。

| 方法 | 路径 | 契约 |
| --- | --- | --- |
| GET | /api/characters | 三名预设角色的显示资料 |
| POST | /api/courses/{id}/chat/sessions | character_id，返回该账号课程角色会话 |
| GET/DELETE | /api/chat/sessions/{id} | 读取消息或清空会话及记忆 |
| POST | /api/chat/sessions/{id}/messages | request_id/message/use_demo，返回SSE流 |

## ADR 006 · 订单、权益和图像任务解耦

products配置服务端价格及角色包数量，orders保留购买时快照。payment_events以通知编号及原始内容摘要实现幂等，entitlements对order_id唯一。付款成功后，任务通过用户级事务锁占用权益，reservation_job_id标识当前占用者。失败、取消或超时只恢复与当前任务匹配的权益，交付后转为consumed。characters对entitlement_id唯一，防止重复交付。

reference_images保存私有PNG、声明和审核状态，image_jobs保存人物属性、服务模式、状态、尝试次数与远端任务号。image_assets以job_id/slot唯一标记输出顺序，characters保存主立绘、表情与姿态的资产清单。Mock共用一张演示图，清单明确记录placeholder。真实模式须具备完整数量的输出并经后台审核。

图像服务和支付服务通过独立适配器访问。Mock支付使用本地HMAC验签模拟，共用正式业务事务逻辑。ComfyUI适配器读取服务端工作流配置，并限制可变节点及输入字段。详细配置、接口、隐私策略和未验证项见workshop.md。

用户选定角色保存在users.selected_character_id。预设阵容和用户角色均转换为相同显示及聊天档案，角色读取和资产访问执行用户归属校验。删除角色清理资产及对应角色聊天，保留已使用的订单权益状态。

## ADR 007 · 请求与生成提交预算

ASGI入口在FastAPI解析表单前检查Content-Length并对实际接收字节计数，兼容分块请求。单次读取限时30秒，认证、上传与其他写请求分别占用有界槽位。登录/注册采用按来源地址与全局的滑动一分钟窗口，在昂贵密码哈希前执行，内存状态适用单进程，重启清空。公开多实例部署时需评估边缘或共享限流。

Next.js的experimental.proxyClientMaxBodySize设为11mb，容纳10MiB文件与表单开销，后端执行实际请求上限。该配置经过真实代理的完整文件摘要和超限返回码验证，升级Next时需保留此边界回归。

前端共享API记录账号会话版本，登录、注册和退出开始时推进版本，旧请求解析后比较版本并拒绝迟到结果。SSE处理函数独立供陪学与单测共用，逐段解码UTF-8，校验事件终态与大小，取消时释放流读取器。

迁移005新增image_submission_usage，用户和全局的UTC+8日期桶记录每次服务商提交。用户锁与PostgreSQL全局事务锁串行预留，预留和submitting状态同事务提交。提交失败与不确定结果保留计数，权益按任务状态恢复。此计数覆盖前几日创建任务的重试，原有新建任务额度继续生效。历史提交不回填。

## ADR 008 · 结构化课程生成与并发发布

LLM_MODE独立控制知识提炼与故事生成，LLM_CHAT_MODE控制聊天，三者共用服务端配置和LLMUsage额度。云端使用JSON Object输出并再次执行应用层结构与来源校验，知识草稿quote必须为输入的逐字子串，故事point_ids仅可引用本次确认知识快照。完整schema、预算、失败语义和真实服务待验收项见cloud-learning.md。

知识草稿在全部批次完成后连同原文块原子发布，文件processing_token防止旧任务覆盖重启或删除后的状态。迁移006保留旧Demo语义，新增来源草稿的类型、模式与引文。

云端剧情请求先以course.story_token占用生成权，释放数据库写锁后调用模型，再重新锁定并比较token、标题、确认知识快照和版本。发生资料变化即丢弃结果，失败恢复生成入口，旧故事与存档继续保留。Demo路径沿用原有同步事务，以保留现有调用行为。

## ADR 009 · PostgreSQL参数类型与真实驱动回归

ChatMessage.created_at使用纳秒整数排序，SQL迁移已采用BIGINT。psycopg会依据SQLAlchemy映射生成参数转换，因此ORM也明确声明BigInteger，避免Python整数被转换为PostgreSQL INTEGER而溢出。SQLite宽松整数存储未暴露该问题，现将同套后端测试运行于两种数据库。

Windows开发验证使用项目内免安装17.12二进制与临时集群，随机SCRAM密码、回环监听和独立数据库，结束时停止。测试模式显式采用Demo/Mock外部提供者。Docker Compose及目标部署环境继续单独验收，复跑脚本与证据见postgresql-verification.md。
