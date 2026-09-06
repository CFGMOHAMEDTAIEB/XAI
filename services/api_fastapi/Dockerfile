FROM python:3.12-slim
WORKDIR /app
COPY services/api_fastapi/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY engines/XAI-Compress/xai_compress /opt/xai-compress/xai_compress
COPY engines/XAI-Compress/checkpoints/selector_v2/best.json /opt/xai-compress/checkpoints/selector_v2/best.json
COPY engines/XAI-Compress/configs /opt/xai-compress/configs
COPY services/api_fastapi/app app
ENV PYTHONPATH=/opt/xai-compress
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
