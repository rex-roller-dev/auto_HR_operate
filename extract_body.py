import json
from typing import Union, Dict, Any

def extract_body(event: Union[Dict, str]) -> Dict[str, Any]:
    """
    从事件中提取并解析 body 字典。

    支持三种输入格式：
    1. 包含 'body' 字段的字典，且该字段值为 JSON 字符串（如 API 网关触发事件）
    2. 已经解析好的字典（直接作为 body 使用）
    3. JSON 格式的字符串（直接解析）

    参数:
        event: 输入事件，可以是字典或字符串

    返回:
        解析后的 body 字典

    抛出:
        ValueError: 当 JSON 解析失败时
        TypeError: 当输入类型不支持时
    """
    # 情况1: 输入是字符串，直接解析为字典
    if isinstance(event, str):
        try:
            return json.loads(event)
        except json.JSONDecodeError as e:
            raise ValueError(f"无效的 JSON 字符串: {e}")

    # 情况2: 输入是字典
    if isinstance(event, dict):
        # 如果字典包含 'body' 键且其值为字符串，则解析该字符串
        if 'body' in event and isinstance(event['body'], str):
            try:
                return json.loads(event['body'])
            except json.JSONDecodeError as e:
                raise ValueError(f"event['body'] 包含无效的 JSON: {e}")
        else:
            # 否则认为 event 本身就是 body 字典，直接返回
            return event

    # 其他类型不支持
    raise TypeError(f"不支持的输入类型: {type(event)}")