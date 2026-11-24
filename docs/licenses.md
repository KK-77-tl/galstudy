# 许可证与素材登记

记录日期为2026-11-16。研究项目与运行依赖分开登记。实际分发应附带已使用依赖的版权与许可证文件，字体、模型和素材分别审查。

## 研究参考

| 项目 | 许可 | 本项目当前使用 |
| --- | --- | --- |
| WebGAL | MPL-2.0 | 官方4.6.7发布版用于本地隔离实验，保存于忽略的data目录，当前应用采用自有运行时 |
| Docling | MIT | 独立CPU研究环境docling-slim 2.150.1，固定模型提交与实际对照见docling-verification.md |
| AnythingLLM | MIT | 资料问答设计参考 |
| SillyTavern | AGPL-3.0 | 产品概念参考 |
| ComfyUI | GPL-3.0 | 官方 API 文档参考，未安装 |
| ink / inkjs / ts-fsrs | MIT | 备选调研，未安装 |

许可原文可从各仓库 LICENSE 获取，官方项目链接与实际分支见 opensource-research.md。未经单独许可评估，AGPL 实现代码、第三方演示美术、checkpoint、LoRA 与工作流均不得直接并入商业产品。

## 当前直接依赖

| 依赖 | 许可 |
| --- | --- |
| Next.js / React / React DOM / TypeScript / Tailwind CSS / Zod | MIT |
| lucide-react | ISC，部分图标继承 Feather MIT，保留包内声明 |
| FastAPI / Starlette / SQLAlchemy / python-docx / python-pptx / python-dotenv | MIT |
| Uvicorn | BSD-3-Clause |
| pypdf | BSD-3-Clause |
| argon2-cffi | MIT |
| python-multipart | Apache-2.0 |
| httpx | BSD-3-Clause |
| httpx2（测试） | BSD-3-Clause |
| Pillow 13.0.0 | MIT-CMU，图片解码与元数据清理 |
| tesserocr 2.13.0（可选OCR） | MIT封装，内含Tesseract/Leptonica等原生组件声明需保留 |
| pypdfium2 5.15.2（可选OCR） | BSD-3-Clause、Apache-2.0及PDFium依赖声明 |
| tessdata_fast中文/英文模型 | Apache-2.0，来源及摘要见data/tessdata/sources.json |
| psycopg | LGPL-3.0，binary 打包依赖须保留各自声明 |
| PostgreSQL | PostgreSQL License |
| pytest（测试） | MIT |
| Playwright（测试） | Apache-2.0 |
| psutil（基准） | BSD-3-Clause |

前端具体版本与逐包许可见 package-lock.json。Python依赖版本见backend/requirements.txt。dependency-inventory.json已生成当前独立虚拟环境49个包、前端锁文件108个条目的许可元数据，含开发依赖及可选包安装状态。发布镜像、打包原生库、完整版权声明与素材许可仍需逐项复核。

PostgreSQL 17.12的Windows免安装归档由官网指向的EDB分发，用于项目内临时开发验证，存储于忽略目录data/postgresql-17.12。来源、摘要及执行证据见postgresql-verification.md。容器发布依赖继续按实际镜像及所含组件审查。

## PyMuPDF 调整

推荐清单中的 PyMuPDF 采用 AGPL/商业双许可。当前应用使用 pypdf 提取 PDF，项目运行依赖未引入 PyMuPDF。开发机已有 PyMuPDF 的安装与 GalStudy 的依赖声明分别管理。[官方许可](https://github.com/pymupdf/PyMuPDF/blob/main/COPYING)

## 原创演示内容与图像

- 学习方法教材、固定剧情、角色名字与人设由本项目编写。
- classroom.webp 由内置 imagegen 工具生成，原始文件 classroom-original.png。角色 shiori.png 同样由内置工具生成。
- 图像作为 AI 生成的演示素材使用，页面明确 Demo 状态。正式商业发布前复核所适用的生成服务条款及素材来源记录。
- 页面字体使用系统回退，未打包外部字体文件。
- 用户上传的私有教材通过会话授权访问，支持删除原文件及关联提取结果。真实人物参考图需要同意确认，图片默认保留7天并支持删除，Mock与后台审核流程见workshop.md。

## 图像提示词与工具记录

完整工具、文件路径与生产提示词保存于 assets.json。教室、小栞、图书馆、遥与凛均已复制到项目 frontend/public/assets，页面直接使用这些本地文件。工作区既有序章素材沿用原任务来源记录，正式发行时须一并复核。


## 2026-11-17 · WebGAL实验与表情变体

WebGAL发布归档来源、固定SHA256、提取范围与实际加载记录见webgal-verification.md及webgal-same-origin-result.json。准备脚本保留官方LICENSE-WebGAL文本并跳过game/。引擎附带的三个TTF、UI图标与声音属于独立素材登记范围，商业分发审查仍开放。

新增shiori-happy.png及haruka-gentle.png由内置image_gen基于项目既有原创角色生成，保留RGBA通道。完整提示词、原图与生成文件路径已追加assets.json。两张图通过角色API的expressions映射用于剧情，并用于隔离的WebGAL实验。

## 2026-11-23 · Docling研究环境

Docling-slim 2.150.1及CPU版PyTorch位于独立data/docling-env，完整依赖版本见docling-environment.txt。布局模型卡标记Apache-2.0，TableFormer所在模型仓库标记CDLA-Permissive-2.0，固定提交和逐文件SHA256见data/docling-models/sources.json。该目录另记录Tesseract官方OSD模型来源和摘要，已有中英模型来源继续见data/tessdata/sources.json。原生OpenCV、PyTorch及其他依赖的分发声明按采用文件复核。

新增original-layout.pdf由项目原创HTML经本机Edge生成，包含双栏、跨行表格及评分公式文本。生成器为scripts/make_layout_sample.py，预期字段为tests/samples/original-layout.expected.json。系统字体通过本机浏览器排版，字体文件未复制到项目。实验范围、资源数据和内容识别缺口见docling-verification.md。

2026-11-23补充：隔离data/alipay-env使用官方alipay-sdk-python 3.7.1411（Apache-2.0）做离线协议实验，依赖冻结于alipay-environment.txt。SDK和依赖尚未加入主应用或生产镜像；实际分发时应保留对应许可证与必要通知。来源和范围见alipay-contract-verification.md。

支付适配现使用rsa 4.9.1（Apache-2.0）及pyasn1 0.6.5（BSD-2-Clause），已加入主开发环境，并写入Dockerfile依赖安装。完整官方SDK仍仅用于隔离研究。新镜像因基础镜像元数据网络失败尚未构建通过，分发时保留依赖许可证与通知。
