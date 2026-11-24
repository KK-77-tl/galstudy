# Docling与轻量解析器对照

2026-11-23完成记录核查。运行证据保存在docling-benchmark.json，逐个样本的原始结构、Markdown和日志保存在报告指定的test-results目录。五类原创样本、两个解析器共10个独立进程全部正常完成，每个进程转换两次。转换完成与内容识别质量分别记录。

Docling使用docling-slim 2.150.1，安装PDF、Office、本地模型和tesserocr所需模块，补装表格模型需要的opencv-python-headless。PyTorch 2.12.0+cpu、torchvision 0.27.0+cpu和完整精确版本见docling-environment.txt。独立环境位于忽略目录data/docling-env，布局和表格权重来自官方公开仓库，推理时设置HF_HUB_OFFLINE=1。

## 方法

每个文件启动一个新进程，首次转换包括该进程的模型初始化，第二次沿用已创建的转换器和已载入模型。表中时间排除Python导入和转换器构造，process_seconds及import_setup_seconds在JSON中另列。操作系统文件缓存未清空。

父进程每10ms采样子进程树RSS，取求和峰值，共享内存可能重复计量。CPU累计秒及约100ms窗口的CPU峰值同时记录，100%代表一个逻辑核。CPU线程参数设置为2，依赖库的初始化与辅助线程仍可能使用更多核。该实验使用本机24逻辑CPU环境，结果适用于这些微型样本。

两条OCR路径均配置180DPI，复用官方tessdata_fast中文和英文模型。Docling另需要osd.traineddata，来源与SHA256位于data/docling-models/sources.json。普通文本PDF关闭Docling OCR，扫描件启用全页OCR和Tesseract。表格结构功能开启，公式专用模型未启用。

| 文件 | 解析器 | 首次转换秒 | 再次转换秒 | RSS峰值MiB | CPU峰值 | CPU累计秒 | 预期文字命中 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| original.pdf | lightweight | 0.045 | 0.001 | 61.73 | 83.79% | 0.73 | 3/3 |
| original.pdf | docling | 60.574 | 4.834 | 1040.61 | 297.79% | 42.33 | 3/3 |
| original.pptx | lightweight | 0.018 | 0.005 | 62.01 | 76.45% | 0.62 | 6/6 |
| original.pptx | docling | 0.138 | 0.041 | 315.84 | 121.95% | 7.05 | 6/6 |
| original.docx | lightweight | 0.019 | 0.007 | 72.65 | 103.42% | 0.81 | 4/4 |
| original.docx | docling | 0.152 | 0.033 | 323.90 | 120.00% | 7.48 | 4/4 |
| original-layout.pdf | lightweight | 0.057 | 0.006 | 62.78 | 98.57% | 0.77 | 15/15 |
| original-layout.pdf | docling | 26.178 | 7.340 | 1082.29 | 246.86% | 49.19 | 15/15 |
| original-scan.pdf | lightweight | 0.931 | 0.341 | 185.72 | 110.50% | 1.66 | 4/4 |
| original-scan.pdf | docling | 23.135 | 5.688 | 1098.45 | 220.21% | 40.95 | 1/4 |

## 实际质量与来源

原创PDF、PPTX、DOCX和双栏PDF的预期文字均命中。PPTX的Docling来源包含幻灯片1、2，PDF包含页码1。DOCX返回结构引用且无物理页码，轻量解析器返回内容块位置。

original-layout.pdf由本项目原创HTML经本机Edge生成，包含中英双栏、带跨行单元格的表格及评分公式文本。预期字段保存在original-layout.expected.json。Docling识别一个3行4列表格，复习策略单元格跨2行，7个预期单元格内容全部命中。结果保留页码和结构引用。轻量路径完整提取了文字，其返回契约提供段落与来源位置。

在同一原创中英扫描件上，轻量Tesseract路径命中4项预期文字，Docling当前OCR配置只命中英文项，遗漏学习方法、检索练习、主动回忆知识。Docling结果将部分中文识别为拉丁字符，原始文本保存在该行output_directory下的extracted.md。当前保留该失败样本和配置，后续可单独调查OCR分段及语言处理。此次实验没有给出全学科或复杂扫描准确率结论。

评分公式score = correct / total作为文本被两条路径提取。公式结构化识别、手写、低清、旋转页面、跨页表格和更大课件的质量保持未测试。

## 选型结论

普通文件继续采用当前轻量解析，扫描件使用现有可选Tesseract适配器。Docling保留为复杂版面、表格结构的独立worker候选。本轮Docling PDF路径RSS约1GiB，普通轻量文本路径约62至73MiB，模型常驻成本及首次初始化时间需要纳入服务器容量与任务超时设计。按本轮样本直接切换默认解析器会增加资源成本，扫描件中文质量也有已观察到的缺口。

应用现有45秒解析子进程超时与Docling候选worker应分别评估，本文没有将Docling接入现有资料上传服务。2核4GB目标环境的并发容量仍需实际部署压测。

## 复跑

独立环境和数据目录均由项目忽略规则覆盖。先准备现有主项目测试环境与可选OCR模型，再安装本轮精确依赖。

```powershell
python -m venv data/docling-env
.\data\docling-env\Scripts\python.exe -m pip install --upgrade pip
.\data\docling-env\Scripts\python.exe -m pip install torch==2.12.0+cpu torchvision==0.27.0+cpu --index-url https://download.pytorch.org/whl/cpu
.\data\docling-env\Scripts\python.exe -m pip install -r docs/docling-environment.txt
.\.venv\Scripts\python.exe scripts/prepare_ocr.py
.\data\docling-env\Scripts\python.exe scripts/prepare_docling_models.py
.\.venv\Scripts\python.exe scripts/make_layout_sample.py
.\.venv\Scripts\python.exe scripts/docling_benchmark.py
```

三格式原始样本由make_samples.py生成，图像扫描样本由ocr_check.py生成，见ocr.md。运行时需要已有tests/samples/original-scan.pdf。

布局模型固定为docling-project/docling-layout-heron提交8f39ad3c0b4c58e9c2d2c84a38465abf757272d8，模型卡标记Apache-2.0。表格模型来自docling-project/docling-models提交fc0f2d45e2218ea24bce5045f58a389aed16dc23，模型卡标记CDLA-Permissive-2.0。本轮下载文件约530MB，逐文件摘要和OSD来源保存于模型清单。模型与原生库的实际分发声明继续按所采用文件复核。[布局模型](https://huggingface.co/docling-project/docling-layout-heron)，[表格模型](https://huggingface.co/docling-project/docling-models)

Docling模块和本地模型配置依据固定版本源码及官方文档。[固定版本依赖](https://github.com/docling-project/docling/blob/v2.150.1/pyproject.toml)，[离线模型与资源配置](https://docling-project.github.io/docling/usage/advanced_options/)
