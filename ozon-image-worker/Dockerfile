FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

COPY *.py ./

CMD ["python", "worker.py"]
