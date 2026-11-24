from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, BadZipFile
from docx import Document
from pptx import Presentation
from pypdf import PdfReader
from .providers import OCRProvider, UnavailableOCRProvider, OCRUnavailable


class ParseError(ValueError):
    pass


def parse_document(
    name: str, data: bytes, ocr: OCRProvider | None = None
) -> list[tuple[str, str]]:
    suffix = Path(name).suffix.lower()
    if not data:
        raise ParseError("文件为空，请重新上传。")
    if suffix not in {".pdf", ".docx", ".pptx"}:
        raise ParseError("仅支持 PDF、PPTX、DOCX。旧版 DOC 请另存为 DOCX。")
    if suffix != ".pdf":
        try:
            with ZipFile(BytesIO(data)) as archive:
                if (
                    sum(item.file_size for item in archive.infolist())
                    > 50 * 1024 * 1024
                ):
                    raise ParseError("文档解压后超过 50MB 限制。")
        except BadZipFile:
            raise ParseError("文件内容与格式不符，无法读取。")
    chunks = []
    try:
        if suffix == ".pdf":
            reader = PdfReader(BytesIO(data))
            if reader.is_encrypted:
                raise ParseError("请先移除 PDF 密码。")
            if len(reader.pages) > 100:
                raise ParseError("单个文件最多 100 页，请拆分上传。")
            for i, page in enumerate(reader.pages, 1):
                text = page.extract_text() or ""
                used_ocr = False
                if not text.strip():
                    try:
                        text = (ocr or UnavailableOCRProvider()).extract_pdf_page(
                            data, i
                        )
                        used_ocr = True
                    except OCRUnavailable as error:
                        raise ParseError(str(error))
                    if not text.strip():
                        raise ParseError(
                            f"第 {i} 页 OCR 未返回文字，请上传更清晰的文本版本。"
                        )
                chunks.append((f"第 {i} 页" + (" · OCR" if used_ocr else ""), text))
        elif suffix == ".docx":
            doc = Document(BytesIO(data))
            # Word page numbers depend on layout. Retain actual paragraph/table positions.
            for i, block in enumerate(doc.iter_inner_content(), 1):
                if hasattr(block, "rows"):
                    text = "\n".join(
                        " | ".join(c.text for c in row.cells) for row in block.rows
                    )
                    location = f"内容块 {i} · 表格"
                else:
                    text = block.text
                    location = f"内容块 {i} · {block.style.name}"
                if text.strip():
                    chunks.append((location, text))
        else:
            slides = Presentation(BytesIO(data)).slides
            if len(slides) > 100:
                raise ParseError("单个文件最多 100 张幻灯片。")
            for i, slide in enumerate(slides, 1):
                texts = []
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        texts.append(shape.text)
                    if shape.has_table:
                        texts.extend(
                            " | ".join(c.text for c in row.cells)
                            for row in shape.table.rows
                        )
                if any(t.strip() for t in texts):
                    chunks.append((f"幻灯片 {i}", "\n".join(texts)))
                else:
                    raise ParseError(f"幻灯片 {i} 无可提取文本。可选OCR支持扫描PDF，请导出PDF或手工补充知识点。")
    except ParseError:
        raise
    except Exception:
        raise ParseError("文档损坏或格式无法读取，请重新导出后上传。")
    if not chunks:
        raise ParseError("未发现可提取文字，请使用含文字的文档或扫描PDF的可选OCR。")
    if sum(len(text) for _, text in chunks) > 300_000:
        raise ParseError("提取文字超过 30 万字，请拆分文件。")
    return chunks
