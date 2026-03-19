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
    
def pdfclean_all_pages(path):
    """
    读取 PDF 所有页，返回合并后的字符串列表
    """
    all_data = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            data = re.split(r'[ \n]+', text)
            all_data.extend(data)
    return all_data


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
    以「至」为分组标志，按规则生成元组：
    - 至的前一个元素 = 活动开始时间（元组第1位）
    - 至的后一个元素 = 服务时长（元组第2位）
    - 至的后第二个元素 = 数据来源（元组第3位）
    """
    cleaned_list = []
    # 遍历整个列表，找到所有的「至」的索引
    for idx, data in enumerate(shortlist):
        if data.strip() == "至":
            # 按你的规则取元素：至的前1、后1、后2
            start_time = shortlist[idx - 1]
            duration = shortlist[idx + 1]
            source = shortlist[idx + 2]
            # 拼成你要的元组，加到结果里
            cleaned_list.append((start_time, duration, source))
    
    return cleaned_list


def dataclean(datalist):
    """
    清洗数据，筛选出有效的时间、时长、志愿组织等信息
    
    :param datalist: 待处理的字符串列表
    :return: 处理后的字符串列表，每 3 个元素为一组（时间、时长、组织）
    """
    shortlist =[]
    # shortlist1=[]
    for data in datalist:
        if ("小时" in data or "分钟" in data or "i志愿" in data or "志愿深圳" in data or '志愿中山' in data or "江门义工" in data or
                re.match(r"\d{4}\.\d{2}\.\d{2}", data) or "时" in data or "分" in data or "至" in data):
            shortlist.append(data)
    shortlist = [data for data in shortlist if not (data != "i志愿" and "i志愿" in data)]
    #删除可能存在的i志愿关键字
    # print(shortlist)
    shortlist = [data for data in shortlist if is_valid_time_format(data) or
                 ("时" not in data and "分" not in data)]
    #删除可能存在的的时间关键字
    # print(shortlist)
    shortlist = [data for data in shortlist if not (
            (match := re.match(r"\d{4}\.\d{2}\.\d{2}", data)) and data != match.group()
    )]  # 删除名称中可能存在的年份时间关键字
    shortlist = clean_shortlist(shortlist)
    #读取到的数据有问题，是“开始时间”“服务时长”“志愿组织”“结束时间”，pop掉最后一个结束时间
    # print(shortlist) #测试

    for i in range(len(shortlist)-1, -1, -1):
        if len(shortlist[i]) >= 3 and "志愿深圳" in shortlist[i][2]:
            shortlist.pop(i)

    # for i in range(0, len(shortlist), 3):  # 每 3 个元素一组
    #     if i + 2 < len(shortlist):  # 确保不会超出索引范围
    #         shortlist1.append((shortlist[i], shortlist[i + 1], shortlist[i + 2]))   # 变成元组，契合后面ai写的代码。
    # print(shortlist) #测试
    return shortlist


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

def parse_ivolunteer(path : str, finalyear : int, base_year : int, base_month : int = 9, base_date : int = 1, finalmonth : int = 8, finalday : int = 31) -> float:
    """
    parse_ivolunteer 的 Docstring

    说明：计算指定 PDF 文件中在给定日期范围内的总志愿服务时长（小时）。

    :param path: PDF 文件路径
    :param base_year: 基准年份
    :param base_month: 基准月份
    :param base_date: 基准日期
    :param finalyear: 最终年份
    :param finalmonth: 最终月份
    :param finalday: 最终日期
    """
    datalist = pdfclean_all_pages(path)
    # print(datalist) #测试
    shortlist = dataclean(datalist)
    # print(shortlist) #测试
    total_minutes = sum_data(shortlist, base_year,base_month,base_date,finalyear,finalmonth,finalday)
    total_hours = total_minutes / 60
    return total_hours

if __name__ == "__main__":
    path = r"C:\Users\20391\Desktop\服务时间证书(58)(1).pdf"
    # datalist = pdfclean(path, 0)
    # shortlist = dataclean(datalist)
    # total_minutes = sum_data(shortlist, 2021,1,1,2025,12,31)
    # total_hours = total_minutes / 60
    total_hours = parse_ivolunteer(path, 2024, 2019, 9, 11, 7, 3)
    print(f"总志愿时长：{total_hours} 小时")