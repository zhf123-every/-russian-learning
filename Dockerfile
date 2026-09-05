# ---- 构建前端 ----
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---- 运行后端（托管 dist/ + API） ----
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# 视频播放依赖 ffmpeg：把 YouTube/B 站分离流或 m3u8 重封装成单一 mp4 流
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY --from=build /app/dist ./dist
COPY server.py ./
ENV PORT=8000 \
    NO_BROWSER=1
EXPOSE 8000
CMD ["python", "server.py"]
