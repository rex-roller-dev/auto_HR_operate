from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import re

SZ = "志愿深圳"
IV = "i志愿"


class UserError(ValueError):
    """可直接向申请人说明的材料错误。"""


class ServiceError(RuntimeError):
    """仅包含已脱敏的运行错误。"""


def school_year(day: date) -> int:
    return day.year if day.month >= 9 else day.year - 1


def year_label(year: int) -> str:
    return f"{year}-{year + 1}"


def hours_text(minutes: Decimal) -> str:
    return str((minutes / 60).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def enrollment_year(student_id: str) -> int:
    """研究生学号以xx00开头，本科生学号以四位入学年份开头。"""
    if not re.fullmatch(r"[0-9]{6,20}", student_id):
        raise UserError("学号应为6至20位纯数字；本科生以四位入学年份开头，研究生以两位年份加00开头")
    if student_id[2:4] == "00":
        return 2000 + int(student_id[:2])
    if not student_id.startswith("20"):
        raise UserError("学号格式无效：本科生以四位入学年份开头，研究生以两位年份加00开头")
    return int(student_id[:4])


@dataclass(frozen=True)
class Upload:
    platform: str
    filename: str
    file_id: str


@dataclass(frozen=True)
class Submission:
    event_id: str
    aid: str
    name: str
    student_id: str
    email: str
    uploads: tuple[Upload, ...]

    @property
    def enrollment(self):
        return enrollment_year(self.student_id)


@dataclass(frozen=True)
class Activity:
    platform: str
    title: str
    begin: datetime | None
    end: datetime | None
    minutes: Decimal
    source: str
    filename: str
    page: int
    record_id: str = ""
    kind: str = "服务时长"

    @property
    def has_complete_dates(self):
        return self.begin is not None and self.end is not None

    @property
    def year(self):
        return school_year(self.end.date()) if self.has_complete_dates else None

    @property
    def identity(self):
        if self.platform == SZ and self.record_id:
            return (self.platform, self.record_id)
        if not self.has_complete_dates and self.record_id:
            return (self.platform, self.record_id)
        return (
            self.platform, re.sub(r"\s+", "", self.title),
            self.begin, self.end, self.minutes, self.source, self.kind,
        )


@dataclass
class ParsedPDF:
    activities: list[Activity]
    names: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)


@dataclass
class Detail:
    activity: Activity
    reason: str = ""

    @property
    def counted(self):
        return not self.reason


@dataclass
class YearTotal:
    year: int
    shenzhen: Decimal = Decimal(0)
    ivolunteer: Decimal = Decimal(0)

    @property
    def total(self):
        return self.shenzhen + self.ivolunteer


@dataclass
class Report:
    submission: Submission
    evaluation_year: int
    as_of: date
    totals: dict[int, YearTotal]
    details: list[Detail]
    warnings: list[str]
    material_minutes: Decimal = Decimal(0)
    undated_minutes: Decimal = Decimal(0)
    undated_count: int = 0

    @property
    def enrollment_years(self):
        return range(self.evaluation_year, self.submission.enrollment - 1, -1)

    @property
    def material_hours(self):
        return hours_text(self.material_minutes)

    @property
    def undated_hours(self):
        return hours_text(self.undated_minutes)

    def year_cells(self, years):
        return [
            "未入学" if year < self.submission.enrollment
            else hours_text(self.totals.get(year, YearTotal(year)).total)
            for year in years
        ]

    def evaluation_cells(self):
        return self.year_cells(self.enrollment_years)


def aggregate(submission, activities, evaluation_year, as_of, warnings=None):
    totals = {
        y: YearTotal(y)
        for y in range(submission.enrollment, school_year(as_of) + 1)
    }
    details = []
    seen = {}
    material_minutes = Decimal(0)
    undated_minutes = Decimal(0)
    undated_count = 0
    for activity in activities:
        reason = ""
        if activity.minutes < 0 or not activity.minutes.is_finite() or (
            activity.has_complete_dates and activity.end < activity.begin
        ):
            raise UserError("PDF存在日期或核定时长无效的活动记录")
        previous = seen.get(activity.identity)
        if previous:
            # 考勤编号相同却内容不同，不能擅自决定采用哪一份。
            if previous != (activity.begin, activity.end, activity.minutes, activity.kind):
                raise UserError("重复考勤编号的日期或时长不一致，请检查多份附件")
            reason = "重复记录"
        else:
            seen[activity.identity] = (activity.begin, activity.end, activity.minutes, activity.kind)
        if not reason and activity.platform == IV and "志愿深圳" in re.sub(r"\s+", "", activity.source):
            reason = "i志愿来源为志愿深圳，按规则排除"
        if not reason and activity.kind == "培训时长":
            reason = "培训时长不计入服务时长"
        if not reason and any(day.date() > as_of for day in (activity.begin, activity.end) if day is not None):
            reason = "活动结束日期晚于统计截止日"
        if not reason:
            material_minutes += activity.minutes
        if not reason and not activity.has_complete_dates:
            undated_minutes += activity.minutes
            undated_count += 1
            reason = "活动日期缺失或不完整，仅计入材料总时长"
        if not reason and activity.year < submission.enrollment:
            reason = "未入学"
        details.append(Detail(activity, reason))
        if not reason:
            total = totals.setdefault(activity.year, YearTotal(activity.year))
            if activity.platform == SZ:
                total.shenzhen += activity.minutes
            else:
                total.ivolunteer += activity.minutes
    notes = list(warnings or [])
    if undated_count:
        notes.append(
            f"您有 {hours_text(undated_minutes)} 小时志愿服务记录（{undated_count}条）缺少完整活动日期，"
            f"已计入材料总时长，未计入任何学年的时长统计；这部分记录无法核验是否在 {as_of.isoformat()} 截止前发生。"
        )
    return Report(submission, evaluation_year, as_of, totals, details, notes,
                  material_minutes, undated_minutes, undated_count)
