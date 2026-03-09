# -*- coding=utf-8 -*-
import json
import os
from datetime import datetime
from cos_init import cos_init
from qcloud_cos.cos_exception import CosServiceError

# 初始化COS客户端
cos_client = cos_init()
COS_BUCKET = os.environ.get("COS_BUCKET")
COS_AID_PREFIX = "wps_form_processed_aid/"

def check_and_mark_aid(aid: str, request_id: str, name: str = "") -> bool:
    """
    幂等检查：检查aid是否已处理/处理中，未处理则标记为processing
    返回True表示需要跳过，False表示可以继续处理
    """
    if not aid or not COS_BUCKET:
        return False
    
    # 1. 检查是否已存在
    try:
        cos_client.head_object(Bucket=COS_BUCKET, Key=f"{COS_AID_PREFIX}{aid}") 
        return True
    except CosServiceError as e:
        if e.get_status_code() != 404:
            return False
    
    # 2. 标记为处理中
    try:
        content = json.dumps({
            "aid": aid,
            "status": "processing",
            "request_id": request_id,
            "name": name,
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }, ensure_ascii=False)
        cos_client.put_object(
            Bucket=COS_BUCKET,
            Key=f"{COS_AID_PREFIX}{aid}",
            Body=content.encode("utf-8")
        )
    except Exception:
        pass
    return False