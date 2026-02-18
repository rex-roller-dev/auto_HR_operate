import os
import platform
import subprocess
from pathlib import Path

def convert(docx_path: str, pdf_path: str):
    """
    Windows/macOS: 优先 docx2pdf
    Linux: 使用 LibreOffice headless
    """
    docx_path = Path(docx_path).resolve()
    pdf_path = Path(pdf_path).resolve()

    if not docx_path.exists():
        raise FileNotFoundError(f"DOCX 不存在: {docx_path}")

    system = platform.system()

    # ===== Windows / macOS =====
    if system in ("Windows", "Darwin"):
        try:
            from docx2pdf import convert as docx2pdf_convert
            docx2pdf_convert(str(docx_path), str(pdf_path))
            return
        except Exception as e:
            print("⚠️ docx2pdf 失败，尝试 LibreOffice:", e)

    # ===== Linux / fallback =====
    out_dir = pdf_path.parent

    subprocess.run(
        [
            "libreoffice",
            "--headless",
            "--convert-to", "pdf",
            str(docx_path),
            "--outdir", str(out_dir)
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    # LibreOffice 输出文件名是同名 pdf，需要重命名
    generated_pdf = out_dir / f"{docx_path.stem}.pdf"
    if not generated_pdf.exists():
        raise RuntimeError("LibreOffice 转 PDF 失败")

    generated_pdf.rename(pdf_path)
