# ---- 运行后端（纯 Python API，前端已拆分到 Netlify） ----
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# ffmpeg（视频流代理 + 音频转 16kHz）+ curl（下载 whisper）+ libgomp1（whisper 运行时 OpenMP）
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl libgomp1 && rm -rf /var/lib/apt/lists/*
# whisper.cpp 预编译二进制（whisper-cli 放 PATH，动态库放标准库路径）
RUN curl -L --fail -o /tmp/whisper.tar.gz https://github.com/ggml-org/whisper.cpp/releases/download/b4938/whisper-bin-ubuntu-x64.tar.gz && \
    mkdir -p /tmp/wx && tar -xzf /tmp/whisper.tar.gz -C /tmp/wx --strip-components=1 && \
    cp /tmp/wx/whisper-cli /usr/local/bin/ && \
    cp /tmp/wx/*.so* /usr/local/lib/ && \
    ldconfig && \
    rm -rf /tmp/whisper.tar.gz /tmp/wx
# ggml tiny 模型（~75MB），构建时下载，运行时无需联网
RUN curl -L --fail -o /app/ggml-tiny.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin
COPY server.py ./
ENV PORT=8000 \
    NO_BROWSER=1 \
    WHISPER_MODEL=/app/ggml-tiny.bin
EXPOSE 8000
CMD ["python", "server.py"]
