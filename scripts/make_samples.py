"""Create original fixtures used by parser and browser acceptance tests."""

from pathlib import Path
from docx import Document
from pptx import Presentation
from pptx.util import Inches
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject


def make_samples(directory=Path("tests/samples")):
    directory.mkdir(parents=True, exist_ok=True)
    doc = Document()
    doc.add_heading("学习方法 Study methods", 0)
    doc.add_paragraph("检索练习 Retrieval practice 是主动从记忆中提取知识。")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "方法 Method", "示例 Example"
    table.cell(1, 0).text, table.cell(1, 1).text = "主动回忆", "合上书复述"
    doc.save(directory / "original.docx")
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[1])
    slide.shapes.title.text = "学习方法 Study methods"
    slide.placeholders[1].text = "检索练习 Retrieval practice\n合上书复述要点。"
    slide = deck.slides.add_slide(deck.slide_layouts[5])
    slide.shapes.title.text = "方法对照 Methods"
    table = slide.shapes.add_table(
        2, 2, Inches(1), Inches(2), Inches(7), Inches(1)
    ).table
    table.cell(0, 0).text, table.cell(0, 1).text = "Recall", "回忆"
    table.cell(1, 0).text, table.cell(1, 1).text = "Read", "阅读"
    deck.save(directory / "original.pptx")
    writer = PdfWriter()
    page = writer.add_blank_page(595, 842)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(
        b"BT /F1 18 Tf 50 770 Td (Study methods) Tj 0 -35 Td /F1 12 Tf (Retrieval practice means recalling information from memory.) Tj 0 -25 Td (Method | Example) Tj 0 -25 Td (Recall | Close the book and explain.) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(directory / "original.pdf")
    scan = PdfWriter()
    scan.add_blank_page(595, 842)
    scan.write(directory / "no-text.pdf")
    return directory


if __name__ == "__main__":
    print(make_samples())
