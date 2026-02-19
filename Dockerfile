FROM continuumio/miniconda3:latest

ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    libreoffice-l10n-zh-cn \
    fonts-wqy-microhei fonts-wqy-zenhei \
    libx11-6 libxext6 libxrender1 libcups2 libfontconfig1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY environment_linux.yml .
RUN conda env create -f environment_linux.yml

COPY . .

# 复制并设置启动脚本
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# 容器启动时默认执行脚本
CMD ["/app/start.sh"]