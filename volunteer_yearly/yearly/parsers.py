"""按官方文字版明细提取逐条记录；格式不完整时拒绝输出部分合计。"""
from dataclasses import replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
import re
from statistics import median
import unicodedata

import pdfplumber

from .models import Activity, ParsedPDF, UserError, SZ, IV

DATE = re.compile(r"(?<!\d)(20\d{2})[.\-/年](\d{1,2})[.\-/月](\d{1,2})日?(?:\s+(\d{1,2}):(\d{2}))?")
DURATION = re.compile(r"(?:(\d+)小?时)?(?:(\d+)分(?:钟)?)?")
SOURCES = {"i志愿", "志愿深圳", "志愿中山", "江门义工", "志愿时"} | {"广州志愿时"}


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


def period(text, location):
    raw = unicodedata.normalize("NFKC", text or "")
    values = dates(raw)
    if len(values) == 2:
        return values[0], values[1]
    remainder = compact(DATE.sub("", raw))
    remainder = re.sub(r"(?:暂无|未知|未提供|未填写|未记录|未注明|待定|无|N/?A)", "", remainder, flags=re.I)
    remainder = re.sub(r"[至~～—–－\-/\\,，;；:：.。]", "", remainder)
    if len(values) <= 1 and not remainder:
        if not values:
            return None, None
        if "至" in raw and not dates(raw.split("至", 1)[0]):
            return None, values[0]
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if len(lines) > 1 and not dates(lines[0]):
            return None, values[0]
        return values[0], None
    raise UserError(f"{location}活动日期无法识别，请提供原始文字版明细")


def is_duration(text):
    value = compact(text).replace("小时", "时").replace("分钟", "分")
    return bool(value and DURATION.fullmatch(value) and any(c in value for c in "时分"))


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
            begin, end = period(row[2], f"志愿深圳第{number}页考勤")
            records.append(Activity(
                SZ, compact(row[1]), begin, end, decimal_minutes(row[3]),
                SZ, filename, number, cells[0], cells[5],
            ))
    # 不把未读取到的页默认为0，防止只返回前几页的部分结果。
    if not candidates:
        raise UserError(f"志愿深圳第{number}页未读取到考勤明细，请上传“服务明细—导出明细”的文字版PDF")
    return records


def _iv_tables(page, filename, number):
    records = []
    covered_markers = 0
    for table in page.extract_tables():
        time_column = None
        for row in table:
            cells = [compact(c) for c in row]
            if "活动时间" in cells:
                time_column = cells.index("活动时间")
                continue
            if len(cells) < 4:
                continue
            # 活动时间是同一单元格的“开始日期 至 结束日期”，不是在整页寻找最近日期。
            column = time_column if time_column is not None else (2 if len(cells) == 9 else None)
            looks_like_record = (cells[-1].replace("I志愿", "i志愿") in SOURCES or is_duration(cells[-2]))
            indexes = ([column] if column is not None and looks_like_record else
                       [i for i, c in enumerate(cells) if "至" in c and len(dates(c)) == 2])
            if not indexes:
                continue
            if len(indexes) != 1:
                raise UserError(f"i志愿第{number}页活动时间列存在歧义")
            i = indexes[0]
            if i == 0 or len(cells) < i + 3:
                raise UserError(f"i志愿第{number}页活动列不完整")
            begin, end = period(row[i], f"i志愿第{number}页")
            source = cells[-1]
            duration = cells[-2]
            if not source:
                raise UserError(f"i志愿第{number}页缺少数据来源")
            records.append(Activity(
                IV, cells[i - 1], begin, end, duration_minutes(duration),
                source, filename, number,
            ))
            covered_markers += cells[i].count("至")
    return records, covered_markers


