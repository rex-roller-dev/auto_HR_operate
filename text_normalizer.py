import re

def normalize_text(text: str) -> str:
    """
    修复 PDF 中常见的“语义内换行”
    """
    # 1️⃣ 去掉 年/月/日 后面的强制换行
    text = re.sub(r"(年|月|日)\s*\n\s*", r"\1", text)

    # 2️⃣ 去掉数字中间的换行（如 10.\n67）
    text = re.sub(r"(\d)\s*\n\s*(\d)", r"\1\2", text)

    # 3️⃣ 多余空白压缩
    text = re.sub(r"[ \t]+", " ", text)

    return text

def name_nomalizer(name : str)->str:
    # 2. 定义所有可能出现的“点”字符
    # 包括但不限于：中文间隔号、英文句号、英文间隔号、全角句号、半角句号等
    dot_variants = ['·', '•', '.', '．', '・', '⋅']
    
    # 3. 将所有变体统一替换为标准的中文间隔号（或者直接去掉，看需求）
    # 这里选择统一替换为中文间隔号 '·'
    standard_dot = '·'
    for dot in dot_variants:
        if dot in name:
            name = name.replace(dot, standard_dot)
        
    return name
