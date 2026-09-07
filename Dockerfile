# ---- 运行后端（纯 Python API，前端已拆分到 Netlify） ----
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# ffmpeg（视频流代理 + 音频转 16kHz）+ curl（下载 whisper）+ libgomp1（whisper 运行时 OpenMP）
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl libgomp1 && rm -rf /var/lib/apt/lists/*
# whisper.cpp v1.8.7 静态链接版（whisper-cli 无 .so 依赖，避开 libggml CPU 变体崩溃）
RUN curl -L --fail -o /tmp/whisper.tar.gz https://github.com/ggml-org/whisper.cpp/releases/download/v1.8.7/whisper-bin-ubuntu-x64.tar.gz && \
    mkdir -p /tmp/wx && tar -xzf /tmp/whisper.tar.gz -C /tmp/wx --strip-components=1 && \
    cp /tmp/wx/whisper-cli /usr/local/bin/ && \
    rm -rf /tmp/whisper.tar.gz /tmp/wx
# ggml tiny 量化模型（~30MB，q5_1 更省内存），构建时下载，运行时无需联网
RUN curl -L --fail -o /app/ggml-tiny-q5_1.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny-q5_1.bin
COPY server.py ./
ENV PORT=8000 \
    NO_BROWSER=1 \
    WHISPER_MODEL=/app/ggml-tiny-q5_1.bin
EXPOSE 8000
CMD ["python", "server.py"]
