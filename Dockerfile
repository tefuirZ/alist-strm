# 使用官方的 Python 镜像作为基础镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装curl和其他必要的软件包，包括更新依赖包和设置时区
RUN apt-get update && apt-get install -y \
    curl \
    tzdata \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 设置时区为中国
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 将 requirements.txt 文件复制到工作目录
COPY requirements.txt .

# 安装依赖包
RUN pip install --no-cache-dir -r requirements.txt


COPY . .

# 创建配置目录
RUN mkdir /config

# 设置环境变量
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV CONFIG_PATH=/config

# 暴露 Flask 默认运行端口
EXPOSE 5000

# 使用 Gunicorn 运行 Flask 应用
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
