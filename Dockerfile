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
COPY --from=build /app/dist ./dist
COPY server.py ./
ENV PORT=8000 \
    NO_BROWSER=1
EXPOSE 8000
CMD ["python", "server.py"]
