# 本地验收记录

记录始于2026-11-16，2026-11-17更新阶段5本地验收。环境为Windows、Node24.14.0、Python3.12.4。

## 实际执行

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| Next.js 生产构建 | 通过，TypeScript 检查通过 | npm run build 实际退出0 |
| 后端回归 | 55项通过，含9项OCR配置与真实识别专项 | backend-test-result.txt |
| 前端单测 | 9项通过，覆盖实际API与SSE处理函数 | frontend-test-result.txt |
| SQLite 初始迁移 | 新测试库与持久化开发库均启动成功 | backend/migrations/001_initial.sqlite.sql、测试及健康端点 |
| PostgreSQL实际回归 | Windows 17.12上55项通过，迁移1至6与重复迁移保留数据通过，临时服务已停止 | postgresql-result.json、postgresql-test-result.txt |
| 数据迁移 | 迁移1至6已应用，所有当前存档节点均有效，数量见报告 | migration-result.json |
| 一键启动 | API 健康通过，Next.js dev 就绪 | powershell -ExecutionPolicy Bypass -File scripts/start.ps1 |
| 浏览器全流程 | Edge与Chrome的桌面和手机主流程通过，page_errors为空 | e2e-result.json、e2e-chrome-result.json |
| 依赖通告查询 | npm生产依赖及当前Python虚拟环境查询均为0条已知漏洞 | npm-audit.json、python-audit.json |
| 本地请求采样 | 5MiB文件课程详情，8并发80请求P95约58.45ms | performance-result.json |
| 真实代理上传边界 | 10MiB文件完整保存/下载摘要一致，超限文件422、超限请求413 | request-limit-probe.json |
| 中文 PDF | 通过，浏览器生成的中英混排PDF可提取 | scripts/e2e.py、tests/samples/original-chinese.pdf |
| 轻量解析资源采样 | 实际运行完成 | parser-benchmark.json |
| WebGAL 在线嵌入 | iframe可装载和移除，跨域状态读取被拒绝 | webgal-probe.json |

其中9项基础回归包含三格式参数化解析测试、异常文档、可替换OCR与完整草稿、图校验、综合API与隔离、自有课程剧情生命周期、生成与删除并发测试。覆盖未登录访问、账号A/B隔离、私有文件读取、知识点修改、解析失败重试上限、存档版本冲突、正确/错误结局、评分、错题复习、退出后续玩、剧情重玩及版本切换和来源删除后的隐私清理。另3项聊天专项见陪学阶段记录。

浏览器验收通过正常网页入口执行注册、创建项目、三格式上传、等待解析、编辑确认、刷新后恢复、自有课程剧情生成、来源引用、两条剧情分支、错题复习、重玩、退出登录再登录续玩及手机导航。手机端另验证120字符课程名、5000字符知识点与600字符选项的布局。截图前等待目标场景提交和图像解码，避免把场景切换中的旧画面作为证据。

## 尚未证明的验收项

Docker Compose本机实际运行与备份恢复已于2026-11-18验收，范围见后文。Docling本地五类样本对照已完成，扫描中文缺口与资源成本见后文。WebGAL生产私有课程桥及原生存档同步和公开部署保持未验收。WebGAL本地同源Demo实验已补充，范围见后文。PostgreSQL原生Windows回归已执行，范围见后文。自有教材可使用确认知识点生成Demo剧情。云端提炼、剧情、聊天与ComfyUI适配器使用模拟传输验证，真实模型质量与费用、GPU及正式支付仍待实际验收。

## 2026-11-17 · 陪学阶段

新增三名角色与头像、按课程和角色隔离的流式对话、持久化消息、摘录记忆、关键词检索和来源。新增API测试覆盖他人账号与其他课程数据隔离、未确认知识排除、会话保存、重复请求、用户额度、80%告警、错误与超时、显式Demo降级，以及云协议的模拟传输。删除来源清理课程聊天也已纳入回归。

浏览器通过工作区现有序章及选择页进入 /study，验证小栞与遥的课程问答、刷新会话后读取消息、凛对无资料问题的未知提示、手机布局与实际拖动收起。浏览器测试另模拟模型服务错误并操作 Demo 重试。实际截图为 companion-desktop.png、companion-mobile.png，云余额错误验证使用模拟响应。

