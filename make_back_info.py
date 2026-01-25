from docx import Document
from docx.shared import Cm
import fitz  # PyMuPDF
from datetime import datetime
import re
from docx.shared import Pt
from docx.oxml.ns import qn
from docx2pdf import convert

def stamp_pdf(
    pdf_path: str,
    stamp_img_path: str,
    output_pdf_path: str,
    page_index: int,
    x: float,
    y: float,
    width: float,
    height: float
):
    doc = fitz.open(pdf_path)
    page = doc[page_index]

    rect = fitz.Rect(
        x,
        y,
        x + width,
        y + height
    )

    page.insert_image(
        rect,
        filename=stamp_img_path,
        overlay=True  # ✅ 关键：盖在文字上方
    )

    doc.save(output_pdf_path)
    doc.close()
    return output_pdf_path



def make_back_info(exception: Exception, src_docx: str, image_path = "章.png") -> str:
    if exception is None:
        """
        找到【倒数最后一个】“深圳大学志愿者联合会”
        并将其后第一个年月日改为今天
        """
        doc = Document(src_docx)

        today = datetime.now().strftime("%Y 年 %m 月 %d 日")

        date_pattern = re.compile(r"\d{0,4}\s*年\s*\d{0,2}\s*月\s*\d{0,2}\s*日")

        # 1️⃣ 找到倒数第一个“深圳大学志愿者联合会”
        target_para_index = None
        for i in range(len(doc.paragraphs) - 1, -1, -1):
            if "深圳大学志愿者联合会" in doc.paragraphs[i].text:
                target_para_index = i
                break

        if target_para_index is None:
            raise ValueError("未找到“深圳大学志愿者联合会”")

        # 2️⃣ 从它后面找第一个“年月日”
        for para in doc.paragraphs[target_para_index + 1:]:
            match = date_pattern.search(para.text)
            if not match:
                continue

            # 清空原有 runs（否则样式会乱）
            para.clear()

            # 新建 run，写入今天日期
            run = para.add_run(today)

            # 3️⃣ 设置字体
            run.font.name = "仿宋_GB2312"
            run.font.size = Pt(16)

            # ⚠️ 中文必须加这个（非常关键）
            run._element.rPr.rFonts.set(qn('w:eastAsia'), '仿宋_GB2312')

            break
        else:
            raise ValueError("未找到日期占位")
        
        doc.save(r".\downloads\深圳大学志愿时认证表_已更新.docx")

        # 4️⃣ 转 PDF
        convert(
            r".\downloads\深圳大学志愿时认证表_已更新.docx",
            r".\downloads\深圳大学志愿时认证表_未盖章.pdf"
        )

                # 5️⃣ PDF 盖章（浮于文字上方）
        pdf_path = r".\downloads\深圳大学志愿时认证表_未盖章.pdf"
        stamped_pdf_path = r".\downloads\深圳大学志愿时认证表_已盖章.pdf"

        output_path = stamp_pdf(
            pdf_path=pdf_path,
            stamp_img_path = image_path,
            output_pdf_path=stamped_pdf_path,
            page_index=0,     # 第一页
            x=360,            # ↓ 这几个值你可以微调
            y=440,
            width=130,
            height=130
        )
        return output_path
    else:
        return exception


    
if __name__ == "__main__":
    a = make_back_info(ValueError("111"), "D:\\D\\file\\auto_HR_operate\\downloads\\深圳大学志愿时认证表(67).docx")
    print(a)