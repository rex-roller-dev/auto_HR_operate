"""
将表单答案解析并写回 WPS 表格（sheets）。

功能：
- 将答题内容平铺为键值对（`parse_answer_contents`）
- 获取活动工作表与写入区域（`get_active_sheet`）
- 将一行数据构建为单元格操作（`build_row_cells`）
- 把审核结果写入表格（`write_verify_result`）

示例：模块最下方有一个简单的使用示例，调用 `write_verify_result` 将数据写入表格。
"""

import requests
from ask_for_token import get_access_token

def parse_answer_contents(answer_contents: list) -> dict:
    """
    将 answerContents 拉平成 {title: value}
    file 类型只保留 fileShareLink
    """
    result = {}
    for item in answer_contents:
        title = item["title"]
        if item["type"] == "file":
            files = item.get("value", [])
            result[title] = [
                f["fileShareLink"] for f in files if "fileShareLink" in f
            ]
        else:
            val = item.get("value")
            if isinstance(val, list):
                val = val[0] if val else ""
            result[title] = val
    return result


def get_active_sheet(file_id: str, headers: dict):
    """
    get_active_sheet 的 说明
    通过文件 ID 获取 工作表1 的 sheet_id 及其 active_area

    
    :param file_id: 说明
    :type file_id: str
    :param headers: 说明
    :type headers: dict
    """
    url = f"https://openapi.wps.cn/v7/sheets/{file_id}/worksheets"
    resp = requests.get(url, headers=headers).json()

    if resp["code"] != 0:
        raise RuntimeError(f"获取 worksheets 失败,{resp}")  

    sheets = resp["data"]["sheets"]

    target_sheet = None
    for sheet in sheets:
        if sheet["name"] == "工作表1":
            target_sheet = sheet
            break

    if not target_sheet:
        raise RuntimeError("未找到 工作表1")

    sheet_id = target_sheet["sheet_id"]
    active = target_sheet.get("active_area")
    return {
        "sheet_id": sheet_id,
        "active_area": active
    }

def build_row_cells(row_index: int, values: list, text_cols=None):
    if text_cols is None:
        text_cols = set()

    cells = []

    for col, value in enumerate(values):  # ✅ col 从 0 开始，保留
        if value is None or value == "":
            continue

        cell = {
            "row_from": row_index,
            "row_to": row_index,
            "col_from": col,
            "col_to": col,
        }

        # 超链接，保持你原逻辑
        if isinstance(value, str) and value.startswith("=HYPERLINK"):
            cell["op_type"] = "cell_operation_type_formula"
            cell["formula"] = value

        # 👉 强制文本列（E / G / H / I）
        elif col in text_cols:
            cell["op_type"] = "cell_operation_type_formula"
            cell["formula"] = as_text(value)

        # 其他列
        else:
            cell["op_type"] = "cell_operation_type_formula"
            cell["formula"] = str(value)

        cells.append(cell)

    return cells


def as_text(value):
    """
    将值包装为公式文本形式
    例如，输入 123 返回 ="123"
    """
    if value is None:
        return ""
    return f"'{value}"

def build_file_cells(links: list, max_count: int, prefix_name: str):
    """
    把文件链接列表转换为多个 HYPERLINK 单元格
    """
    cells = []

    for i in range(max_count):
        if i < len(links):
            url = links[i]
            name = f"{prefix_name}{i+1}" if i > 0 else prefix_name
            cells.append(f'=HYPERLINK("{url}","{name}")')
        else:
            cells.append("")

    return cells


def write_verify_result(
    form_data: dict,
    exception: Exception,
    file_id: str,
    access_token: str,
    TEXT_COLS = {4, 6, 7, 8, 26, 30}
) -> dict:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # 解析表单
    answers = parse_answer_contents(form_data["answerContents"])

    # 获取工作表
    sheet_info = get_active_sheet(file_id, headers)
    sheet_id = sheet_info["sheet_id"]
    active = sheet_info["active_area"]

    write_row = active["row_to"] + 1
    编号 = 18180000 + write_row

    状态 = "待人工审核" if exception is None else f"异常：{exception}"

    # 示例附件（你后面可以按 title 对应）
    word_links = answers.get("深圳大学志愿时认证表Word", [])
    word_cells = build_file_cells(
        word_links,
        max_count=5,
        prefix_name="志愿时认证表Word"
    )

    shenzhen_links = []
    shenzhen_links += answers.get("广东省内志愿时服务证明（佐证材料）--志愿深圳部分", [])
    shenzhen_cells = build_file_cells(
        shenzhen_links,
        max_count=4,
        prefix_name="志愿深圳"
    )

    iyuan_links = answers.get("广东省内志愿时服务证明（佐证材料）--i志愿部分", [])
    iyuan_cells = build_file_cells(
        iyuan_links,
            max_count=2,
            prefix_name="i志愿"
        )



    row_values = [
        编号,
        状态,
        answers.get("请输入姓名", ""),
        answers.get("请选择性别", ""),
        answers.get("学号", ""),
        answers.get("学院", ""),
        answers.get("电子义工证注册号/义工证号", ""),
        answers.get("请输入身份证号", ""),
        answers.get("请输入联系方式", ""),
        answers.get("用途", ""),
        answers.get("2024-2025学年是否有挂科记录", ""),
        answers.get("是否重复申请", ""),
        answers.get("审核方式", ""),
        answers.get("备注", ""),
        
        # 14–18 志愿时认证表Word
        *word_cells,

        # 19–22 志愿深圳
        *shenzhen_cells,

        # 23–24 i志愿
        *iyuan_cells,

        # 25 深大义工
        answers.get("深大义工", ""),

        # 26 学号
        answers.get("深大义工附件2", ""),


        "",                                    # 27-29 预留（如果你表里有）
        "",
        "",

        answers.get("邮箱", ""),               # 30 ✅ 新增邮箱
    ]


    range_data = build_row_cells(
        write_row,
        row_values,
        text_cols=TEXT_COLS
    )

    url = f"https://openapi.wps.cn/v7/sheets/{file_id}/worksheets/{sheet_id}/range_data/batch_update"
    resp = requests.post(
        url,
        headers=headers,
        json={"range_data": range_data}
    ).json()

    if resp["code"] != 0:
        raise RuntimeError(f"写入失败，错误信息：{resp}")

    return {
        "success": True,
        "row": write_row,
        "sheet_id": sheet_id
    }

