# 开源项目核查与技术验证

核查日期为 2026-11-16。版本、分支、Star 和许可证来自 GitHub 官方 API 的一次快照，原始结果保存在 research-metadata.json。发布前应再次检查具体依赖版本与许可文本。ts-fsrs 的仓库最新 Release 属于 binding 子包，不能将它当作 ts-fsrs 的 npm 版本。

下文的功能状态和资源实验为初始调研快照。后续学习、陪学、工坊与云适配的实现及回归见verification.md。2026-11-17已补充原生Windows PostgreSQL 17.12实际迁移与完整后端回归，证据见postgresql-verification.md，Docker Compose环境继续待验收。

| 项目 | 分支 / 最新 Release | Star 快照 | 许可证 | 当前决定 |
| --- | --- | --- | --- | --- |
| [WebGAL](https://github.com/OpenWebGAL/WebGAL) | main / 4.6.7 | 4,037 | MPL-2.0 | 借鉴演出形式，当前采用自有状态机 |
| [Docling](https://github.com/docling-project/docling) | main / v2.150.1 | 70,642 | MIT | 独立CPU对照已完成，保留复杂版面worker候选 |
| [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm) | master / v1.19.0 | 68,333 | MIT | 借鉴按工作空间隔离资料及来源引用的设计 |
| [SillyTavern](https://github.com/SillyTavern/SillyTavern) | release / 1.19.0 | 35,675 | AGPL-3.0 | 借鉴角色档案、对话记忆与上下文设计 |
| [ComfyUI](https://github.com/Comfy-Org/ComfyUI) | master / v0.45.0 | 147,128 | GPL-3.0 | 后续独立服务 API 适配，当前未运行 |
| [ink](https://github.com/inkle/ink) | master / v1.2.1 | 5,021 | MIT | 备用分支脚本方案，暂缓引入 |
| [inkjs](https://github.com/y-lohse/inkjs) | master / v2.4.0 | 668 | MIT | 暂缓引入，避免图与脚本双模型 |
| [ts-fsrs](https://github.com/open-spaced-repetition/ts-fsrs) | main / binding@0.6.1 | 875 | MIT | 错题排程后置，实际 npm 版本及 Node 要求待复核 |

## 官方接口与实现观察

WebGAL使用React与引擎内部状态，官方存档函数读取模块单例、舞台状态、Redux store与画布预览。4.6.7发布版已在独立Next生产宿主中通过同源iframe装卸、动态脚本、显式题目提交、版本冲突回退和节点续玩实验。引擎会预取分支脚本，读取与业务写入需要分开。JS堆与加载体积实测见webgal-verification.md，生产私有课程、原生存档同步和总内存仍待验证。[WebGAL 存档源码](https://github.com/OpenWebGAL/WebGAL/blob/main/packages/webgal/src/Core/controller/storage/saveGame.ts)

Docling 支持多种文档格式和结构化表示，OCR 及版面模型适合作为独立 worker 候选。当前服务器目标为2核4GB，先让普通文档走轻量解析。已安装独立CPU实验环境并固定模型，原创跨行表格还原成功，扫描件中文遗漏与资源成本见docling-verification.md。公式专用模型和复杂扫描质量仍待评估。[Docling 官方项目](https://github.com/docling-project/docling)

AnythingLLM 以工作空间组织资料问答。GalStudy 的课程与用户必须成为检索硬边界，来源映射由自有数据表负责。当前完成按账号隔离的原文和知识点，RAG 聊天尚未实现。[AnythingLLM 官方项目](https://github.com/Mintplex-Labs/anything-llm)

SillyTavern 的角色配置、聊天历史与上下文管理作为交互参考。GalStudy 将独立定义角色档案、课程引用、摘要与用量字段，当前尚未实现自由聊天。[SillyTavern 官方项目](https://github.com/SillyTavern/SillyTavern)

ComfyUI 的 POST /prompt 校验并排队工作流，GET /history/{prompt_id} 查询历史，GET /view 读取输出，/ws 传递实时事件。未来后端只允许服务端配置的地址与模板，客户端提交白名单属性，生成任务与订单权益分离。当前尚未接入 Mock 工坊或真实 GPU。[官方 Server Routes](https://docs.comfy.org/development/comfyui-server/comms_routes)

## 实验 A · 剧情

原创两章固定剧情已实现两个首选分支、答题条件跳转、两个结局与服务端持久化存档。API 测试验证两条结局和版本冲突，浏览器测试验证桌面答错、手机答对与退出登录后续玩。实际截图为 story-desktop.png 和 story-mobile.png。

WebGAL初次在线iframe实验的跨域状态限制见webgal-probe.json。后续4.6.7同源发布版实验通过两分支、题目、两结局、409拒绝后的画面保持和节点续玩，证据见webgal-same-origin-result.json及webgal-verification.md。两条路线共用项目原创背景、角色和表情变体，当前继续采用自有状态机。

## 实验 B · 文档

scripts/make_samples.py 生成原创 PDF/PPTX/DOCX，包含英文标题、正文和表格文字。DOCX/PPTX 含中英混排，浏览器验收另生成 original-chinese.pdf，验证 PDF 中英文字提取。DOCX 保留内容块顺序，PPTX 保留幻灯片编号，PDF 保留页码。表格文字可提取，复杂 PDF 表格结构尚未还原。

no-text.pdf 为无文本页测试，损坏文档与空文件测试均检查明确错误。真实扫描图像识别、跨栏、嵌套形状、公式及合并单元格的复杂案例尚待扩充。账号 A/B 的课程、原文件下载、知识点修改、剧情与错题隔离由 API 测试覆盖。

下表为本机单次微型样本实验。进程耗时包含 Python 与依赖加载，解析耗时为导入完成后的函数时间。内存为10ms间隔采样到的 RSS 峰值，CPU 为进程累计秒，均不能用作大文件容量承诺。原始记录见 parser-benchmark.json。

| 文件 | 解析秒 | 进程秒 | 采样峰值 MiB | CPU秒 |
| --- | --- | --- | --- | --- |
| PDF | 0.0025 | 0.957 | 59.45 | 0.750 |
| PPTX | 0.0219 | 1.016 | 61.41 | 0.703 |
| DOCX | 0.0239 | 0.981 | 64.39 | 0.641 |

Docling与轻量解析器已对五类原创样本完成实际离线对照，记录CPU峰值/累计、RSS、首次/重复转换、表格结构和文字命中。结果及选型判断见docling-verification.md。

## 资源与部署边界

本机为 Windows、24逻辑CPU、约15.7GiB内存，Node 24.14.0、Python 3.12.4。Next.js 构建与浏览器验收在开发机运行。PostgreSQL原生Windows回归与Ubuntu WSL内Compose实际集成已完成，范围见postgresql-verification.md和compose-verification.md。

正式服务器计划运行 Web、API、PostgreSQL 与单解析 worker。2核4GB是否能承受真实负载仍需压测，100元/月为采购目标。普通文件采用大小、页数和解压上限。GPU、模型 API、复杂 OCR 应按需接入并实施额度，当前未产生这些调用。

## 剩余验证

- WebGAL生产私有课程桥、原生存档同步、浏览器总内存/长期释放与CPU对照。
- 更大课件、复杂扫描和公式模型的质量与目标环境容量评估。
- 目标公开部署环境的容量、数据恢复和运行验收。
- 更多角色表情变体与复杂演出验收，当前已有两张独立表情PNG。
- 后续阶段的 RAG、角色、订单权益与 ComfyUI 业务验证。
