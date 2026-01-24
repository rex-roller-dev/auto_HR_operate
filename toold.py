#不保证正确，只能说是一个辅助工具.
import tkinter as tk
from tkinter import filedialog,messagebox
import re
import pdfplumber
from datetime import datetime


def pdfclean(pos, page):
    """
    读取 PDF 指定页，返回按空格和换行分割的字符串列表

    :param pos: PDF 文件路径
    :param page: 页码
    """
    with pdfplumber.open(pos) as pdf:
        current_page = pdf.pages[page]
        text = current_page.extract_text()
        datalist = re.split(r'[ \n]+', text)
        #print(datalist)
        return datalist

def is_valid_time_format(data):
    """
    判断是否是合法的时间格式：
    - 1小时 / 2小时30分钟 / 3时40分 / 25分钟 / 5分 / 48分
    """
    return bool(
        re.match(r"^\d+(小时|时)(\d+(分钟|分))?$", data)  # **匹配 "X小时Y分钟" / "X时Y分"**
        or re.match(r"^\d+(小时|时)$", data)              # **匹配 "X小时" / "X时"**
        or re.match(r"^\d+(分钟|分)$", data)              # **匹配 "X分钟" / "X分"（解决 48分 被删）**
    )


def clean_shortlist(shortlist):
    """
    按每 4 个元素为一组，删除其中的第 4 个（即 '结束时间' 字段）
    :param shortlist: 待处理的字符串列表
    :return: 处理后的字符串列表
    """
    cleaned_list = []

    for i in range(0, len(shortlist), 4):
        if i + 3 < len(shortlist):
            cleaned_list.extend(shortlist[i:i + 3])  # 只保留前 3 个（时间、时长、组织）
        else:
            cleaned_list.extend(shortlist[i:])  # 最后一组不够 4 个就全保留

    return cleaned_list


def dataclean(datalist):
    """
    清洗数据，筛选出有效的时间、时长、志愿组织等信息
    
    :param datalist: 待处理的字符串列表
    :return: 处理后的字符串列表，每 3 个元素为一组（时间、时长、组织）
    """
    shortlist =[]
    shortlist1=[]
    for data in datalist:
        if ("小时" in data or "分钟" in data or "i志愿" in data or "志愿深圳" in data or '志愿中山' in data or "江门义工" in data or
                re.match(r"\d{4}\.\d{2}\.\d{2}", data) or "时" in data or "分" in data):
            shortlist.append(data)
    shortlist = [data for data in shortlist if not (data != "i志愿" and "i志愿" in data)]
    #删除可能存在的i志愿关键字
    # print(shortlist)
    shortlist = [data for data in shortlist if is_valid_time_format(data) or
                 ("时" not in data and "分" not in data)]
    #删除可能存在的的时间关键字
    #print(shortlist)
    shortlist = [data for data in shortlist if not (
            (match := re.match(r"\d{4}\.\d{2}\.\d{2}", data)) and data != match.group()
    )]  # 删除名称中可能存在的年份时间关键字
    shortlist = clean_shortlist(shortlist)
    #读取到的数据有问题，是“开始时间”“服务时长”“志愿组织”“结束时间”，pop掉最后一个结束时间
    #print(shortlist) #测试

    for num in range(len(shortlist)-1,-1,-3):
        if "志愿深圳" in shortlist[num]:
            if "小时" in shortlist[num-1] or "分钟" in shortlist[num-1] or "时" in shortlist[num-1] :
                shortlist.pop(num)
                shortlist.pop(num-1)
                shortlist.pop(num-2)#删掉志愿深圳的数据

    for i in range(0, len(shortlist), 3):  # 每 3 个元素一组
        if i + 2 < len(shortlist):  # 确保不会超出索引范围
            shortlist1.append((shortlist[i], shortlist[i + 1], shortlist[i + 2]))   # 变成元组，契合后面ai写的代码。
    #print(shortlist) #测试
    return shortlist1


def is_valid_date(date_str, base_year,base_month,base_date,finalyear,finalmonth,finalday):
    """
    is_valid_date 的 Docstring
    说明：检查给定的日期字符串是否在指定的基准日期范围内。
    
    :param date_str: 日期字符串，格式为 'YYYY.MM.DD'
    :param base_year: 基准年份
    :param base_month: 基准月份
    :param base_date: 基准日期
    :param finalyear: 最终年份
    :param finalmonth: 最终月份
    :param finalday: 最终日期
    """
    try:
        if not date_str or not re.match(r"\d{4}\.\d{2}\.\d{2}", date_str):
            return False
        # 解析日期格式：2021.09.01
        date = datetime.strptime(date_str, "%Y.%m.%d")
        # 对比基准日期
        base_date = datetime(base_year,base_month, base_date)
        final_date = datetime(finalyear,finalmonth,finalday)
        return base_date <= date <= final_date
    except ValueError:
        return False


