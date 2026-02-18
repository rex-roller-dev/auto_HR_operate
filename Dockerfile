FROM continuumio/miniconda3:latest

# 设置 Python 无缓冲输出
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY environment_linux.yml .

# 创建 Conda 环境
RUN conda env create -f environment_linux.yml

# 激活环境
SHELL ["conda", "run", "-n", "auto_HR", "/bin/bash", "-c"]

# 复制项目
COPY . .

# CMD 启动 Flask
CMD ["conda", "run", "-n", "auto_HR", "python", "main.py"]


