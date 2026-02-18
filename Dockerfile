FROM continuumio/miniconda3:latest

# 设置 Python 无缓冲输出
ENV PYTHONUNBUFFERED=1

# ========== 新增：安装 LibreOffice 和相关依赖 ==========
# 切换为国内镜像源加速（可选，但强烈推荐）
# RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list && \
#     sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list

# 安装 LibreOffice 核心套件、中文语言包、中文字体和必要系统库
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    libreoffice-l10n-zh-cn \
    fonts-wqy-microhei fonts-wqy-zenhei \
    libx11-6 libxext6 libxrender1 libcups2 libfontconfig1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
# ====================================================

WORKDIR /app

COPY environment_linux.yml .

# 创建 Conda 环境
RUN conda env create -f environment_linux.yml

# 激活环境
SHELL ["conda", "run", "-n", "auto_HR", "/bin/bash", "-c"]

# 复制项目
COPY . .

# CMD 启动 Flask
CMD ["conda", "run", "--no-capture-output", "-n", "auto_HR", "python", "-u", "main.py"]