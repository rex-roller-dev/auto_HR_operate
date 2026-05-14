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
        return datalist


def pdfclean_all_pages(path):
    """
    读取 PDF 所有页，返回合并后的字符串列表（预处理：去除空字符串、统一空格）
    """
    all_data = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            # 先替换全角空格，再分割，最后去空
            text = text.replace('　', ' ').strip()
            data = [item.strip() for item in re.split(r'[ \n]+', text) if item.strip()]
            all_data.extend(data)
    return all_data


def is_valid_time_format(data):
    """
    判断是否是合法的时间格式：
    - 1小时 / 2小时30分钟 / 3时40分 / 25分钟 / 5分 / 48分 / 1时4分（兼容不规范格式）
    """
    return bool(
        re.match(r"^\d+(小时|时)(\d+(分钟|分))?$", data)  # X小时Y分钟 / X时Y分
        or re.match(r"^\d+(小时|时)$", data)              # X小时 / X时
        or re.match(r"^\d+(分钟|分)$", data)              # X分钟 / X分
    )


def is_valid_date(data):
    """判断是否是合法的日期格式：YYYY.MM.DD"""
    if not re.match(r"^\d{4}\.\d{2}\.\d{2}$", data):
        return False
    try:
        datetime.strptime(data, "%Y.%m.%d")
        return True
    except ValueError:
        return False


def is_valid_source(data):
    """判断是否是合法的来源（统一处理空格）"""
    data = data.replace(' ', '')  # 去除来源中的空格（如“志愿 深圳”→“志愿深圳”）
    return any(key in data for key in ["i志愿", "志愿深圳", "志愿中山", "江门义工"])


def clean_shortlist(shortlist):
    """
    优化版：以「至」为分组标志，按「内容匹配+距离最近」原则提取元素
    """
    cleaned_list = []
    # 先统一处理元素（去空格、替换全角字符）
    processed_list = [item.replace(' ', '').strip() for item in shortlist if item.strip()]
    
    # 定义来源列表（用于精确匹配）
    source_keywords = ["i志愿", "志愿深圳", "志愿中山", "江门义工"]
    
    # 遍历所有“至”的索引
    for idx, data in enumerate(processed_list):
        if data != "至":
            continue
            
        # --------------------------
        # 1. 找 start_time_candidate：至前面最近的日期 (YYYY.MM.DD)
        # --------------------------
        start_time_candidate = None
        # 从 idx-1 往前遍历到 0，找到第一个符合的就停止
        for j in range(idx - 1, -1, -1):
            if is_valid_date(processed_list[j]):
                start_time_candidate = processed_list[j]
                break
        
        # --------------------------
        # 2. 找 duration_candidate：至前后最近的时长 (包含小时/时/分钟/分)
        # --------------------------
        duration_candidate = None
        min_distance = float('inf')
        
        # 先往前找
        for j in range(idx - 1, -1, -1):
            if is_valid_time_format(processed_list[j]):
                dist = idx - j
                if dist < min_distance:
                    min_distance = dist
                    duration_candidate = processed_list[j]
                break # 往前找第一个就是最近的，不用继续
        
        # 再往后找，对比距离
        for j in range(idx + 1, len(processed_list)):
            if is_valid_time_format(processed_list[j]):
                dist = j - idx
                if dist < min_distance:
                    min_distance = dist
                    duration_candidate = processed_list[j]
                break # 往后找第一个就是最近的，不用继续
        
        # --------------------------
        # 3. 找 source_candidate：至前后最近的来源 (在指定列表中)
        # --------------------------
        source_candidate = None
        min_source_dist = float('inf')
        
        # 往前找
        for j in range(idx - 1, -1, -1):
            if processed_list[j] in source_keywords:
                dist = idx - j
                if dist < min_source_dist:
                    min_source_dist = dist
                    source_candidate = processed_list[j]
                break
        
        # 往后找
        for j in range(idx + 1, len(processed_list)):
            if processed_list[j] in source_keywords:
                dist = j - idx
                if dist < min_source_dist:
                    min_source_dist = dist
                    source_candidate = processed_list[j]
                break
        
        # --------------------------
        # 最终校验 & 入库
        # --------------------------
        if (start_time_candidate 
            and duration_candidate 
            and source_candidate 
            and "志愿深圳" not in source_candidate):
            cleaned_list.append((start_time_candidate, duration_candidate, source_candidate))
    
    return cleaned_list


