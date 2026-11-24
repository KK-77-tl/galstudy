# GalStudy 上线与验收清单

2026-11-17，本地阶段5检查。整体发布及真实服务验收仍开放。

## 可重复执行的本地验收

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip==26.3
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests -q
Push-Location frontend
npm.cmd ci
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
npm.cmd audit --omit=dev
Pop-Location
```

启动API与网页后执行浏览器流程。默认Edge，设置 E2E_BROWSER=chrome 后使用Chrome。E2E_BASE_URL可修改网页地址。脚本产生合成账号，测试数据保留在当前本地库。性能脚本同样创建合成账号与一个5MiB PDF。

```powershell
.\.venv\Scripts\python.exe scripts/e2e.py
.\.venv\Scripts\python.exe scripts/cloud_browser_probe.py
.\.venv\Scripts\python.exe scripts/performance_check.py
.\.venv\Scripts\python.exe scripts/request_limit_probe.py
.\.venv\Scripts\python.exe scripts/check_migrations.py
.\.venv\Scripts\python.exe scripts/dependency_inventory.py
```

## 本地测试清单

- [x] 三格式原创样本、损坏文档、扫描件OCR缺失提示、来源定位与解析重试。
- [x] 未登录与A/B账号隔离、私有文件、图像和角色归属。
- [x] 知识点编辑确认、剧情图校验、分支、分数、错题、重玩与旧存档兼容。
- [x] 聊天依据、角色切换、消息保存、清空、超时与显式Demo降级。
- [x] Mock付款失败/成功、金额核对、通知幂等、并发权益占用与生成失败补偿。
- [x] 请求体在表单解析前限流量，包含无Content-Length的分块请求。
- [x] 经Next真实代理验证10MiB文件内容完整，超限文件与请求返回明确错误。
- [x] 登录尝试限额、请求并发槽位与退出后迟到响应防护。
- [x] 流式聊天的UTF-8分片、CRLF、多事件、异常/截断与取消。
- [x] 跨日旧任务重试计入当天图像提交限额。
- [x] 桌面和390px手机浏览器主流程、长文本、悬浮拖动与横向溢出。
- [x] 本机CDP固定弱网配置下的学习流程与上传/答题/SSE断线恢复，范围见network-verification.md。
- [ ] iOS Safari、Android真机、辅助技术与实际移动网络验收。
- [ ] 独立部署环境的负载、数据恢复和故障演练。

## 发布配置与运维检查

清单同时记录PRD验收条件和公开运营时的运维评估事项。账号恢复、多实例和对象存储的具体取舍随实际发布范围确定。

- [ ] 选定主机、域名、数据区域与部署方式，取得本次实际部署授权。
- [x] 本地原生PostgreSQL 17.12、迁移1至6、完整后端回归和重复迁移保留数据验证。
- [x] 在本机Ubuntu WSL实际启动Docker Compose，验证镜像、数据库持久卷、网络、备份与恢复，证据见compose-verification.md。
- [ ] 在实际发布环境复核容器配置、数据恢复和目标负载。
- [ ] HTTPS证书、正确APP_ORIGIN、Secure Cookie、反向代理上传限制与SSE超时。
- [ ] 受信代理地址配置，边缘登录限流与多进程共享限流方案。当前内存限流按单进程计算，进程重启会清零。
- [ ] 账号验证、密码找回、账号删除与用户支持流程。
- [ ] 全球/全站存储预算、磁盘容量告警、备份保留期和私有对象存储。
- [ ] 隐私说明、服务与退款条款、内容审核和适用运营手续，结合实际主体与部署地区复核。
- [ ] 目标镜像依赖及原生组件许可证、版权声明和素材许可完整审查。dependency-inventory.json提供包级元数据清单。
- [ ] 模型密钥、GPU及商户配置通过服务端注入，日志抽查无教材全文、照片、令牌与私钥。
- [ ] 对象存储链接时效与权限、外部GPU图片保留及清理、参考图到期删除经过实际验证。
- [ ] 上传解析任务的进程内存/CPU隔离、持久队列租约与跨实例恢复。

## 真实AI、GPU和支付验收

- [x] 云模型提炼和剧情生成适配、结构化输出与失败处理，经模拟HTTP传输和业务API验证。
- [ ] 真实云模型提炼与剧情生成的教学质量、时延、引用及账单验收。
- [ ] 云聊天真实问答集、引用正确性和不确定性评估。
- [x] 本地Tesseract扫描PDF OCR、原创中英样本、来源与私有上传验收。
- [x] 原创双栏跨行表格、中英扫描件及三格式的Docling/轻量解析实测，质量缺口与CPU/RSS见docling-verification.md。
- [ ] 公式结构、跨页表格、手写、旋转和低清扫描的更广质量与容量评估。
- [ ] 授权ComfyUI工作流、模型/LoRA许可、实际角色一致性及完整资产包。
- [ ] GPU提交超时后的查重、运行中取消、远端资源清理和实际计费上限。
- [ ] 官方支付宝准入与沙箱联调、正式通知验签和主动查询、金额与应用核对。
- [ ] 经授权的真实支付、交付、失败补偿和原路退款测试。
- [ ] 公开可用作品、视频、官方赛事规则和报名主体信息确认。

## 当前已知限制

本地默认知识点为原文摘录，剧情为摘录识别题模板，未验证全学科的教学质量。已提供可配置的云端知识提炼和结构化剧情适配器，真实模型输出待评估。检索采用有限候选关键词评分，聊天记忆采用截取摘要。云API和GPU没有配置可验收的真实环境，角色一致性尚无实测。Mock角色包复用一张预设图，清单显示其余槽位的占位状态。

本地资料与图像存储于数据库，容量上限覆盖单文件和账号文件数量，全站总存储需要独立预算。解析子进程具有45秒超时，操作系统级内存配额尚未设置。服务按单API worker设计，当前内存限流、后台轮询与恢复流程依赖该运行方式。

当前限额由实现阶段设定，可在.env配置。登录每IP每分钟30次、全局120次，认证并发2个、上传并发2个、其他写请求并发16个，上传读入总时长30秒。JSON请求体64KiB，登录与Mock通知4KiB，课程上传请求11MiB，图片上传请求6MiB，业务文件内容仍分别限制10MiB和5MiB。

图像新任务默认每用户每天5个、全局20个。每次提交服务商的调用另计为每天15次/用户、60次/全局，失败和跨日旧任务重试仍计数，达到限额后恢复权益。两类每日计数均按UTC+8划分，新迁移前的历史提交不回填。单任务仍最多3次提交。当前计数约束调用次数，实际费用需与供应商账单核对。


2026-11-23补充：Windows WebKit 26.0桌面与手机视口主流程通过，范围和证据见webkit-verification.md。该结果不替代iOS Safari、Android真机和真实移动网络项目。
