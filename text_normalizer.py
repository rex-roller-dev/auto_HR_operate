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