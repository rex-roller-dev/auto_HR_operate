from docx import Document
from typing import Optional
import pdfplumber
from pathlib import Path
from text_normalizer import normalize_text

def extract_text_from_docx(path: str) -> str:
    """读取 docx，合并所有段落为一个字符串"""
    doc = Document(path)
    texts = []
    for p in doc.paragraphs:
        if p.text.strip():
            texts.append(p.text.strip())
    return "\n".join(texts)

def extract_text_from_pdf(path: Path) -> str:
    texts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                texts.append(t)
    return "\n".join(texts)

def extract_text(file_path: str) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".docx":
        return extract_text_from_docx(path)
    elif suffix == ".pdf":
        return extract_text_from_pdf(path)
    else:
        raise ValueError(f"不支持的文件类型: {suffix}")
    
if __name__ == "__main__":
    pdf_path = r"D:\D\file\auto_HR_operate\downloads\张宁宁_深圳大学志愿时认证表.pdf"
    word_path = r"D:\D\file\auto_HR_operate\downloads\深圳大学志愿时认证表(67).docx"

    pdf_text = extract_text(pdf_path)
    print("===== PDF 内容 =====")
    pdf_text = normalize_text(pdf_text)
    print(pdf_text)

    #word_text = extract_text(word_path)
    #print("===== Word 内容 =====")
    #print(word_text)