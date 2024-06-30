# 使用官方的 Python 镜像作为基础镜像
FROM python:3.6-slim

# 设置工作目录
WORKDIR /app

# 将 requirements.txt 文件复制到工作目录
COPY requirements.txt .

# 安装依赖包
RUN pip install --no-cache-dir -r requirements.txt

# 将当前目录下的所有文件复制到工作目录
COPY . .

# 设置环境变量
ENV FLASK_APP=app.py


# 暴露 Flask 默认运行端口
EXPOSE 5000

# 运行 Flask 应用
CMD ["flask", "run", "--host=0.0.0.0"]
