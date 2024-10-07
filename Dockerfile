# 使用官方的 Python 镜像作为基础镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装必要的软件包，包括 curl, cron, tzdata 和 supervisord
RUN apt-get update && apt-get install -y \
    curl \
    cron \
    tzdata \
    supervisor \
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

# 复制 supervisord 配置文件
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# 使用 supervisord 启动
CMD ["/usr/bin/supervisord"]
