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
    FileError)


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
    data = {
"rid":"4qAUgDcoUY",
"formId":"20260123201242397174053",
"formTitle":"志愿时认证表审核申请（粤海校区）-2025—2026",
"aid":"20260129221947070747904",
"eventTs":1769696387000,
"messageTs":1769696523619,
"creatorId":"1794481838",
"creatorName":"admin",
"event":"create_answer",
"version":2,
"answerContents":[
{
"qid":"j4jodj",
"type":"input",
"title":"请输入姓名",
"value":"王佳豪"
},
{
"qid":"aiecak",
"type":"select",
"title":"请选择性别",
"value":[
"男"
]
},
{
"qid":"mb9vz5",
"type":"select",
"title":"您所在的校区",
"value":[
"粤海"
]
},
{
"qid":"m97otm",
"type":"input",
"title":"学号",
"value":"2300474002"
},
{
"qid":"8884so",
"type":"input",
"title":"学院",
"value":"土木与交通工程学院"
},
{
"qid":"egxtog",
"type":"input",
"title":"电子义工证注册号/义工证号",
"value":"0099234732"
},
{
"qid":"5fbh5l",
"type":"input",
"title":"请输入身份证号",
"value":"441522200002201012"
},
{
"qid":"pyci44",
"type":"input",
"title":"请输入联系方式",
"value":"13428216169"
},
{
"qid":"z5nkcu",
"type":"email",
"title":"电子邮箱",
"value":"2039179148@qq.com"
},
{
"qid":"93aewv",
"type":"input",
"title":"用途",
"value":"入党"
},
{
"qid":"vk7i5f",
"type":"select",
"title":"2024-2025学年是否有挂科记录",
"value":[
"否"
]
},
{
"qid":"uljvc0",
"type":"input",
"title":"是否重复申请",
"value":"无"
},
{
"qid":"shjlog",
"type":"select",
"title":"审核方式",
"value":[
"线下审核"
]
},
{
"qid":"wywm2a",
"type":"input",
"title":"备注",
"value":"测试"
},
{
"qid":"k6xep1",
"type":"file",
"title":"深圳大学志愿时认证表Word",
"value":[
{
"fileName":"深圳大学志愿时认证表(42).docx",
"fileShareLink":"https://www.kdocs.cn/l/cfN6wZ3wtlAL",
"fileId":"490798112754",
"fileSid":"cfN6wZ3wtlAL",
"ext":"docx"
}
]
},
{
"qid":"p2zrq9",
"type":"file",
"title":"广东省内志愿时服务证明（佐证材料）--志愿深圳部分",
"value":[
{
"fileName":"志愿深圳-王佳豪.pdf",
"fileShareLink":"https://www.kdocs.cn/l/ccLOxraJ3ZzG",
"fileId":"490801341848",
"fileSid":"ccLOxraJ3ZzG",
"ext":"pdf"
}
]
},
{
"qid":"tjbcap",
"type":"file",
"title":"广东省内志愿时服务证明（佐证材料）--i志愿部分",
"value":[
{
"fileName":"i志愿-王佳豪.pdf",
"fileShareLink":"https://www.kdocs.cn/l/caW59esJzbv9",
"fileId":"490799665151",
"fileSid":"caW59esJzbv9",
"ext":"pdf"
}
]
},
{
"qid":"lusa9s",
"type":"select",
"title":"广东省内志愿时--深大义工部分",
"value":[
"需要深大义工"
]
},
{
"qid":"swxlpy",
"type":"multiStepInput",
"title":"本科和研究生都是深大的同学请注意️",
"value":[
"2019093042"
]
},
{
"qid":"yfyzzw",
"type":"file",
"title":"附件二--补充佐证材料（相同无需重复上传）",
"value":[]
}
]
}
    send_success_email(
    to_email=data["answerContents"][8]["value"],
    name=data["answerContents"][0]["value"],
)