FROM python:3.12-slim
WORKDIR /app
# 国内云主机直连 PyPI 很慢（实测：aliyun 镜像 0.10s vs pypi.org 1.62s，快约 15 倍），
# 因此把索引做成可覆盖的构建参数，默认仍是官方源：
#   docker build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ .
ARG PIP_INDEX_URL=https://pypi.org/simple
# 审计与批次时间要跟部署方一致；容器默认 UTC 会让日志比本机时间早 8 小时。
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*
ENV TZ=Asia/Shanghai
ENV LANG=C.UTF-8
COPY requirements.txt .
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r requirements.txt
COPY zhilian ./zhilian
COPY web ./web
COPY run.py .
ENV ZHILIAN_HOST=0.0.0.0 ZHILIAN_PORT=8765 ZHILIAN_DATA_DIR=/data
EXPOSE 8765
CMD ["python", "run.py"]
