FROM python:3.12-slim
WORKDIR /app
COPY services/api_fastapi/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY engines/XAI-Compress/xai_compress /opt/xai-compress/xai_compress
COPY engines/XAI-Compress/checkpoints/selector_v2/best.json /opt/xai-compress/checkpoints/selector_v2/best.json
COPY engines/XAI-Compress/configs /opt/xai-compress/configs
COPY services/api_fastapi/app app
RUN pip install --no-cache-dir yara-python==4.5.4
COPY services/api_fastapi/security security
COPY services/api_fastapi/migrations migrations
COPY scripts/run_all_migrations.py scripts/run_all_migrations.py
ENV PYTHONPATH=/opt/xai-compress
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 STORAGE_PATH=/data \
    CLAMAV_HOST=clamav CLAMAV_PORT=3310
RUN groupadd --gid 10001 xai \
    && useradd --uid 10001 --gid 10001 --no-create-home xai \
    && mkdir -p /data \
    && chown 10001:10001 /data
USER xai
EXPOSE 8000
CMD ["sh", "-c", "python scripts/run_all_migrations.py --apply && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --timeout-keep-alive 5"]
