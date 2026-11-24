# Docker Compose实际验收

2026-11-18，使用已有Ubuntu 26.04 WSL安装Docker Engine 29.1.3、Compose 2.40.3及Buildx 0.30.1，执行本地隔离验收。结果为passed，证据为compose-result.json和对应test-results/compose-*内的compose.log。测试期间使用现有Windows代理，真实模型调用和付款均为0。

## 实际覆盖

- 以项目compose.yaml为基础构建API和Web镜像，postgres:17-alpine、python:3.12-slim、node:24-alpine来自官方镜像仓库。
- 独立项目名、随机本机网页端口、随机测试密码和Mock签名密钥。覆盖文件仅调整测试env_file、端口及构建代理参数。
- db/api/web达到健康状态，经网页代理访问API，数据库类型为postgresql，学习和聊天模式均为demo。
- 注册合成账号、创建原创课程、选择concept分支、上传原创DOCX、容器worker解析到ready、私有下载SHA256与原文件一致。
- 停止并重新启动三个容器，原会话继续有效，存档节点/版本及私有文件SHA256保持一致。
- Edge 157.0.4341.60在1440×1000桌面和390×844手机视口完成现有e2e.py全流程。涵盖三种上传、知识点编辑确认、剧情、评分、来源、错题复习、退出重登续玩、流式聊天、悬浮角色及Mock工坊交付。结果另存e2e-result.json，page_errors为空。
- pg_dump自定义格式备份恢复到另一个新建数据库，users/courses/saves/source_files行数分别为3/5/5/4，源库与恢复库一致。恢复后的原文件SHA256以及concept节点和版本也一致。
- 最终compose down成功，测试容器停止，WSL保持会话退出。生成的测试数据卷和构建镜像保留在本地Docker中，项目名记录于报告。

本轮覆盖本机Linux容器与恢复流程。公网HTTPS、真实部署负载、真机Safari/Android和真实云/GPU/支付仍待验收。容器OCR模式为disabled，原生Windows OCR的独立验收见ocr.md。

## 复跑

先在已有Ubuntu WSL中准备Docker Engine、Compose和Buildx，再从项目根目录执行。

```powershell
.\.venv\Scripts\python.exe scripts\compose_check.py
```

若WSL直连Docker Hub失败，可通过COMPOSE_BUILD_PROXY传入现有且能从WSL访问的HTTP代理地址。地址取决于本机网关与代理监听配置，应使用本机实际值。

```powershell
$env:COMPOSE_BUILD_PROXY='http://WSL可访问的代理主机:代理端口'
.\.venv\Scripts\python.exe scripts\compose_check.py
```

代理模式会在空闲Docker守护进程中设置本轮专用的/run/systemd/system/docker.service.d临时配置并重启服务，完成时移除该配置。脚本保持一个读stdin的WSL进程，避免Windows浏览器测试期间WSL空闲退出清除运行环境。镜像仓库TLS超时、连接重置和I/O超时最多重试三次。凭证和覆盖配置位于已忽略的test-results目录，浏览器测试使用合成账号。

首次尝试经历WSL直连连接重置、临时代理随WSL退出丢失、Compose start不支持--wait及仓库瞬时TLS超时。最终脚本通过保持会话、临时代理、兼容的up --no-build --wait和有界重试完成验收。当前报告保留最终成功结果，前序失败日志保存在各自测试目录。

2026-11-23更新：包含支付依赖和新网页的重建被Docker Hub node:24-alpine元数据请求EOF阻断，有限重试失败。当前compose-result.json为failed且测试资源已停止；本文件此前通过结果属于2026-11-18快照。新镜像待重新验证，见alipay-integration-verification.md。

## 2026-11-24 · 当前容器构建与支付密钥验证

Docker Hub直连清单请求在部分客户端出现TLS EOF；WSL curl匿名认证及HTTP/1.1、HTTP/2清单请求均返回200。读取Docker Hub官方标签元数据，并对Google官方mirror.gcr.io缓存清单的实际字节计算SHA256，Node 24-alpine和Python 3.12-slim两个摘要均完全匹配，来源见container-base-sources.json。Dockerfile新增可覆盖的基础镜像ARG，默认来源不变；仅本轮Compose测试显式使用核对后的缓存摘要，不更改宿主的全局注册表配置。

项目galstudycheck6b94f1cbb076一次构建完成，api/db/web健康。学习页入口的桌面与390px手机25项Demo/Mock流程通过，重启保持会话/存档/私有文件，PostgreSQL备份恢复行数3/5/5/4及文件和存档内容匹配。compose-result.json记录passed，容器与临时WSL保活已关闭，构建镜像和合成测试卷保留本机。新运行未覆盖序章、篇章选择或真实移动设备。

同一实际API镜像另在禁用网络的容器中以非root用户读取只读合成密钥，成功选择alipay_sandbox Provider并签名页面支付URL，rsa版本4.9.1。结果见alipay-container-result.json。没有调用支付网关或发起交易。
