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

import os
import pandas as pd
from io import BytesIO
from qcloud_cos import CosConfig
from qcloud_cos import CosS3Client
import logging

# 初始化 COS 客户端（建议在模块级别初始化，避免重复创建）
def get_cos_client():
    """
    获取 COS 客户端实例
    从环境变量读取配置，适合云函数环境
    """
    # 从环境变量获取配置（在云函数控制台设置）
    secret_id = os.environ.get('COS_SECRET_ID')
    secret_key = os.environ.get('COS_SECRET_KEY')
    region = os.environ.get('COS_REGION', 'ap-guangzhou')  # 默认广州，根据你的存储桶区域修改
    
    if not secret_id or not secret_key:
        raise ValueError("COS_SECRET_ID 和 COS_SECRET_KEY 环境变量未设置")
    
    config = CosConfig(
        Region=region,
        SecretId=secret_id,
        SecretKey=secret_key,
        Token=None,  # 使用永久密钥不需要 Token
        Scheme='https'
    )
    return CosS3Client(config)

# 创建全局客户端实例（供所有请求复用）
cos_client = get_cos_client()

def calc_hours_by_name_and_date_from_cos(
    bucket_name,
    cos_key,
    name,
    start_date,
    end_date
):
    """
    从 COS 直接读取 CSV 文件并计算时长
    
    参数：
        bucket_name : COS 存储桶名称（格式：examplebucket-1250000000）
        cos_key     : COS 中的文件路径（如：data/2014-2021（完整版）.csv）
        name        : 姓名（xm）
        start_date  : 'YYYY-MM-DD'
        end_date    : 'YYYY-MM-DD'
    
    返回：hours 总和（float）
    """
    try:
        # 从 COS 获取文件对象
        response = cos_client.get_object(
            Bucket=bucket_name,
            Key=cos_key
        )
        
        # 将文件内容读取到内存流（BytesIO）
        file_stream = BytesIO(response['Body'].get_raw_stream().read())
        
        # 使用 pandas 直接从内存流读取 CSV
        # 注意：如果你的 CSV 文件是 GBK 等编码，可以指定 encoding 参数
        df = pd.read_csv(
            file_stream,
            usecols=["xm", "Begin_Date", "hours"],
            parse_dates=["Begin_Date"],
            encoding='utf-8'  # 如果文件是其他编码，请修改
        )
        
        # 转换日期列为 datetime（虽然 parse_dates 已经做了，但确保格式正确）
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
    
    except Exception as e:
        print(f"从 COS 读取文件失败: {e}")
        raise

if __name__ == "__main__":
    hours = calc_hours_by_name_and_date(
    file_path = r"D:\D\file\auto_HR_operate\szu_volunteer_data\2014-2021（完整版） .csv",
    name = "王佳豪",
    start_date = "2019-09-01",
    end_date = "2024-10-9"
)

    print("总义工时长：", hours)