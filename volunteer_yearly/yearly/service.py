from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from pathlib import Path
import tempfile

from .cosio import CosLease, CosStore, SummaryCSV, client_from_env
from .forms import normalized
from .mailer import Mailer
from .models import UserError, ServiceError, aggregate, SZ, IV
from .parsers import parse_pdf
from .reporting import email_bodies
from .tokens import TokenManager
from .wps import WPSDownloader

SHANGHAI = timezone(timedelta(hours=8))
logger = logging.getLogger("volunteer_yearly")


class Processor:
    def __init__(self, settings, store, token_store=None, downloader=None, mailer=None, clock=None):
        self.settings, self.store = settings, store
        self.clock = clock or (lambda: datetime.now(SHANGHAI))
        self.mailer = mailer or Mailer()
        self.downloader = downloader or WPSDownloader(TokenManager(token_store or store, settings), settings)

    @classmethod
    def for_request(cls, settings, headers):
        client = client_from_env(settings.cos_region, headers)
        store = CosStore(client, settings.cos_bucket)
        token_store = CosStore(client, settings.token_bucket or settings.cos_bucket)
        return cls(settings, store, token_store)

    def run(self, submission):
        cfg = self.settings
        # 四学年汇总单独记录状态，旧版失败答卷可以在新输出版本中重新处理。
        base = f"{cfg.cos_prefix}/events/{cfg.label}-summary/{submission.event_id}"
        lease = CosLease(self.store, base + "/job.jsonl", cfg.lease_seconds)
        if not lease.acquire():
            return {"status": "duplicate"}
        root = Path(cfg.temp_root or (Path(tempfile.gettempdir()) / "volunteer-yearly"))
        root.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix="job-", dir=root) as work:
                work = Path(work)
                manifest_key = base + "/prepared.json"
                manifest = self.store.json(manifest_key, 2 * 1024 * 1024)
                if manifest is None:
                    records, warnings, seen_files = [], [], set()
                    self.downloader.check_session()
                    for index, upload in enumerate(submission.uploads):
                        local = work / f"source-{index}.pdf"
                        self.downloader.download(upload, local)
                        digest = (upload.platform, hashlib.sha256(local.read_bytes()).hexdigest())
                        if digest in seen_files:
                            warnings.append(f"已忽略一份内容完全相同的{upload.platform}重复附件")
                            continue
                        seen_files.add(digest)
                        parsed = parse_pdf(local, upload.platform, cfg.max_pdf_pages, upload.filename)
                        if parsed.names and any(normalized(n) != normalized(submission.name) for n in parsed.names):
                            raise UserError(f"{upload.platform}PDF姓名与表单姓名不一致，请核对材料")
                        records.extend(parsed.activities)
                        warnings.extend(parsed.warnings)
                    uploaded_platforms = {u.platform for u in submission.uploads}
                    for platform in (SZ, IV):
                        if platform not in uploaded_platforms:
                            warnings.append(f"未上传{platform}PDF：该平台统计为0仅表示没有提供相应材料")
                    now = self.clock()
                    report = aggregate(submission, records, cfg.evaluation_year, now.date(), warnings)
                    plain, html = email_bodies(report)
                    row = [submission.name, submission.student_id, *report.evaluation_cells(),
                           submission.event_id, now.isoformat(timespec="seconds")]
                    manifest = {"event_id": submission.event_id, "student_id": submission.student_id,
                                "row": row, "plain": plain, "html": html}
                    # 先保存可恢复的个人结果；后续重试复用同一统计截止日和同一份结果。
                    self.store.put(manifest_key, json.dumps(manifest, ensure_ascii=False).encode(), "application/json")
                else:
                    if manifest.get("event_id") != submission.event_id or manifest.get("student_id") != submission.student_id:
                        raise ServiceError("已保存的任务与当前答卷不一致")
                lease.assert_owned()
                SummaryCSV(self.store, cfg.summary_key, cfg.evaluation_year, cfg.max_csv_bytes).append_once(
                    manifest["row"], submission.event_id)
                sent_key = base + "/sent.json"
                if self.store.json(sent_key) is None:
                    lease.assert_owned()
                    self.mailer.send(submission, f"{cfg.label}学年志愿服务统计结果",
                                     manifest["plain"], manifest["html"])
                    self.store.put(sent_key, b'{"smtp_accepted":true}', "application/json")
                lease.finish("done", "success")
                return {"status": "success"}
        except UserError as exc:
            logger.warning("material_validation_failed=%s", str(exc))
            # 材料错误可向填写者解释；修改材料后需提交新答卷，保留原申请历史。
            try:
                lease.assert_owned()
                self.mailer.failure(submission, str(exc))
                lease.finish("done", "invalid_material")
            except Exception:
                lease.finish("failed", "notification_failed")
                raise
            return {"status": "invalid_material"}
        except Exception:
            lease.finish("failed", "retryable_failure")
            raise
