# ---- 运行后端（纯 Python API，前端已拆分到 Netlify） ----
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# ffmpeg（视频流代理 + 音频转 16kHz）+ curl（下载 Vosk 模型）
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl && rm -rf /var/lib/apt/lists/*
# Vosk 俄语小模型（~45MB），构建时下载解压，运行时无需联网
RUN curl -L --fail -o /tmp/vosk-model.zip https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip && \
    python -c "import zipfile; zipfile.ZipFile('/tmp/vosk-model.zip').extractall('/app')" && \
    rm /tmp/vosk-model.zip
COPY server.py ./
ENV PORT=8000 \
    NO_BROWSER=1 \
    VOSK_MODEL_PATH=/app/vosk-model-small-ru-0.22
EXPOSE 8000
CMD ["python", "server.py"]
