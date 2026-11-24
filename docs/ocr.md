# 本地扫描PDF OCR

2026-11-17。可选Tesseract适配器已真实识别原创中英扫描PDF，并通过上传、来源定位和知识草稿流程。默认OCR_MODE=disabled，文本PDF走pypdf提取。

## 配置与复跑

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-ocr.txt
.\.venv\Scripts\python.exe scripts/prepare_ocr.py
.\.venv\Scripts\python.exe scripts/ocr_check.py
```

在服务端.env设置OCR_MODE=tesseract，OCR_DATA_PATH=data/tessdata，OCR_LANGUAGES=chi_sim+eng，然后重启API。健康端点ocr和课程详情ocr_enabled展示组件与模型文件的就绪状态，上传区域据此展示扫描PDF能力。依赖或模型缺失返回明确错误，识别来源带页码及OCR标记，草稿继续由用户编辑确认。

可选依赖为tesserocr 2.13.0和pypdfium2 5.15.2，本机Windows轮包实际加载Tesseract 5.5.4及Leptonica 1.87.0。其他系统按对应平台安装原生库或编译依赖，Linux容器仍需实际构建验证。[tesserocr官方项目](https://github.com/sirfz/tesserocr)、[Tesseract安装说明](https://tesseract-ocr.github.io/tessdoc/Installation.html)

prepare_ocr.py下载官方tessdata_fast的eng及chi_sim模型，合计约6.6MB，连同LICENSE、提交号及SHA256放在忽略目录data/tessdata。当前提交为87416418657359cb625c412a48b6e1d6d41c29bd，完整来源见该目录sources.json。[官方语言模型](https://github.com/tesseract-ocr/tessdata_fast)

## 资源与隐私

文字提取为空时才启用OCR。默认180 DPI、每页最多800万像素、每份文件最多10个OCR页。支持配置72至300 DPI、100万至1600万像素和1至100个OCR页，原有100页及30万字上限继续生效。

PDFium调用以进程内锁串行执行，显式关闭文档、页面与位图。Tesseract运行于现有解析子进程，默认OMP_THREAD_LIMIT=1，整个解析任务45秒硬超时。渲染图像在内存中处理并释放，结果与原PDF沿用私有课程权限及删除流程。[PDFium线程与内存说明](https://pypdfium2.readthedocs.io/en/stable/python_api.html)

配置、缺模型、原生库加载、像素/页数超限、空结果和识别失败均给出错误反馈。图片型PPTX或DOCX可导出PDF后识别，或手工补充知识点。

## 已验证

ocr_check.py使用系统微软雅黑绘制原创文字并生成图像型PDF，先确认PDF没有文本层，再经backend.parse_worker识别。验证了“检索练习”“主动回忆知识”和“Retrieval practice”，原始输出及耗时见ocr-result.json。样本内嵌栅格图像，字体由系统提供。

tests/test_ocr.py覆盖配置、缺模型、页数预算、像素上限、文本PDF跳过OCR、来源标记、真实识别、上传/worker及账号隔离。缺少可选依赖、模型或扫描样本时，两项真实识别测试skip，本机全部执行。原有测试默认关闭OCR，继续验证未配置退路。

启动生产构建网页后执行隔离浏览器验收。

```powershell
$env:E2E_OCR='1'
.\.venv\Scripts\python.exe scripts/cloud_browser_probe.py
```

该流程使用真实本地OCR和模拟课程模型，临时API结束时关闭。手机与桌面的上传、OCR出处和编辑框已验证，截图ocr-mobile.png、ocr-desktop.png，记录cloud-browser-result.json。

当前样本为清晰正向的中英单页。倾斜、低清、手写、复杂表格、公式、跨栏与批量扫描质量仍需数据集评估。Docling对照、Linux容器、操作系统级内存配额和生产负载继续开放。