def sum_data(shortlist, base_year,base_month,base_date,finalyear,finalmonth,finalday):
    total_minutes = 0
    hours=0
    minutes=0
    for item in shortlist:
        if len(item) != 3:
            continue

        time_range, duration, source = item


        # 解析开始日期
        start_date = time_range.strip()

        # 筛选条件2：日期检查
        if not is_valid_date(start_date, base_year,base_month,base_date,finalyear,finalmonth,finalday):
            continue
    #如果时间大于base小于final就把他算进去
        hours = 0
        minutes = 0
        # 解析时长
        time_match = re.match(r"(\d+)(小时|时)(\d+)(分钟|分)", duration)

        if time_match:
            hours = int(time_match.group(1))
            if time_match.group(3):
                minutes = int(time_match.group(3)) if time_match.group(3) else 0

        else:
            time_match=re.match(r"(\d+)(小时|时)",duration)
            if time_match:
                hours = int(time_match.group(1))

            else:
                time_match=re.match(r"(\d+)(分钟|分)?",duration)
                if time_match:
                    minutes = int(time_match.group(1))

        total_minutes += hours * 60 + minutes
    return total_minutes


if __name__ == "__main__":
    window = tk.Tk()
    window.title("Tool")
    window.geometry("500x250")
    lbl= tk.Label(window,text="第一行写开始年月日,月与日不填则默认为9月1日\n第二行填写截至日期，留空则默认到现在",font=("Arial",10))
    lbl.grid(column=1,row=0)
    txt=tk.Entry(window,width=6)
    txt.grid(column=1,row=3)
    txt1=tk.Entry(window,width=6)
    txt1.grid(column=2,row=3)
    txt2=tk.Entry(window,width=6)
    txt2.grid(column=3,row=3)

    txt3=tk.Entry(window,width=6)
    txt3.grid(column=1,row=4)
    txt4=tk.Entry(window,width=6)
    txt4.grid(column=2,row=4)
    txt5=tk.Entry(window,width=6)
    txt5.grid(column=3,row=4)

    # 选择 PDF 文件
    def pdf_scan():
        global selected_file
        selected_file = filedialog.askopenfilename(title="选择 PDF 文件", filetypes=[("PDF Files", "*.pdf")])
        if not selected_file:
            messagebox.showwarning("警告", "未选择 PDF 文件！")
            return

    # 计算 PDF 总时长
    def clicked():
        global selected_file
        if not selected_file:
            messagebox.showerror("错误", "请先选择 PDF 文件！")
            return

        try:
            base_year = int(txt.get())  # 获取用户输入的年份
        except ValueError:
            messagebox.showerror("错误", "请输入有效的基准年份（例如2021）")
            return
        try:
            base_month = int(txt1.get()) if txt1.get().strip() else 9
            base_date = int(txt2.get()) if txt2.get().strip() else 1
            finalyear = int(txt3.get()) if txt3.get().strip() else datetime.now().year
            finalmonth = int(txt4.get()) if txt4.get().strip() else datetime.now().month
            finalday = int(txt5.get()) if txt5.get().strip() else datetime.now().day
        except ValueError:
            return

        with pdfplumber.open(selected_file) as pdf:
            max_pages = len(pdf.pages)

        total_minutes = 0
        for i in range(max_pages):
            datalist = pdfclean(selected_file, i)
            shortlist = dataclean(datalist)
            total_minutes += sum_data(shortlist, base_year,base_month,base_date,finalyear,finalmonth,finalday)

        hours = total_minutes / 60

        # 显示计算结果
        result_text.set(f"基准日期: {base_year}.{base_month}.{base_date}\n截止日期 {finalyear}.{finalmonth}.{finalday}\n总时长 {hours:.2f} 小时")


    # "选择 PDF" 按钮
    btn_select = tk.Button(window, text="选择 PDF", command=pdf_scan, font=("Arial", 12))
    btn_select.grid(column=0, row=2, columnspan=2, pady=20)

    # "确定" 按钮（点击后进行计算）
    btn = tk.Button(window, text="确定", command=clicked)
    btn.grid(column=2, row=2)
    btn_select = tk.Button(window, text="选择 PDF", command=pdf_scan, font=("Arial", 12))
    btn_select.grid(column=0, row=2, columnspan=2, pady=20)

    # 结果显示
    result_text = tk.StringVar()
    result_label = tk.Label(window, textvariable=result_text, font=("Arial", 12), fg="blue")
    result_label.grid(column=0, row=2, columnspan=2, pady=10)


    window.mainloop()

