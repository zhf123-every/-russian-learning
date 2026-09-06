# ---- 运行后端（纯 Python API，前端已拆分到 Netlify） ----
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# 视频播放依赖 ffmpeg：把 YouTube/B 站分离流或 m3u8 重封装成单一 mp4 流
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
# 修复 faster-whisper 依赖 ctranslate2 在 slim 容器里因 executable-stack 导致 import 崩溃的问题
RUN apt-get update && apt-get install -y --no-install-recommends patchelf && \
    find /usr/local/lib/python3.11/site-packages -name 'libctranslate2*.so*' \
        -exec patchelf --clear-execstack {} \; ; \
    apt-get remove -y patchelf && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
COPY server.py ./
ENV PORT=8000 \
    NO_BROWSER=1
EXPOSE 8000
CMD ["python", "server.py"]
