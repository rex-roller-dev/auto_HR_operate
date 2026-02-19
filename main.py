from datetime import datetime
import re
import shutil
import threading
from make_back_info import make_back_info
from send_email import send_failure_email, send_success_email
from task_queue import task_queue
# from download_file import download_file_from_wps
from listen_form_data import app, task_queue
from get_data_in_Certification_Form_text import parse_volunteer
from get_data_in_szvolunteer_text import parse_szvolunteer
from get_data_in_ivolunteer_file import parse_ivolunteer
from get_data_in_szuvolunteer_file import calc_hours_by_name_and_date, calc_hours_by_name_and_date_from_cos
from volunteer_hours_verify import volunteer_hours_verify
from write_back import write_verify_result
import sys
import io
from refresh_token import *
import time
import sys
from download_file_with_dive import download_file_from_wps_with_drive
import os
from ask_for_token import ask_for_token

# 打开日志文件（追加模式）
# log_file = open("log.txt", "a", encoding="utf-8")
# sys.stdout = log_file
# sys.stderr = log_file  # 同时把错误输出也重定向

# 确保输出使用 UTF-8 编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

downloads_dir = Path("downloads")

def worker():
    try:
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} 🚀 Worker 启动，等待任务...",flush=True)
        while True:
            data, request_id = task_queue.get()  # 阻塞等待
            print(f"📥 收到任务，请求 ID: {request_id}", flush=True)
            print(data,flush=True)
            
            # ✅ 新增判断：没有 answerContents 就认为是绑定
            if data.get("answerContents") is None:
                print(data.get("answerContents"))
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} ✅ 绑定成功，没有 answerContents", flush=True)
                continue  # 跳过本次循环，等待下一个任务

            # 从环境变量获取 code（如果未设置则为 None）
            code = os.environ.get("CODE")
            
            if code and len(code) > 80:
                print(f"📦 CODE 长度 {len(code)} > 80，正在获取 Token...")
                try:
                    ask_for_token(code)
                    print("✅ Token 已保存到 token.json")
                except Exception as e:
                    print(f"❌ 获取 Token 失败: {e}")
                    # 根据需求决定是否退出程序
                    # sys.exit(1)
            else:
                print(code)
                print("⏭️ CODE 不存在或长度 ≤ 80，跳过 Token 获取步骤")

            err = None
            try:
                print("🛠 开始处理任务",flush=True)
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
                        # 去掉括号和数字
                        name_without_brackets = re.sub(r"\(\d+\)", "", file["fileName"])
                        # 去掉后缀
                        base_name = Path(name_without_brackets).stem
                        base_name = base_name.strip()  # 去掉前后空格
                        print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} ⬇️ 正在下载文件：{file['fileName']}", flush=True)
                        file_add = download_file_from_wps_with_drive(
                            file_id = file["link"].split("/")[-1],  
                            filename = file["fileName"]
                        )
                        file["local_path"] = file_add

                # 2. 校验时间
                form_data = parse_volunteer(file_links[0]["local_path"])
                if form_data["start_date"] is None or form_data["end_date"] is None:
                    raise ValueError("开始日期或结束日期格式错误")
                start_date = datetime.strptime(form_data["start_date"], "%Y-%m-%d").date()
                end_date = datetime.strptime(form_data["end_date"], "%Y-%m-%d").date()
                if start_date > end_date:
                    raise ValueError("开始日期不能晚于结束日期")

                if len(file_links) > 1 and file_links[1]["link"]:
                    sz_data = parse_szvolunteer(file_links[1]["local_path"])
                if len(file_links) > 2 and file_links[2]["link"]: 
                    ivolunteer_hours = parse_ivolunteer(
                        file_links[2]["local_path"],
                        finalyear=end_date.year,
                        base_year=start_date.year,
                        base_month=start_date.month,
                        base_date=start_date.day,
                        finalmonth=end_date.month,
                        finalday=end_date.day
                    )
                if len(data["answerContents"][-2]["value"]) >= 1 and data["answerContents"][-2]["value"][0] == "需要深大义工":
                    # 从环境变量获取 COS 配置
                    COS_BUCKET = os.environ.get('COS_BUCKET')
                    COS_KEY = "2014-2021（完整版） .csv"  # 根据你在 COS 中的实际路径修改
                    szu_hours = calc_hours_by_name_and_date_from_cos(
                        bucket_name=COS_BUCKET,
                        cos_key=COS_KEY,
                        name=form_data["name"],
                        start_date=form_data["start_date"],
                        end_date=form_data["end_date"]
                    )
                            
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} 📊 解析结果：", flush=True)
                print("表格数据：", form_data, flush=True)
                if len(file_links) > 1 and file_links[1]["link"]:
                    print("志愿深圳数据：", sz_data, flush=True)
                if len(file_links) > 2 and file_links[2]["link"]:
                    print("i志愿总时长：", ivolunteer_hours, flush=True)
                if len(data["answerContents"][-3]["value"]) >= 1 and data["answerContents"][-3]["value"][0] == "需要深大义工":
                    print("深大义工总时长：", szu_hours, flush=True)

                volunteer_hours_verify(
                    certificate_data = form_data,
                    sz_volunteer_data = sz_data if len(file_links) > 1 and file_links[1]["link"] else None,
                    ivolunteer_hours = ivolunteer_hours if len(file_links) > 2 and file_links[2]["link"] else None,
                    szu_volunteer_hours = szu_hours if len(data["answerContents"][-3]["value"]) >= 1 and data["answerContents"][-3]["value"][0] == "需要深大义工" else None,
                    contain_ivolunteer = len(file_links) > 2 and file_links[2]["link"] is not None,
                    contain_szu_volunteer = len(data["answerContents"][-3]["value"]) >= 1 and data["answerContents"][-3]["value"][0] == "需要深大义工"
                )
                
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} ✅ 时间校验通过", flush=True)

            except Exception as e:
                err = e
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} ❌ 任务失败:", e, flush=True)
            finally:
                try:
                    # 3. 准备回写内容
                    back_info = make_back_info(exception=err,
                                            src_docx=file_links[0]["local_path"],
                                            image_path=r"章.png",
                                            szu_hours=szu_hours if len(data["answerContents"][-3]["value"]) >= 1 and data["answerContents"][-3]["value"][0] == "需要深大义工" else 0,
                                            i_volunteer_hours=ivolunteer_hours if len(file_links) > 2 and file_links[2]["link"] else 0)
                    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} 📝 回写内容准备完毕: {back_info}", flush=True)
                except Exception as e:
                    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} ❌ 回写内容准备失败:", e, flush=True)

                try:
                    # 4. 回写
                    write_situation = write_verify_result(
                        form_data=data,
                        exception=err if err else None,
                        access_token = access_token
                    )
                    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} 📝 回写结果：{write_situation}", flush=True)
                except Exception as e:
                    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} ❌ 回写失败:", e, flush=True)

                # 5. 发送邮件
                try:
                    if err:
                        send_failure_email(
                            to_email=data["answerContents"][8]["value"],
                            name=data["answerContents"][0]["value"],
                            exception=err
                        )
                        print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} 📧 失败邮件已发送", flush=True)
                    else:
                        send_success_email(
                            to_email=data["answerContents"][8]["value"],
                            name=data["answerContents"][0]["value"],
                        )
                        print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} 📧 成功邮件已发送", flush=True)
                except Exception as e:
                    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} ❌ 发送邮件失败:", e, flush=True)

                try:
                    # 清理下载的文件
                    if downloads_dir.exists() and downloads_dir.is_dir():
                        shutil.rmtree(downloads_dir)
                    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} 🧹 下载文件已清理", flush=True)
                except Exception as e:
                    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} ❌ 清理下载文件失败:", e, flush=True)

            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} 🚀 任务处理完毕，等待下一个任务...", flush=True)
            task_queue.task_done()
    except Exception as e:
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} ❌ Worker 发生异常:", e, flush=True)

if __name__ == "__main__":
    t = threading.Thread(target=worker, daemon=True)
    t.start()

    app.run(host="0.0.0.0", port=9000)