#!/bin/bash
# 加载 conda 函数（路径取决于基础镜像）
source /opt/conda/etc/profile.d/conda.sh
# 激活目标环境
conda activate auto_HR
# 启动 Flask 应用（exec 保证信号正确传递）
exec python -u main.py