FROM python:3.12-slim

# Don't write .pyc files, don't buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# .last_etag and internships.db are written at runtime — keep them in a volume
VOLUME ["/app/data"]

# Point DB and ETag file at the volume so they survive container restarts
ENV DB_PATH=/app/data/internships.db \
    ETAG_FILE=/app/data/.last_etag

CMD ["python", "worker.py"]