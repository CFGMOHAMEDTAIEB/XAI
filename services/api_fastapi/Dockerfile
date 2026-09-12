FROM python:3.12-slim
WORKDIR /app
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       ca-certificates clamav-daemon clamav-freshclam supervisor \
    && rm -rf /var/lib/apt/lists/*
COPY services/api_fastapi/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY engines/XAI-Compress/xai_compress /opt/xai-compress/xai_compress
COPY engines/XAI-Compress/checkpoints/selector_v2/best.json /opt/xai-compress/checkpoints/selector_v2/best.json
COPY engines/XAI-Compress/configs /opt/xai-compress/configs
COPY services/api_fastapi/app app
RUN pip install --no-cache-dir yara-python==4.5.4
COPY services/api_fastapi/security security
COPY services/api_fastapi/migrations migrations
COPY services/api_fastapi/runtime/clamd.conf /etc/clamav/clamd.conf
COPY services/api_fastapi/runtime/freshclam.conf /etc/clamav/freshclam.conf
COPY services/api_fastapi/runtime/freshclam-init.conf /etc/clamav/freshclam-init.conf
COPY services/api_fastapi/runtime/supervisord.conf /etc/supervisor/conf.d/xai.conf
COPY services/api_fastapi/runtime/container-entrypoint.sh /usr/local/bin/container-entrypoint
COPY services/api_fastapi/runtime/start-api.sh /usr/local/bin/start-api
ENV PYTHONPATH=/opt/xai-compress
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 STORAGE_PATH=/data \
    CLAMAV_HOST=127.0.0.1 CLAMAV_PORT=3310
RUN groupadd --gid 10001 xai \
    && useradd --uid 10001 --gid 10001 --no-create-home xai \
    && mkdir -p /data /run/clamav /var/log/clamav /var/lib/clamav \
    && chown 10001:10001 /data \
    && chown -R clamav:clamav /run/clamav /var/log/clamav /var/lib/clamav \
    && chmod 0755 /usr/local/bin/container-entrypoint /usr/local/bin/start-api
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/container-entrypoint"]
