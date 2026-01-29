import pandas as pd

def calc_hours_by_name_and_date(
    file_path,
    name,
    start_date,
    end_date
):
    """
    file_path : csv / xlsx 文件路径
    name       : 姓名（xm）
    start_date : 'YYYY-MM-DD'
    end_date   : 'YYYY-MM-DD'
    返回：hours 总和（float）
    """
    # 分块读取文件
    df = pd.read_csv(
        file_path,
        usecols=["xm", "Begin_Date", "hours"],
        parse_dates=["Begin_Date"]
    )
    

    # 转换日期列为 datetime
    df["Begin_Date"] = pd.to_datetime(df["Begin_Date"])

    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)

    # 筛选条件
    filtered = df[
        (df["xm"] == name) &
        (df["Begin_Date"] >= start) &
        (df["Begin_Date"] <= end)
    ]

    # 求和 hours 列
    total_hours = filtered["hours"].fillna(0).sum()

    return float(total_hours)

if __name__ == "__main__":
    hours = calc_hours_by_name_and_date(
    file_path = r"D:\D\file\auto_HR_operate\szu_volunteer_data\2014-2021（完整版） .csv",
    name = "王佳豪",
    start_date = "2019-09-01",
    end_date = "2024-10-9"
)

    print("总义工时长：", hours)