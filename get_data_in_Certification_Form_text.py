from datetime import datetime
import re
from text_loader import extract_text
from typing import Optional
from text_normalizer import normalize_text

def find_first(pattern: str, text: str, cast=None, allow_multiline=True) -> Optional[object]:
    flags = re.S if allow_multiline else 0  # 只有允许跨行时才加 re.S
    m = re.search(pattern, text, flags)
    if not m:
        return None
    value = m.group(1).strip()
    if value == "":
        return None
    if cast:
        try:
            return cast(value)
        except ValueError:
            return None
    return value


def parse_date_flexible(date_str: str) -> Optional[str]:
    """
    支持：
    - YYYY 年 M 月 D 日
    - YYYY 年 M 月日   （视为 YYYY-MM-01）
    - YYYY 年 M 月     （视为 YYYY-MM-01）
    """
    date_str = date_str.strip()

    # 完整日期
    m_full = re.match(
        r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
        date_str
    )
    if m_full:
        y, m, d = m_full.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"

    # 月日（但没有具体日）
    m_month_day_word = re.match(
        r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*日",
        date_str
    )
    if m_month_day_word:
        y, m = m_month_day_word.groups()
        return f"{y}-{int(m):02d}-01"

    # 只有年月
    m_month_only = re.match(
        r"(\d{4})\s*年\s*(\d{1,2})\s*月",
        date_str
    )
    if m_month_only:
        y, m = m_month_only.groups()
        return f"{y}-{int(m):02d}-01"

    return None



def parse_volunteer(path: str) -> dict:
    text = extract_text(path)
    text = normalize_text(text)# 规范化文本

    # ===== 基本信息 =====
    name = find_first(
        r"经核查\s*([^\s]+)\s*同学",
        text
    )

    student_id = find_first(
        r"学号[:：]?\s*(\d+)",
        text
    )

    start_raw = find_first(
        r"(\d{4}\s*年\s*\d{1,2}\s*月\s*(?:\d{1,2}\s*日|日)?)\s*至",
        text
    )


    end_raw = find_first(
        r"至\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)",
        text
    )

    start_date = parse_date_flexible(start_raw) if start_raw else None
    end_date = parse_date_flexible(end_raw) if end_raw else None

    # ===== 系统志愿时 =====
    # 1. 深大义工系统
    szu_hours = find_first(
        r"深大义工系统内.*?([\d.]+)\s*(?:小时|个义工时|个志愿时)",
        text,
        float,
        allow_multiline=False  # 这里设为 False，正则就不会跨行
    )

    # 2. 志愿深圳系统
    shenzhen_hours = find_first(
            r"志愿深圳系统内.*?([\d.]+)\s*(?:小时|个志愿时)",
            text,
            float,
            allow_multiline=False
        )


    i_volunteer_hours = find_first(
            r"[iI]志愿系统内.*?([\d.]+)\s*个志愿时",
            text,
            float,
            allow_multiline=False
        )

    # ===== 广东省外志愿（最多两组）=====
    external_matches = re.findall(
        r"([\u4e00-\u9fa5A-Za-z0-9]+)\s*系统内[，,]\s*志愿时\s*([\d.]+)",
        text
    )

    external_system_1 = external_matches[0][0] if len(external_matches) >= 1 else None
    external_system_1_hours = float(external_matches[0][1]) if len(external_matches) >= 1 else None

    external_system_2 = external_matches[1][0] if len(external_matches) >= 2 else None
    external_system_2_hours = float(external_matches[1][1]) if len(external_matches) >= 2 else None

    # ===== 总志愿时 =====
    total_hours = find_first(
        r"志愿时总数为\s*([\d.]+)",
        text,
        float
    )

    # 若未给出总数，则按规则计算
    if total_hours is None:
        total_hours = 0.0
        for h in [
            szu_hours,
            shenzhen_hours,
            i_volunteer_hours,
            external_system_1_hours,
            external_system_2_hours,
        ]:
            if isinstance(h, (int, float)):
                total_hours += h

    # ===== 统一 None / 0 逻辑 =====
    def normalize(v):
        if v is None:
            return None
        if isinstance(v, float) and v.is_integer():
            return int(v)
        return v

    result = {
        "name": name,
        "student_id": student_id,
        "start_date": start_date,
        "end_date": end_date,

        "szu_volunteer_hours": normalize(szu_hours),
        "volunteer_shenzhen_hours": normalize(shenzhen_hours),
        "i_volunteer_hours": normalize(i_volunteer_hours),

        "external_system_1": external_system_1,
        "external_system_1_hours": normalize(external_system_1_hours),
        "external_system_2": external_system_2,
        "external_system_2_hours": normalize(external_system_2_hours),

        "total_hours": normalize(total_hours),
    }

    return result


if __name__ == "__main__":
    path = r"C:\Users\0\Desktop\test\识别错误.docx"
    data = parse_volunteer(path)
    end_date = datetime.strptime(data["end_date"], "%Y-%m-%d").date()
    print(end_date.year)
    print(data)