def dataclean(datalist):
    """
    清洗数据，筛选出有效的时间、时长、志愿组织等信息（优化版）
    """
    # 第一步：初步筛选（保留日期、时长、来源、至）
    shortlist = []
    for data in datalist:
        data_stripped = data.strip()
        if (is_valid_date(data_stripped) 
            or is_valid_time_format(data_stripped) 
            or is_valid_source(data_stripped) 
            or data_stripped == "至"):
            shortlist.append(data_stripped)
    
    # 第二步：过滤掉包含“i志愿”但不是“i志愿”本身的元素（如“i志愿123”）
    shortlist = [data for data in shortlist if not (data != "i志愿" and "i志愿" in data)]
    
    # 第三步：生成合法元组
    shortlist = clean_shortlist(shortlist)
    
    # 第四步：过滤掉来源为“志愿深圳”的条目（保留i志愿/志愿中山/江门义工）
    shortlist = [item for item in shortlist if "志愿深圳" not in item[2]]
    
    return shortlist


def is_valid_date_range(date_str, base_year, base_month, base_date, final_year, final_month, final_day):
    """
    检查给定的日期字符串是否在指定的基准日期范围内
    """
    if not is_valid_date(date_str):
        return False
    date = datetime.strptime(date_str, "%Y.%m.%d")
    base_date = datetime(base_year, base_month, base_date)
    final_date = datetime(final_year, final_month, final_day)
    return base_date <= date <= final_date


def parse_duration(duration_str):
    """
    解析时长字符串为分钟数（兼容所有合法格式）
    支持：1小时、2时30分、48分、1时4分等
    """
    hours = 0
    minutes = 0
    
    # 匹配 X小时Y分钟 / X时Y分
    match = re.match(r"^(\d+)(小时|时)(\d+)(分钟|分)$", duration_str)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(3))
        return hours * 60 + minutes
    
    # 匹配 X小时 / X时
    match = re.match(r"^(\d+)(小时|时)$", duration_str)
    if match:
        hours = int(match.group(1))
        return hours * 60
    
    # 匹配 X分钟 / X分
    match = re.match(r"^(\d+)(分钟|分)$", duration_str)
    if match:
        minutes = int(match.group(1))
        return minutes
    
    return 0  # 无效格式返回0


def sum_data(shortlist, base_year, base_month, base_date, final_year, final_month, final_day):
    """
    计算指定日期范围内的总时长（分钟）
    """
    total_minutes = 0
    for item in shortlist:
        if len(item) != 3:
            continue
        start_date, duration, source = item
        
        # 日期范围过滤
        if not is_valid_date_range(start_date, base_year, base_month, base_date, final_year, final_month, final_day):
            continue
        
        # 调试输出符合条件的记录
        # print(f"符合条件的记录: 日期={start_date}, 时长={duration}, 来源={source}", flush=True)  
        # 解析时长并累加
        total_minutes += parse_duration(duration)
    
    return total_minutes


def     parse_ivolunteer(path: str, final_year: int, base_year: int, base_month: int = 9, base_date: int = 1,
                     final_month: int = 8, final_day: int = 31) -> float:
    """
    计算指定 PDF 文件中在给定日期范围内的总志愿服务时长（小时）

    :param path: PDF 文件路径
    :param base_year: 基准年份
    :param base_month: 基准月份
    :param base_date: 基准日期
    :param final_year: 最终年份
    :param final_month: 最终月份
    :param final_day: 最终日期
    :return: 总时长（小时）
    """
    # 1. 读取PDF所有页数据
    datalist = pdfclean_all_pages(path)
    # print("原始数据：", datalist)  # 调试输出原始数据
    # 2. 数据清洗
    shortlist = dataclean(datalist)
    # print("清洗后的数据：", shortlist)  # 调试输出清洗后的数据
    # 3. 计算符合日期范围的总时长
    total_minutes = sum_data(shortlist, base_year, base_month, base_date, final_year, final_month, final_day)
    # 4. 转换为小时
    total_hours = total_minutes / 60
    return total_hours


if __name__ == "__main__":
    # 测试示例
    path = r"C:\Users\20391\Desktop\服务时间证书(120).pdf"
    # 参数说明：path, 最终年份, 基准年份, 基准月, 基准日, 最终月, 最终日
    total_hours = parse_ivolunteer(path, 2026, 2025, 9, 1, 5, 12)

    print(f"总志愿时长：{total_hours:.2f} 小时")
    # dataclean(['2023.08.21', '15小时44分', '至', 'i志愿', '2023.08.22'])

    # mins = sum_data([('2025.11.30', '8小时', 'i志愿'), ('2025.11.29', '8小时', 'i志愿')], 2025, 9, 1,2026, 5, 12)
    # print(f"总志愿时长：{mins/60:.2f} 小时")