def _iv_words(page, filename, number):
    """Use source/duration rows as anchors so undated rows are retained too."""
    words = page.extract_words(x_tolerance=2, y_tolerance=3)
    middle = lambda word: (word["top"] + word["bottom"]) / 2
    markers = [w for w in words if compact(w["text"]) == "至"]
    headers = [w for w in words if compact(w["text"]) == "活动时间"]
    sources = [w for w in words if w["x0"] > page.width * 0.55
               and compact(w["text"]).replace("I志愿", "i志愿") in SOURCES]
    unused = list(markers)
    anchors, offsets = [], []
    for source in sorted(sources, key=middle):
        durations = [w for w in words if is_duration(w["text"])
                     and w["x1"] <= source["x0"] + 1
                     and source["x0"] - w["x1"] < page.width * 0.16
                     and abs(middle(w) - middle(source)) <= 12]
        if not durations:
            continue
        if headers and middle(source) <= max(w["bottom"] for w in headers):
            continue
        nearby_missing = any(compact(w["text"]) in ("-", "—", "–", "--", "/", "无", "暂无", "未知")
                             and page.width * 0.18 < w["x0"] < min(d["x0"] for d in durations)
                             and abs(middle(w) - middle(source)) <= 18 for w in words)
        if not headers and ((not markers) or middle(source) < min(map(middle, markers)) - 55) and not nearby_missing:
            continue
        marker = min(unused, key=lambda w: abs(middle(w) - middle(source)), default=None)
        if marker is not None and abs(middle(marker) - middle(source)) <= 30:
            unused.remove(marker)
            offsets.append(middle(marker) - middle(source))
        else:
            marker = None
        anchors.append({"source": source, "marker": marker,
                        "center": middle(marker) if marker else middle(source)})
    offset = median(offsets) if offsets else 0
    for anchor in anchors:
        if anchor["marker"] is None:
            anchor["center"] += offset
    anchors.extend({"source": None, "marker": marker, "center": middle(marker)} for marker in unused)
    anchors.sort(key=lambda a: a["center"])
    if not anchors:
        return []
    hint = (median((w["x0"] + w["x1"]) / 2 for w in markers) if markers else
            median((w["x0"] + w["x1"]) / 2 for w in headers) if headers else None)
    records = []
    for i, anchor in enumerate(anchors):
        center = anchor["center"]
        top = (anchors[i-1]["center"] + center) / 2 if i else max(0, center - 55)
        bottom = (center + anchors[i+1]["center"]) / 2 if i+1 < len(anchors) else min(page.height, center + 55)
        if headers:
            top = max(top, max(w["bottom"] for w in headers))
        band = [w for w in words if top <= middle(w) < bottom]
        source = anchor["source"]
        if source is None:
            candidates = [w for w in sources if w in band]
            if not candidates:
                raise UserError(f"i志愿第{number}页第{i+1}条记录的数据来源无法识别，请提供原始文字版明细")
            source = max(candidates, key=lambda w: w["x0"])
        durations = [w for w in band if is_duration(w["text"])
                     and w["x1"] <= source["x0"] + 1
                     and source["x0"] - w["x1"] < page.width * 0.16]
        if len(durations) != 1:
            raise UserError(f"i志愿第{number}页第{i+1}条记录的核定服务时长存在歧义")
        time_words = ([w for w in band if abs((w["x0"] + w["x1"]) / 2 - hint) < page.width * 0.065]
                      if hint is not None else [])
        begin, end = period("\n".join(w["text"] for w in sorted(time_words, key=lambda w: (w["top"], w["x0"]))),
                            f"i志愿第{number}页第{i+1}条记录")
        boundary = min((w["x0"] for w in time_words), default=hint - page.width * 0.065 if hint is not None else durations[0]["x0"])
        title_words = [w for w in band if w["x1"] < boundary - 2]
        title = "".join(w["text"] for w in sorted(title_words, key=lambda w: (round(w["top"], 1), w["x0"])))
        if not title:
            raise UserError(f"i志愿第{number}页第{i+1}条记录缺少活动名称")
        records.append(Activity(IV, title, begin, end, duration_minutes(durations[0]["text"]),
                                compact(source["text"]).replace("I志愿", "i志愿"), filename, number))
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
                    table_records, covered_markers = _iv_tables(page, filename, number)
                    # 有表格时也核对“至”的数量，防止某些行在表格提取中丢失。
                    marker_count = sum(compact(w["text"]) == "至" for w in page.extract_words())
                    if table_records and covered_markers >= marker_count:
                        records.extend(table_records)
                    else:
                        word_records = _iv_words(page, filename, number)
                        if word_records:
                            records.extend(word_records)
                        elif marker_count or not any(key in text for key in ("志愿者", "证件类型", "说明")):
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
    if platform == IV and any(not record.has_complete_dates for record in records):
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        records = [replace(record, record_id=f"undated:{digest}:{index}")
                   if not record.has_complete_dates else record
                   for index, record in enumerate(records, 1)]
    text = "\n".join(texts)
    pattern = r"姓名\s*[:：]?\s*([^\s:：]+)" if platform == SZ else r"志愿者\s*[:：]\s*([^\s:：]+)"
    names = {compact(m) for m in re.findall(pattern, text)}
    return ParsedPDF(records, names, [] if names else [f"{platform}PDF未提取到姓名，无法自动核对材料所属人"])
