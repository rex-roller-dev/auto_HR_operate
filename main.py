from datetime import datetime
import threading
from make_back_info import make_back_info
from send_email import send_failure_email, send_success_email
from task_queue import task_queue
from download_file import download_file_from_wps
from listen_form_data import app, task_queue
from get_data_in_Certification_Form_text import parse_volunteer
from get_data_in_szvolunteer_text import parse_szvolunteer
from get_data_in_ivolunteer_file import parse_ivolunteer
from get_data_in_szuvolunteer_file import calc_hours_by_name_and_date
from volunteer_hours_verify import volunteer_hours_verify
from write_back import write_verify_result
import sys
import io
from get_code import *

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def worker():
    print("🚀 Worker 启动，等待任务...")
    while True:
        data = task_queue.get()  # 阻塞等待
        err = None
        try:
            print("🛠 开始处理任务")
            # 0.刷新token
            access_token, refresh_token = get_access_token()

            # 1. 下载文件
            file_links = []
            for item in data["answerContents"]:
                if item["type"] == "file":
                    for f in item["value"]:
                        if item["value"] is not []:#防止没有上传文件时报错
                            file_links.append({
                                "title": item["title"],
                                "fileName": f["fileName"],
                                "link": f["fileShareLink"]
                            })
                        else:
                            file_links.append({
                                "title": item["title"],
                                "fileName": None,
                                "link": None
                            })
            for file in file_links:
                if file["link"]:
                    print(f"⬇️ 正在下载文件：{file['fileName']}")
                    file_add = download_file_from_wps(
                        url=file["link"],
                        expected_name=file["fileName"],
                        ext="." + file["fileName"].split(".")[-1]
                    )
                    file["local_path"] = file_add

            # 2. 校验时间
            form_data = parse_volunteer(file_links[0]["local_path"])
            start_date = datetime.strptime(form_data["start_date"], "%Y-%m-%d").date()
            end_date = datetime.strptime(form_data["end_date"], "%Y-%m-%d").date()

            if file_links[1]["link"]:
                sz_data = parse_szvolunteer(file_links[1]["local_path"])
            if file_links[2]["link"]:
                ivolunteer_hours = parse_ivolunteer(
                    file_links[2]["local_path"],
                    finalyear=end_date.year,
                    base_year=start_date.year,
                    base_month=start_date.month,
                    base_date=start_date.day,
                    finalmonth=end_date.month,
                    finalday=end_date.day
                )
            if data["answerContents"][-3]["value"][0] == "需要深大义工":
                szu_hours = calc_hours_by_name_and_date(
                    file_path=r"D:\D\file\auto_HR_operate\szu_volunteer_data\2014-2021（完整版） .csv",
                    name=form_data["name"],
                    start_date=form_data["start_date"],
                    end_date=form_data["end_date"]
                )
            
            print("📊 解析结果：")
            print("表格数据：", form_data)
            if file_links[1]["link"]:
                print("志愿深圳数据：", sz_data)
            if file_links[2]["link"]:
                print("i志愿总时长：", ivolunteer_hours)
            if data["answerContents"][-3]["value"][0] == "需要深大义工":
                print("深大义工总时长：", szu_hours)

            volunteer_hours_verify(
                certificate_data = form_data,
                sz_volunteer_data = sz_data if file_links[1]["link"] else None,
                ivolunteer_hours = ivolunteer_hours if file_links[2]["link"] else None,
                szu_volunteer_hours = szu_hours if data["answerContents"][-3]["value"][0] == "需要深大义工" else None,
                contain_ivolunteer = file_links[2]["link"] is not None,
                contain_szu_volunteer = data["answerContents"][-3]["value"][0] == "需要深大义工"
            )
            
            print("✅ 时间校验通过")

        except Exception as e:
            err = e
            print("❌ 任务失败:", e)

        finally:
            try:
                # 3. 准备回写内容
                back_info = make_back_info(exception=err,
                                        src_docx=file_links[0]["local_path"],
                                        image_path=r"章.png",szu_hours=szu_hours if data["answerContents"][-3]["value"][0] == "需要深大义工" else 0)
                print(f"📝 回写内容准备完毕:{back_info}")
            except Exception as e:
                print("❌ 回写内容准备失败:", e)

            try:
                # 4. 回写
                write_situation = write_verify_result(
                    form_data=data,
                    exception=err if err else None,
                    access_token = access_token
                )
                print("📝 回写结果：", write_situation)
            except Exception as e:
                print("❌ 回写失败:", e)

            # 5. 发送邮件
            try:
                if err:
                    send_failure_email(
                        to_email=data["answerContents"][8]["value"],
                        name=data["answerContents"][0]["value"],
                        exception=err
                    )
                    print("📧 失败邮件已发送")
                else:
                    send_success_email(
                        to_email=data["answerContents"][8]["value"],
                        name=data["answerContents"][0]["value"],
                    )
                    print("📧 成功邮件已发送")
            except Exception as e:
                print("❌ 发送邮件失败:", e)

        print("🚀 任务处理完毕，等待下一个任务...")
        task_queue.task_done()

if __name__ == "__main__":
    t = threading.Thread(target=worker, daemon=True)
    t.start()

    app.run(host="0.0.0.0", port=8000)