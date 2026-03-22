import smtplib
from pathlib import Path
from email.message import EmailMessage
from email.header import Header
from email.utils import formataddr
from email import encoders
from email.mime.base import MIMEBase
from email.header import Header
from email.utils import formataddr
from exceptions import (
    VolunteerVerifyError,
    NameMismatchError,
    szvHourMismatchError,
    ivolHourMismatchError,
    szuHourMismatchError,
    FileError,
    timeValueError)


from email_config import (
    SMTP_SERVER,
    SMTP_PORT,
    SENDER_EMAIL,
    SENDER_PASSWORD,
    SENDER_NAME
)

def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    body: str,
    attachments: list[str] | None = None
) -> None:

    msg = EmailMessage()

    # 发件人 / 收件人 / 主题（直接传字符串）
    msg["From"] = formataddr((SENDER_NAME, SENDER_EMAIL))
    msg["To"] = formataddr((to_name, to_email))
    msg["Subject"] = subject   # ✅ 不再用 Header()

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
您可以自行打印并使用该证明文件进行相关申请或提交。

如您不知道提交到哪里，请咨询要求您提交本文件的"相关部门"或"辅导员"

如有疑问，请及时联系。
"""

    send_email(
        to_email=to_email,
        to_name=name,
        subject=subject,
        body=body,
        attachments=[str(stamped_pdf)]
    )

def send_failure_email(to_email: str, name: str, exception: Exception, request_id: str = None):
    """
    发送志愿服务时长审核失败邮件，包含失败原因。

    :param to_email: 收件人邮箱
    :param name: 收件人姓名
    :param exception: 审核失败或异常信息对象
    """
    subject = "志愿服务时长审核异常通知"
    
    # 将异常信息转换为字符串，方便邮件显示
    error_msg = str(exception) if exception else "未知错误"
    Related_information = None
    if isinstance(exception, NameMismatchError):
        Related_information = "请您检查您的志愿时长认证表，志愿深圳或i志愿上的姓名是否都一致，如果不一致，请您修改后再提交审核"
    elif isinstance(exception, szvHourMismatchError):
        Related_information = "请您检查您的志愿时长认证表，志愿深圳的服务时长是否正确，仅包括服务时长，请您仔细阅读公众号推文 https://mp.weixin.qq.com/s/4ottRxNg-5l1jSSZ2FLmHg 以及表单上方的提示后准备材料后提交"
    elif isinstance(exception, ivolHourMismatchError):
        Related_information = "请您检查您的志愿时长认证表，i志愿上的服务时长是否正确，注意：请您在您的申请日期内剔除“志愿深圳”部分进行计算，那部分在志愿深圳中已经计算过，请您仔细阅读公众号推文 https://mp.weixin.qq.com/s/4ottRxNg-5l1jSSZ2FLmHg 以及表单上方的提示后准备材料后提交"
    elif isinstance(exception, szuHourMismatchError):
        Related_information = "请您检查您的志愿时长认证表，深大义工的申请请您在表单后勾选相关的选项后填写您的学号，我们会为您查找并写上您的时长，深大义工系统于2021年已停用，22级及以后入学的同学请忽略“深大义工”部分义工时！，请您仔细阅读公众号推文 https://mp.weixin.qq.com/s/4ottRxNg-5l1jSSZ2FLmHg 以及表单上方的提示后准备材料后提交"
    elif isinstance(exception, FileError):
         Related_information = "请您修改您的志愿时长认证表的文件类型，我们使用.docx格式作为标准的格式，志愿深圳和i志愿统一使用.pdf文件作为标准的格式，请您仔细阅读公众号推文 https://mp.weixin.qq.com/s/4ottRxNg-5l1jSSZ2FLmHg 以及表单上方的提示后准备材料后提交"
    elif isinstance(exception, timeValueError):
        Related_information = "请您检查您的志愿时长认证表，开始日期或结束日期的格式是否正确，标准格式为 xxxx 年 x 月 xx 日至  xxxx  年 x 月 xx 日，请您仔细阅读您的认证表，此处不应多字少字，另：请您仔细阅读公众号推文 https://mp.weixin.qq.com/s/4ottRxNg-5l1jSSZ2FLmHg 以及表单上方的提示后准备材料后提交"

    body = f"""
{name} 同学，您好：

您的志愿服务时长审核未通过，出现以下异常情况：

{error_msg}, 请求 ID: {request_id}。

重要提示：{Related_information if Related_information else ""}


请核查提交信息或联系相关工作人员处理。
"""
    
    send_email(
        to_email=to_email,
        to_name=name,
        subject=subject,
        body=body,
        attachments=[]  # 失败邮件一般不附文件
    )


if __name__ == "__main__":
    # 测试函数（可选，验证配置是否正确）
    if __name__ == "__main__":
        try:
            # 发送测试邮件到自己的邮箱
            send_email(
                to_email="2039179148@qq.com",  # 填你能接收的邮箱
                to_name="测试用户",
                subject="网易邮箱切换测试",
                body="这是测试邮件，说明网易邮箱配置成功！"
            )
            print("邮件发送成功！")
        except Exception as e:
            print(f"发送失败：{e}")