from email.message import EmailMessage
from email.utils import formataddr, formatdate
import os
from pathlib import Path
import smtplib
import ssl

from .models import ServiceError


class Mailer:
    def send(self, submission, subject, plain, html=None, attachment=None):
        host = os.getenv("SMTP_SERVER", "")
        port = int(os.getenv("SMTP_PORT", "465"))
        name = os.getenv("SENDER_NAME", "志愿服务学年统计")
        accounts = [(os.getenv("SENDER_EMAIL"), os.getenv("SENDER_PASSWORD")),
                    (os.getenv("AUTO_HR_BACKUP_SENDER_EMAIL"), os.getenv("AUTO_HR_BACKUP_SENDER_PASSWORD"))]
        if not host or not accounts[0][0] or not accounts[0][1]:
            raise ServiceError("发件邮箱配置不完整")
        for index, (sender, password) in enumerate(accounts):
            if not sender or not password:
                continue
            msg = EmailMessage()
            msg["From"] = formataddr((name, sender))
            msg["To"] = formataddr((submission.name, submission.email))
            msg["Subject"] = subject
            msg["Date"] = formatdate(localtime=False)
            msg["Message-ID"] = f"<volunteer-{submission.event_id}-{'report' if attachment else 'notice'}@{sender.split('@')[-1]}>"
            msg.set_content(plain)
            if html:
                msg.add_alternative(html, subtype="html")
            if attachment:
                path = Path(attachment)
                msg.add_attachment(path.read_bytes(), maintype="application",
                                   subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=path.name)
            server = None
            accepted = False
            try:
                mode = os.getenv("SMTP_SECURITY", "ssl").lower()
                if mode == "ssl":
                    server = smtplib.SMTP_SSL(host, port, timeout=25, context=ssl.create_default_context())
                elif mode == "starttls":
                    server = smtplib.SMTP(host, port, timeout=25)
                    server.starttls(context=ssl.create_default_context())
                else:
                    raise ServiceError("SMTP_SECURITY仅支持ssl或starttls")
                server.login(sender, password)
                refused = server.send_message(msg)
                if refused:
                    raise smtplib.SMTPRecipientsRefused(refused)
                accepted = True
                return
            except smtplib.SMTPRecipientsRefused:
                raise ServiceError("收件邮箱被服务器拒绝，请检查填写地址") from None
            except (smtplib.SMTPException, OSError):
                if index == 1 or not accounts[1][0] or not accounts[1][1]:
                    raise ServiceError("邮件发送未获确认，请管理员查看发件服务状态") from None
            finally:
                if server is not None:
                    try:
                        server.quit()
                    except Exception:
                        server.close()
                    # SMTP已接受的邮件，不因QUIT失败重复发送。
        if not accepted:
            raise ServiceError("没有可用的发件账号")

    def failure(self, submission, message):
        self.send(submission, "志愿服务学年统计：材料需要修改",
                  f"{submission.name} 同学，您好：\n\n本次材料未能完成统计：\n{message}\n\n请修改后重新提交一份表单。")
