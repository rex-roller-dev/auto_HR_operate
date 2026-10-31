from dataclasses import dataclass
from datetime import date
import os
import re
import tempfile
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    evaluation_year: int = 2025
    cos_bucket: str = ""
    cos_region: str = "ap-guangzhou"
    cos_prefix: str = "volunteer-yearly"
    token_bucket: str = ""
    token_key: str = "token/token.json"
    # 所有使用同一份 Token 的服务必须共用此锁路径。
    token_lock_key: str = "token/refresh-lock.jsonl"
    client_id: str = ""
    client_secret: str = ""
    bind_code: str = ""
    callback_secret: str = ""
    name_field: str = "姓名"
    student_field: str = "学号"
    email_field: str = "邮箱"
    shenzhen_field: str = "志愿深圳PDF"
    ivolunteer_field: str = "i志愿PDF"
    temp_root: str = ""
    max_pdf_bytes: int = 30 * 1024 * 1024
    max_pdf_pages: int = 150
    max_files: int = 8
    max_csv_bytes: int = 32 * 1024 * 1024
    lease_seconds: int = 1200

    @classmethod
    def from_env(cls):
        year = os.getenv("EVALUATION_SCHOOL_YEAR", "2025-2026").strip()
        match = re.fullmatch(r"(20\d{2})[-—–](20\d{2})(?:学年)?", year)
        if not match or int(match[2]) != int(match[1]) + 1:
            raise ValueError("EVALUATION_SCHOOL_YEAR 应为 2025-2026")
        bucket = os.getenv("COS_BUCKET", "").strip()
        return cls(
            evaluation_year=int(match[1]), cos_bucket=bucket,
            cos_region=os.getenv("COS_REGION", os.getenv("REGION", "ap-guangzhou")),
            cos_prefix=os.getenv("COS_PREFIX", "volunteer-yearly").strip("/"),
            token_bucket=os.getenv("TOKEN_COS_BUCKET", bucket),
            token_key=os.getenv("TOKEN_COS_KEY", "token/token.json"),
            token_lock_key=os.getenv("TOKEN_LOCK_KEY", "token/refresh-lock.jsonl"),
            client_id=os.getenv("WPS_CLIENT_ID", ""),
            client_secret=os.getenv("WPS_CLIENT_SECRET", ""),
            bind_code=os.getenv("WPS_BIND_CODE", ""),
            callback_secret=os.getenv("CALLBACK_SECRET", ""),
            name_field=os.getenv("FIELD_NAME", "姓名"),
            student_field=os.getenv("FIELD_STUDENT_ID", "学号"),
            email_field=os.getenv("FIELD_EMAIL", "邮箱"),
            shenzhen_field=os.getenv("FIELD_SHENZHEN", "志愿深圳PDF"),
            ivolunteer_field=os.getenv("FIELD_IVOLUNTEER", "i志愿PDF"),
            temp_root=os.getenv("TMP_ROOT", str(Path(tempfile.gettempdir()) / "volunteer-yearly")),
            max_pdf_bytes=int(os.getenv("MAX_PDF_BYTES", str(30 * 1024 * 1024))),
            max_pdf_pages=int(os.getenv("MAX_PDF_PAGES", "150")),
            max_files=int(os.getenv("MAX_FILES", "8")),
            max_csv_bytes=int(os.getenv("MAX_CSV_BYTES", str(32 * 1024 * 1024))),
        )

    @property
    def label(self):
        return f"{self.evaluation_year}-{self.evaluation_year + 1}"

    @property
    def evaluation_cutoff(self):
        return date(self.evaluation_year + 1, 8, 31)

    @property
    def summary_key(self):
        return f"{self.cos_prefix}/summaries/{self.label}-summary.csv"