if __name__ == "__main__":
    data = {'rid': 'ZzOCK4euEq', 
'formId': '20251010154413380029407', 
'formTitle': '志愿时认证表审核申请（粤海校区）-2025—2026', 
'aid': '20260120211648978971186', 
'eventTs': 1768915009000, 
'messageTs': 1768985641586, 
'creatorId': '1640347175', 
'creatorName': '曹裕超',
'event': 'create_answer', 
'version': 2, 
'answerContents': 
[{'qid': 'j4jodj', 'type': 'input', 'title': '请输入姓名', 'value': '曹裕超'}, {'qid': 'aiecak', 'type': 'select', 'title': '请选择性别', 'value': ['男']}, {'qid': 'm97otm', 'type': 'input', 'title': '学号', 'value': '2300471004'}, {'qid': '8884so', 'type': 'input', 'title': '学院', 'value': '土木与交通工程学院'}, {'qid': 'egxtog', 'type': 'input', 'title': '电子义工证注册号/义工证号', 'value': '0000514250'}, {'qid': '5fbh5l', 'type': 'input', 'title': '请输入身份证号', 'value': '44022920001112161X'}, {'qid': 'pyci44', 'type': 'input', 'title': '请输入联系方式', 'value': '13531474271'}, {'qid': '93aewv', 'type': 'input', 'title': '用途', 'value': '入党档案'}, {'qid': 'vk7i5f', 'type': 'select', 'title': '2024-2025学年是否有挂科记录', 'value': ['否']}, {'qid': 'uljvc0', 'type': 'input', 'title': '是否重复申请', 'value': '是，第一次申请一直未进入制表状态'}, {'qid': 'shjlog', 'type': 'select', 'title': '审核方式', 'value': ['线上审核']}, {'qid': 'wywm2a', 'type': 'input', 'title': '备注', 'value': ''}, {'qid': 'k6xep1', 'type': 'file', 'title': '深圳大学志愿时认证表Word', 'value': [{'fileName': '认证表.pdf', 'fileShareLink': 'https://www.kdocs.cn/l/co4BlrgCtC3p', 'fileId': '487941693390', 'fileSid': 'co4BlrgCtC3p', 'ext': 'pdf'}]}, {'qid': 'p2zrq9', 'type': 'file', 'title': '广东省内志愿时服务证明（佐证材料）--志愿深圳部分', 'value': [{'fileName': '志愿深圳记录.pdf', 'fileShareLink': 'https://www.kdocs.cn/l/chgTYIgIr6o3', 'fileId': '487943188085', 'fileSid': 'chgTYIgIr6o3', 'ext': 'pdf'}]}, {'qid': 'xxo6ib', 'type': 'file', 'title': '附件一--志愿深圳部分（同上，相同无需重复上传）', 'value': []}, {'qid': 'tjbcap', 'type': 'file', 'title': '广东省内志愿时服务证明（佐证材料）--i志愿部分', 'value': []}, {'qid': 'lusa9s', 'type': 'select', 'title': '广东省内志愿时--深大义工部分', 'value': ['不需要深大义工']}, {'qid': 'yfyzzw', 'type': 'file', 'title': '附件二--补充佐证材料（相同无需重复上传）', 'value': []}]}
    user_token = "eyJhbGciOiJFUzI1NiIsImtpZCI6IjNiNTkyYWYwLTk5ODktNDRhOC1hMzQ3LTE4Yzc1MDQ4MTlmNCIsInR5cCI6IkpXVCJ9.eyJhaWQiOjE3OTQ0ODE4MzgsImF0cCI6InVzZXIiLCJhdHMiOiJHREt3bGJyIiwiYnVpIjpmYWxzZSwiY2lkIjo2OTk1NTE0MTIsImNsaSI6IkFLMjAyNjAxMjNNSUpLR00iLCJleHAiOjE3Njk2ODgyNDAsImpzdCI6ZmFsc2UsInNwaSI6MTc5NDk5NzkzMH0.zB_5rNMNhYeWiv0wpLCJr3sL-qiSGK3LT5L3CtmYnTNX9Bl1783B9-ahdPHKjSygjpnDUBzTLIxOys0iaGqJ6A"
    token = user_token if user_token else get_access_token()["access_token"]
    write_verify_result(data, None, "489000618255", token)