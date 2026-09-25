FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY zhilian ./zhilian
COPY web ./web
COPY run.py .
ENV ZHILIAN_HOST=0.0.0.0 ZHILIAN_PORT=8765 ZHILIAN_DATA_DIR=/data
EXPOSE 8765
CMD ["python", "run.py"]