网页本地数据库采用SQLite，部署配置采用PostgreSQL。PDF运行依赖选择pypdf以配合当前商业化许可评估。两个决定的原因与影响见 architecture-decisions.md，整体阶段状态见 todo.md。

## 2026-11-17 · 角色工坊阶段

新增5项工坊专项，合计17项后端测试。覆盖服务端价格、订单幂等、通知验签、金额匹配、付款失败、重复通知、终态保护、私有图片、权利和真人同意确认、图片格式及EXIF清理、手机照片方向、并发权益占用、失败补偿、重试次数、超时与取消、未审核资产保护、角色归属、角色选择及删除。ComfyUI使用模拟HTTP传输验证输入白名单与输出读取。

桌面和390px手机均通过参考图上传、模拟审核、模拟付款失败及成功、权益发放、排队生成、审核交付、角色库选择、剧情人物使用和悬浮对话。手机悬浮控件缩为96px并保留拖动，生成列表和轮询避免读取图片二进制。实际截图为workshop-desktop.png、workshop-mobile.png、custom-character-desktop.png、custom-character-mobile.png。

项目已使用独立.venv安装运行和测试依赖，Pillow为13.0.0，pip check通过。17项测试存在1条Starlette/AnyIO测试接口弃用警告，功能测试均通过。真实GPU、远端图片清理、实际角色一致性、正式商户支付和退款验证仍未完成。

## 2026-11-17 · 阶段5本地验收

新增8项后端回归，合计25项。验证登录全局/IP预算与到期、带长度头和分块传输的请求大小、并发槽位、读入超时与释放、课程元数据查询排除二进制、解析期间删除来源和跨日图像任务重试额度。处理中资料可以立即删除，解析完成后重新检查记录并锁定课程，避免已删除资料重新发布或异常终止后台循环。

新增9项前端单测，直接调用页面使用的API与SSE函数。覆盖JSON/FormData头、取消信号、错误反馈、登录/注册/退出后的迟到私有数据、逐字节中文UTF-8、CRLF、多行事件、多事件网络分片、错误、截断、体积上限和消费者取消。源码采用ES模块声明，Node24原生测试运行器执行，未引入额外测试框架。

