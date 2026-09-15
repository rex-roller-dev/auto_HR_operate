import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pdfplumber

from exceptions import FileError
from text_loader import extract_text


def _service_hours_in_range(path: str, start_date: date, end_date: date) -> float:
    """读取文字版明细；与认证区间有重叠的服务记录按核定时长全额计入。"""
    total = Decimal("0")
    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            # 官方报表的斜向网址水印会混入表格单元格，仅在提取时过滤。
            page = page.filter(
                lambda obj: obj["object_type"] != "char"
                or abs(obj.get("matrix", (1, 0, 0, 1))[1]) < 0.001
            )
            record_count = 0
            for table in page.extract_tables():
                for row in table:
                    if len(row) != 6:
                        if row and (row[0] or "").strip().isdigit():
                            raise FileError(f"志愿深圳第{page_number}页明细列不完整")
                        continue
                    record_id = (row[0] or "").strip()
                    kind = (row[5] or "").strip()
                    if kind == "培训时长":
                        record_count += 1
                        continue
                    if kind != "服务时长":
                        if record_id.isdigit():
                            raise FileError(f"志愿深圳第{page_number}页明细时长类型无法识别")
                        continue

                    record_count += 1
                    try:
                        if not record_id.isdigit():
                            raise ValueError("缺少考勤编号")
                        times = re.fullmatch(
                            r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) "
                            r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})",
                            " ".join((row[2] or "").split()),
                        )
                        if times is None:
                            raise ValueError("缺少服务起止时间")
                        begin, finish = (
                            datetime.strptime(value, "%Y-%m-%d %H:%M")
                            for value in times.groups()
                        )
                        hours = Decimal((row[3] or "").strip())
                        if finish < begin or not hours.is_finite() or hours < 0:
                            raise ValueError("服务日期或时长无效")
                    except (ValueError, InvalidOperation) as exc:
                        raise FileError(
                            f"志愿深圳第{page_number}页考勤{record_id}明细无法解析，"
                            "请重新导出文字版服务明细"
                        ) from exc

                    # 包含认证起止日；跨界记录全额计入，不按重叠时间折算。
                    if begin.date() <= end_date and finish.date() >= start_date:
                        total += hours
            if record_count == 0:
                raise FileError(
                    f"志愿深圳第{page_number}页未读取到明细，请上传文字版服务明细"
                )
    return float(total)


def parse_szvolunteer(path: str, start_date: date, end_date: date) -> dict:
    """
    解析志愿深圳身份信息，并按认证表起止日期汇总服务明细（不计培训）。
    
    :param path: 文件路径
    :type path: str
    :return: 解析结果字典
    :rtype: dict
    """
    text = extract_text(path)
    name = re.search(r"姓名\s*([^\s]+)", text)
    volunteer_id = re.search(r"(志愿者号|义工号)\s*(\d+)", text)
    service_time = _service_hours_in_range(path, start_date, end_date)

    result = {
        "姓名": name.group(1) if name else None,
        "义工号": volunteer_id.group(2) if volunteer_id else None,
        "服务时长": service_time
    }

    return result

if __name__ == "__main__":
    path = r"C:\Users\0\Desktop\志愿深圳时长证明(1).pdf"
    data = parse_szvolunteer(path, date(2025, 9, 1), date(2026, 8, 31))
    print(data)