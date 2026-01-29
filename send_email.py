import smtplib
from pathlib import Path
from email.message import EmailMessage
from email.header import Header
from email.utils import formataddr
from email import encoders
from email.mime.base import MIMEBase

from email_config import (
    SMTP_SERVER,
    SMTP_PORT,
    SENDER_EMAIL,
    SENDER_PASSWORD,
    SENDER_NAME
)

def send_email(
    to_email: str,
    subject: str,
    body: str,
    attachments: list[str] | None = None
) -> None:

    msg = EmailMessage()

    # 发件人 / 收件人 / 主题
    msg["From"] = formataddr((SENDER_NAME, SENDER_EMAIL))
    msg["To"] = to_email
    msg["Subject"] = subject   # ✅ 关键修复点

    # 正文
    msg.set_content(body, charset="utf-8")

    # 附件
    if attachments:
        for file_path in attachments:
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"附件不存在: {path}")

            with open(path, "rb") as f:
                file_data = f.read()

            msg.add_attachment(
                file_data,
                maintype="application",
                subtype="pdf",
                filename=path.name
            )

    # 发送
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)


def find_stamped_pdf(download_dir: str = "downloads") -> Path:
    download_dir = Path(download_dir)
    """
    在 Downloads 目录中查找文件名以「已盖章.pdf」结尾的文件
    返回最新修改的那一个
    """

    pdf_files = [
        f for f in download_dir.iterdir()
        if f.is_file() and f.name.endswith("已盖章.pdf")
    ]

    if not pdf_files:
        raise FileNotFoundError("未在 Downloads 目录中找到已盖章的 PDF 文件")

    # 按修改时间排序，取最新的
    pdf_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    return pdf_files[0]


def send_success_email(to_email: str, name: str):
    stamped_pdf = find_stamped_pdf()

    subject = "志愿服务时长证明（已盖章）"
    body = f"""
{name} 同学，您好：

您的志愿服务时长信息已核验通过，
附件为已加盖公章的志愿服务证明文件，请查收。

如有疑问，请及时联系。
"""

    send_email(
        to_email=to_email,
        subject=subject,
        body=body,
        attachments=[str(stamped_pdf)]
    )

if __name__ == "__main__":
    send_success_email(
        to_email="2039179148@qq.com",
        name="测试用户")