依赖初次审计在pip、pypdf、python-multipart和Starlette四组包中返回安全通告。已在独立虚拟环境升级pip26.3、pypdf7.1.0、python-multipart0.0.34，以及兼容的FastAPI0.163.1和Starlette1.10.0。测试客户端使用httpx2 2.16.2，业务云适配器保留httpx 0.28.1。修复后的完整回归通过且无弃用警告，pip check通过。pip-audit与npm audit当前均为0条已知漏洞，查询结果具有时间范围，目标容器镜像仍需再次核查。[FastAPI发布记录](https://fastapi.tiangolo.com/release-notes/)

课程详情查询延迟加载文件二进制，避免仅查看知识点就读取全部原文件。performance_check.py经正常API上传一个5,243,736字节原创PDF，课程响应为672字节。30次串行详情请求P95为8.56ms，8并发80次请求P95为58.45ms，10次网页HTML请求P95为1.91ms，所匹配API进程合计RSS采样峰值130.75MiB。测量为本机热请求，范围排除公网延迟、浏览器绘制与云/GPU服务。数据与环境见performance-result.json。

生产构建和TypeScript检查通过，Edge及Chrome各完成桌面与390px手机主流程。测试创建的合成账号保留在本地数据库。真实手机Safari、弱网、公开站点负载和生产备份恢复仍开放。

边界验证发现Next默认10MB代理缓冲会截断含表单开销的10MiB文件，已依据当前包内指南将experimental.proxyClientMaxBodySize设置为11mb，与API请求上限对齐。重新构建后经真实Next代理上传10,485,760字节有效PDF，私有下载SHA256一致，解析排队/执行期间删除返回200。文件多1字节返回422，上传请求超过11MiB及JSON超过64KiB均返回413。证据见request-limit-probe.json，脚本为request_limit_probe.py。

已生成demo-script.md、submission-draft.md及launch-checklist.md。PAYATHON报名与作品提交时间已从官方页面核对。智能体涌现奖官方入口已发现，本次正文抓取超时，具体当期条款保持待核实。公开部署、真实云AI、GPU与支付验证仍按PRD开放。[PAYATHON官方赛事](https://aipay.alipay.com/community/events/payathon-2026)

## 2026-11-17 · 云端课程适配

新增21项模拟传输与业务API测试，合计46项后端回归。覆盖长文本分批与短来源块合批、source_id绑定及逐次预算预留、空结果、伪造逐字引用、类型错误、畸形响应信封、题目来源与可玩结构、授权/额度错误、截断、1MiB响应上限、总体超时、调用前额度拒绝及配置缺失Demo。

业务API验证上传到云端草稿、编辑确认、生成结构化故事、答题前隐藏答案、服务端判分、私有来源、失败后显式Demo、部分批次失败不发布、同课程并发拒绝及生成期间修改资料后丢弃结果。用户/全局80%预算告警也已接入课程详情。测试上游为httpx.MockTransport，原创Demo图作为结构化响应样本，真实模型调用数为0。

迁移006保留旧资料与存档，并增加草稿模式/类型/引文、文件处理token及课程生成token。云请求等待期间释放数据库写锁，发布时重新核对版本与来源快照，旧处理者无法重新发布已删除或重启后的任务。配置与边界见cloud-learning.md。

cloud_browser_probe.py在独立测试库及本机临时同源服务中载入生产构建网页，后台模型传输仍为模拟。桌面与390px手机通过上传云端草稿、确认、结构化剧情、服务端判分、失败提示、显式Demo剧情及文件提炼降级，降级未增加模拟模型调用。临时API在脚本结束时关闭。结果见cloud-browser-result.json，截图cloud-fixture-desktop.png和cloud-fixture-mobile.png用于协议模拟验收，真实云模型调用数为0。

原有Demo/Mock桌面与手机全流程重新通过。刷新回归暴露会话恢复前侧栏可点击的问题，已为相关入口增加checked就绪条件，恢复期间避免误弹登录。浏览器脚本延迟auth/me回复500ms后验证进入课程与持久数据恢复。旧库迁移1至6完成，50份当前存档节点有效，生成中的聊天和图像任务为0，数量详见migration-result.json。

## 2026-11-17 · PostgreSQL实际验收

通过PostgreSQL官方Windows入口取得EDB免安装17.12归档，初始化项目独立集群，仅监听127.0.0.1，SCRAM-SHA-256认证，运行全套46项后端测试。首轮发现消息纳秒时间戳被ORM转换为INTEGER，修正ChatMessage.created_at为BigInteger后，两种数据库均46项通过。

最终PostgreSQL回归46项通过，迁移1至6应用成功，共22张public表。重复运行迁移后28个用户、18个课程、3份存档和8条聊天消息的行数保持一致。测试数据均为自动生成。临时集群结束时停止，密码文件移除。运行证据、下载摘要与复跑方法见postgresql-verification.md、postgresql-result.json及postgresql-test-result.txt。Docker Compose与Linux镜像、真实目标负载和发布环境恢复测试继续开放。

## 2026-11-17 · 可选本地OCR

新增9项OCR测试，SQLite及PostgreSQL均55项通过。tesserocr2.13.0、pypdfium2 5.15.2和官方中文/英文模型实际加载，原生引擎为Tesseract5.5.4。原创扫描PDF没有文本层，经解析worker识别出中英内容并标记OCR来源，总耗时约1.6秒，输出见ocr-result.json。这是清晰单页样本实测，复杂内容继续待评估。

隔离浏览器流程已真实上传扫描PDF，显示OCR出处和可编辑知识点，桌面及390px手机无横向溢出，截图ocr-desktop.png、ocr-mobile.png。识别为本地真实执行，课程模型上游使用MockTransport，cloud-browser-result.json记录real_local_ocr=true、real_model_calls=0。临时API和PostgreSQL均在结束时关闭。

默认OCR未启用，配置与资源限制见ocr.md。Python依赖库存更新为49个包，pip check通过，新增依赖后pip-audit查询为0条已知漏洞。Linux容器、Docling、复杂布局与生产资源约束继续开放。

## 2026-11-17 · WebGAL同源运行与角色表情

固定官方4.6.7发布版通过独立Next生产构建与React客户端组件装卸，动态.txt脚本来自真实课程图。显式POST桥通过两分支、两个评分结局、预取不推进存档、409时保持原画面，以及quiz/version=2节点卸载重进。两条路线共用同一原创课程，截图和资源、JS堆采样见webgal-verification.md及webgal-same-origin-result.json。临时Next、HTTP测试代理和API上下文在结束时关闭。

新增小栞开心和遥温柔两张内置image_gen表情变体，经角色公开资料的expressions字段接入剧情。WebGAL检查两种图片资源已加载，现有学习页验证答对后使用shiori-happy.png。前端9项单测及主应用生产构建通过，后端按README规定的pytest tests -q执行，55项通过。一次仓库根目录pytest调用收集到scripts中的独立浏览器脚本，因其命令行参数与独立服务前提报错，该调用未作为后端回归结果。

当前恢复的是应用节点级进度，原生WebGAL存档、生产私有课程脚本桥、长期内存释放、GPU/原生总内存与复杂演出仍待验证。资源数据采用本机固定窗口与单次流程，适用范围写入报告。

## 2026-11-18 · Linux容器与恢复

Docker Engine、Compose和Buildx已安装到已有Ubuntu WSL。隔离Compose项目实际构建API/Web镜像，三个服务健康，容器内PostgreSQL通过网页API执行登录、剧情推进、DOCX解析及私有下载校验。停止并重新启动后会话、存档与文件保持一致。桌面和390px手机Edge完整Demo/Mock浏览器流程通过，记录见e2e-result.json。

pg_dump备份实际恢复到新的数据库，四张关键表行数3/5/5/4保持一致，恢复文件SHA256和存档节点/版本匹配。compose-result.json记录passed、containers_stopped=true及wsl_keepalive_stopped=true。测试卷与构建镜像保留于本地Docker，运行环境变化与网络恢复步骤见compose-verification.md。

## 2026-11-18 · 弱网和断线恢复

network_probe.py在独立测试库中载入当前生产构建，以CDP设置300ms延迟、下载200KiB/s和上传64KiB/s。桌面与390px手机视口均通过三格式上传、知识点编辑确认、剧情与答题。断网上传未留下文件，恢复重选同一文件成功。答题前断网保持原存档，提交已被服务端接受但响应丢失时只推进一个版本，刷新重新进入恢复review/version=3，错题1条。

SSE收到片段后断网，页面显示错误，刷新会话读到服务端已完成的回复。第一条请求只保存2条消息，用户显式发送新问题后共4条消息，新回复complete且含课程知识。报告network-result.json记录两个视口page_errors为空、临时API和Next关闭。范围与复跑方法见network-verification.md，真机移动网络、真实云模型流与目标环境负载继续开放。

## 2026-11-23 · Docling CPU对照

固定Docling 2.150.1、CPU版PyTorch、布局和TableFormer模型，五类样本共10个独立解析进程正常完成，每个进程转换两次。原创3×4表格的跨行单元格还原成功，普通三格式与双栏PDF预期文字均命中。当前Docling扫描OCR遗漏3项中文，轻量Tesseract路径命中全部4项扫描预期文字。具体耗时、CPU峰值和RSS见docling-benchmark.json及docling-verification.md。环境依赖冻结于docling-environment.txt。

研究使用独立data/docling-env与忽略的本地模型目录。当前生产解析继续采用轻量实现及可选Tesseract，Docling保留复杂版面worker候选，目标部署容量和更广扫描质量仍待验证。

## 2026-11-23 · 赛事与真实服务前提

补查PAYATHON官方发布细则，核对北京时间报名/提交截止、正式部署、AI付产品接入及报名和支付同账号条件。涌现奖官网发布包给出首轮12月6日及评审时间，另有12月31日弹窗文案，完整规则仍未取得，保留差异。来源快照摘要与材料准备状态见contest-verification.md及contest-sources.json。

配置审查只记录存在性，项目根目录无.env，环境中未发现模型、ComfyUI及支付宝所需配置。真实服务、正式交易和公开发布继续待资源与相应授权。

## 2026-11-23 · 授权后的真实模型实验

用户授予全部项目授权后，已连接Cloudflare并部署私有模型网关。Qwen原创教材提炼、逐字引用与账号隔离通过，真实剧情因格式与结构不符被拒绝。GLM短JSON调用成功，应用长请求与后续直连超时。最新cloud-live-result.json保留failed，完整网站、真实剧情和三角色聊天尚未通过云端验收。本机默认保持Demo，配置和证据见cloud-live-verification.md。网关6项单测、后端55项回归通过。

## 2026-11-23 · WebKit兼容性

独立WebKit 26.0在1440×1000及390×844视口完成Demo/Mock学习、聊天和角色工坊流程，页面无未捕获异常，API与Next已关闭。首次因测试教材打印API仅支持Chromium而失败，拆分打印实例后完整重跑通过。范围、截图及复跑见webkit-verification.md；iOS Safari和Android真机仍未验收。

## 2026-11-23 · 支付宝离线协议

官方SDK 3.7.1411、内存临时RSA密钥及合成订单完成15项协议检查，无网关调用或真实交易。新增独立通知校验模块拒绝SHA-1冒充RSA2、重复参数、篡改及不匹配的应用、卖家、订单与金额。依赖位于隔离环境，主应用继续Mock。具体范围和后续接入缺口见alipay-contract-verification.md。

## 2026-11-23 · 支付宝查询与退款传输层

新增固定网关、UTC+8请求时间、RSA2原始响应验签、128KiB响应上限和20秒总超时的服务端组件，提供页面支付URL、交易查询、退款与退款查询。10项MockTransport支付测试与完整后端共65项回归通过（37.33秒），两个环境pip check通过，官方SDK安装进程正常退出。未启用真实PaymentProvider、未调用支付宝网关，业务状态机和远程验收仍开放。结果见alipay-gateway-result.json与alipay-gateway-verification.md。

## 2026-11-23 · 订单权益与退款事务

内部支付凭据状态机、退款冻结及迁移007完成；SQLite与PostgreSQL均74项回归通过。并发复用交易号被唯一索引拒绝，迟到支付不能恢复退款中或已退款权益。PostgreSQL重复迁移检查扩展到订单、支付事件、权益和退款。HTTP支付宝适配与真实交易仍未开启，范围见payment-state-verification.md。

## 2026-11-23 · 支付宝业务适配

新增支付宝业务适配类与严格配置入口，将通知/查询及退款查询绑定到订单快照，15项本地假网关业务测试通过。SQLite完整89项通过（38.41秒），PostgreSQL完整89项通过（43.42秒），迁移1至7及八类关键记录重复迁移保持一致，临时数据库已关闭。运行中的付款方式仍为Mock，真实路由与前端尚未接入，详见alipay-provider-verification.md。

## 2026-11-23 · 支付宝应用路由与界面

Provider选择、主动付款查询、可信通知、退款申请/查询及前端模式展示已接入。SQLite/PostgreSQL各99项通过，前端11项和生产构建通过，WebKit原25项及Edge桌面/手机本地银行替身流程通过，临时服务均关闭。真实网关调用与交易为零。Docker新镜像构建因Docker Hub EOF在有限重试后失败，只读密钥挂载配置语法通过；完整容器与远程沙箱继续待验。见alipay-integration-verification.md。

## 2026-11-24 · 当前容器构建与支付密钥验证

Docker Hub直连清单请求在部分客户端出现TLS EOF；WSL curl匿名认证及HTTP/1.1、HTTP/2清单请求均返回200。读取Docker Hub官方标签元数据，并对Google官方mirror.gcr.io缓存清单的实际字节计算SHA256，Node 24-alpine和Python 3.12-slim两个摘要均完全匹配，来源见container-base-sources.json。Dockerfile新增可覆盖的基础镜像ARG，默认来源不变；仅本轮Compose测试显式使用核对后的缓存摘要，不更改宿主的全局注册表配置。

项目galstudycheck6b94f1cbb076一次构建完成，api/db/web健康。学习页入口的桌面与390px手机25项Demo/Mock流程通过，重启保持会话/存档/私有文件，PostgreSQL备份恢复行数3/5/5/4及文件和存档内容匹配。compose-result.json记录passed，容器与临时WSL保活已关闭，构建镜像和合成测试卷保留本机。新运行未覆盖序章、篇章选择或真实移动设备。

同一实际API镜像另在禁用网络的容器中以非root用户读取只读合成密钥，成功选择alipay_sandbox Provider并签名页面支付URL，rsa版本4.9.1。结果见alipay-container-result.json。没有调用支付网关或发起交易。
