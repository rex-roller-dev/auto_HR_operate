import re
from text_loader import extract_text

def parse_szvolunteer(path: str) -> dict:
    """
    解析志愿深圳中的信息
    
    :param path: 文件路径
    :type path: str
    :return: 解析结果字典
    :rtype: dict
    """
    text = extract_text(path)
    name = re.search(r"姓名\s*([^\s]+)", text)
    volunteer_id = re.search(r"(志愿者号|义工号)\s*(\d+)", text)
    service_time = re.search(r"服务时长\s*([\d.]+)", text)

    result = {
        "姓名": name.group(1) if name else None,
        "义工号": volunteer_id.group(2) if volunteer_id else None,
        "服务时长": float(service_time.group(1)) if service_time else None
    }

    return result

if __name__ == "__main__":
    path = r"C:\Users\0\Desktop\志愿深圳时长证明(1).pdf"
    data = parse_szvolunteer(path)
    print(data)