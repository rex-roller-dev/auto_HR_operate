"""按官方文字版明细提取逐条记录；格式不完整时拒绝输出部分合计。"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import unicodedata

import pdfplumber

from .models import Activity, ParsedPDF, UserError, SZ, IV

DATE = re.compile(r"(?<!\d)(20\d{2})[.\-/年](\d{1,2})[.\-/月](\d{1,2})日?(?:\s+(\d{1,2}):(\d{2}))?")
DURATION = re.compile(r"(?:(\d+)小?时)?(?:(\d+)分(?:钟)?)?")
SOURCES = {"i志愿", "志愿深圳", "志愿中山", "江门义工", "志愿时"}


def compact(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or ""))


def dates(text):
    result = []
    for m in DATE.finditer(unicodedata.normalize("NFKC", text or "")):
        try:
            result.append(datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4] or 0), int(m[5] or 0)))
        except ValueError:
            raise UserError("PDF中存在无效活动日期") from None
    return result


def duration_minutes(text):
    text = compact(text).replace("小时", "时").replace("分钟", "分")
    match = DURATION.fullmatch(text)
    if not match or not any(x is not None for x in match.groups()):
        raise UserError("i志愿服务时间无法识别，请重新导出文字版明细")
    return Decimal(int(match[1] or 0) * 60 + int(match[2] or 0))


def decimal_minutes(text):
    try:
        hours = Decimal(compact(text))
        if not hours.is_finite() or hours < 0:
            raise InvalidOperation
        return hours * 60
    except InvalidOperation:
        raise UserError("志愿深圳核定服务时长不是有效的非负数字") from None


def unwatermarked(page):
    # 与原项目一致：只剔除斜向字符，不修改原始PDF。
    return page.filter(
        lambda obj: obj.get("object_type") != "char"
        or abs(obj.get("matrix", (1, 0, 0, 1))[1]) < 0.001
    )


def _sz_page(page, filename, number):
    records = []
    candidates = 0
    for table in page.extract_tables():
        for row in table:
            cells = [compact(c) for c in row]
            if not cells or not cells[0].isdigit():
                continue
            candidates += 1
            if len(cells) != 6:
                raise UserError(f"志愿深圳第{number}页考勤明细列不完整")
            if cells[5] not in ("服务时长", "培训时长"):
                raise UserError(f"志愿深圳第{number}页时长类型无法识别")
            times = dates(" ".join((row[2] or "").split()))
            if len(times) != 2:
                raise UserError(f"志愿深圳第{number}页考勤缺少完整起止时间")
            records.append(Activity(
                SZ, compact(row[1]), times[0], times[1], decimal_minutes(row[3]),
                SZ, filename, number, cells[0], cells[5],
            ))
    # 不把未读取到的页默认为0，防止只返回前几页的部分结果。
    if not candidates:
        raise UserError(f"志愿深圳第{number}页未读取到考勤明细，请上传“服务明细—导出明细”的文字版PDF")
    return records


def _iv_tables(page, filename, number):
    records = []
    for table in page.extract_tables():
        for row in table:
            cells = [compact(c) for c in row]
            # 活动时间是同一单元格的“开始日期 至 结束日期”，不是在整页寻找最近日期。
            indexes = [i for i, c in enumerate(cells) if "至" in c and len(dates(c)) == 2]
            if not indexes:
                continue
            if len(indexes) != 1:
                raise UserError(f"i志愿第{number}页活动时间列存在歧义")
            i = indexes[0]
            if i == 0 or len(cells) < i + 3:
                raise UserError(f"i志愿第{number}页活动列不完整")
            times = dates(cells[i])
            source = cells[-1]
            duration = cells[-2]
            if not source:
                raise UserError(f"i志愿第{number}页缺少数据来源")
            records.append(Activity(
                IV, cells[i - 1], times[0], times[1], duration_minutes(duration),
                source, filename, number,
            ))
    return records


def _iv_words(page, filename, number):
    """兼容无表格边框的官方PDF，以“至”的纵向位置划分独立活动行。"""
    words = page.extract_words(x_tolerance=2, y_tolerance=3)
    markers = [w for w in words if compact(w["text"]) == "至"]
    markers.sort(key=lambda w: (w["top"], w["x0"]))
    if not markers:
        return []
    records = []
    for i, marker in enumerate(markers):
        center = (marker["top"] + marker["bottom"]) / 2
        top = ((markers[i-1]["top"] + markers[i-1]["bottom"]) / 2 + center) / 2 if i else max(0, center - ((markers[1]["top"] - marker["top"]) / 2 if len(markers) > 1 else 55))
        bottom = (center + (markers[i+1]["top"] + markers[i+1]["bottom"]) / 2) / 2 if i+1 < len(markers) else min(page.height, center + ((marker["top"] - markers[i-1]["top"]) / 2 if i else 55))
        band = [w for w in words if top <= (w["top"] + w["bottom"]) / 2 < bottom]
        xcenter = (marker["x0"] + marker["x1"]) / 2
        date_words = [w for w in band if dates(w["text"]) and abs((w["x0"] + w["x1"]) / 2 - xcenter) < page.width * 0.065]
        before = [w for w in date_words if w["top"] < marker["top"]]
        after = [w for w in date_words if w["top"] > marker["top"]]
        if not before or not after:
            raise UserError(f"i志愿第{number}页第{i+1}条记录缺少独立的起止日期")
        start_word = max(before, key=lambda w: w["top"])
        end_word = min(after, key=lambda w: w["top"])
        begin = dates(start_word["text"])[0]
        end = dates(end_word["text"])[0]
        right = [w for w in band if w["x0"] > marker["x1"] + page.width * 0.2]
        source_words = [w for w in right if compact(w["text"]).replace("I志愿", "i志愿") in SOURCES]
        if not source_words:
            raise UserError(f"i志愿第{number}页第{i+1}条记录的数据来源无法识别，请提供原始文字版明细")
        source_word = max(source_words, key=lambda w: w["x0"])
        source = compact(source_word["text"]).replace("I志愿", "i志愿")
        duration_words = [
            w for w in right
            if w["x1"] <= source_word["x0"] + 1
            and source_word["x0"] - w["x1"] < page.width * 0.16
            and DURATION.fullmatch(compact(w["text"]).replace("小时", "时").replace("分钟", "分"))
            and any(c in w["text"] for c in "时分")
        ]
        if len(duration_words) != 1:
            raise UserError(f"i志愿第{number}页第{i+1}条记录的核定服务时间存在歧义")
        title_words = [w for w in band if w["x1"] < start_word["x0"] - 2]
        title = "".join(w["text"] for w in sorted(title_words, key=lambda w: (round(w["top"], 1), w["x0"])))
        if not title:
            raise UserError(f"i志愿第{number}页第{i+1}条记录缺少活动名称")
        records.append(Activity(
            IV, title, begin, end, duration_minutes(duration_words[0]["text"]),
            source, filename, number,
        ))
    return records


def parse_pdf(path, platform, max_pages=150, filename=None):
    filename = filename or Path(path).name
    records = []
    texts = []
    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages or len(pdf.pages) > max_pages:
                raise UserError(f"PDF页数须在1至{max_pages}页之间")
            for number, original in enumerate(pdf.pages, 1):
                page = unwatermarked(original)
                text = page.extract_text() or ""
                texts.append(text)
                if not text.strip():
                    raise UserError(f"{platform}第{number}页没有可读取文字，不支持扫描件或截图PDF")
                if platform == SZ:
                    records.extend(_sz_page(page, filename, number))
                elif platform == IV:
                    table_records = _iv_tables(page, filename, number)
                    # 有表格时也核对“至”的数量，防止某些行在表格提取中丢失。
                    marker_count = sum(compact(w["text"]) == "至" for w in page.extract_words())
                    if table_records and len(table_records) == marker_count:
                        records.extend(table_records)
                    elif marker_count:
                        records.extend(_iv_words(page, filename, number))
                    elif not any(key in text for key in ("志愿者", "证件类型", "说明")):
                        raise UserError(f"i志愿第{number}页未找到活动明细")
                else:
                    raise UserError("不支持的PDF平台")
    except UserError:
        raise
    except Exception:
        # 不将PDF内部文本、证件信息或异常对象原文发到日志/邮件。
        raise UserError(f"{platform}PDF无法完整解析，请重新导出未加密的文字版服务明细") from None
    if not records:
        raise UserError(f"{platform}PDF未读取到任何活动明细；不能据此认定时长为0")
    text = "\n".join(texts)
    pattern = r"姓名\s*[:：]?\s*([^\s:：]+)" if platform == SZ else r"志愿者\s*[:：]\s*([^\s:：]+)"
    names = {compact(m) for m in re.findall(pattern, text)}
    return ParsedPDF(records, names, [] if names else [f"{platform}PDF未提取到姓名，无法自动核对材料所属人"])
