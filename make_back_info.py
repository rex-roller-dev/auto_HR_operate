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



def make_back_info(exception: Exception, src_docx: str, szu_hours: float = None, image_path = "章.png") -> str:
    """
    根据处理结果生成志愿时认证表的回执文件（更新日期并加盖公章）。

    功能说明：
    - 当 exception 为 None 时：
        1. 读取指定的 Word 文档；
        2. 从文档末尾向前查找“深圳大学志愿者联合会”；
        3. 在其后找到第一个“年-月-日”格式的日期并替换为当天日期；
        4. 统一设置日期字体为 仿宋_GB2312，字号为 16；
        5. 将更新后的 Word 文档导出为 PDF；
        6. 在 PDF 指定位置叠加公章图片，生成最终盖章文件；
        7. 返回最终盖章 PDF 的路径。
    - 当 exception 不为 None 时：
        直接返回异常对象，用于上层流程判断失败原因。

    参数：
        exception (Exception | None):
            上游处理过程中产生的异常；为 None 表示流程正常。
        src_docx (str):
            原始“深圳大学志愿时认证表”的 Word 文件路径。
        image_path (str, optional):
            公章图片路径，默认使用当前目录下的“章.png”。

    返回：
        str | Exception:
            - 成功时：返回已盖章 PDF 文件的路径；
            - 失败时：返回传入的异常对象。

    异常：
        ValueError:
            - 未在文档中找到“深圳大学志愿者联合会”；
            - 未找到可替换的日期占位文本。

    备注：
        - 日期格式统一为“YYYY 年 MM 月 DD 日”；
        - PDF 盖章默认作用于第一页，坐标与尺寸可在函数内调整。
    
    """
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
        
                # 3️⃣ 替换深大义工志愿时长
                
        if szu_hours is not None:
            hours_pattern = re.compile(r"(深大义工系统内，)\s*个志愿时；")
            for para in doc.paragraphs:
                if hours_pattern.search(para.text):
                    new_text = hours_pattern.sub(f"\\1{szu_hours}个志愿时；", para.text)
                    para.clear()
                    run = para.add_run(new_text)
                    run.font.name = "仿宋_GB2312"
                    run.font.size = Pt(16)
                    run._element.rPr.rFonts.set(qn('w:eastAsia'), '仿宋_GB2312')
                    break
        
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