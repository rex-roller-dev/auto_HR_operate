FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 TZ=Asia/Shanghai
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY yearly/ ./yearly/
EXPOSE 9000
CMD ["gunicorn", "--bind", "0.0.0.0:9000", "--workers", "2", "--threads", "1", "--timeout", "900", "--access-logfile", "-", "--error-logfile", "-", "--access-logformat", "%(m)s %(U)s %(s)s", "app:app"]
