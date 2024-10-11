import subprocess
import sys

# 定义 requirements.txt 文件路径
requirements_file = 'requirements.txt'

def install_package(package_name):
    """
    安装单个包的函数
    """
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", package_name], check=True)
        print(f"成功安装包: {package_name}")
    except subprocess.CalledProcessError as e:
        print(f"安装包 {package_name} 时出错: {e}")
        raise

def install_missing_packages():
    """
    检查并安装缺失的依赖包
    """
    try:
        # 检查是否安装了 pkg_resources，如果没有则安装 setuptools
        try:
            import pkg_resources
        except ImportError:
            print("pkg_resources 模块未找到，正在安装 setuptools...")
            install_package('setuptools')
            import pkg_resources  # 安装后重新导入

        # 读取 requirements.txt 中的所有依赖
        with open(requirements_file, 'r') as file:
            dependencies = [dep.strip() for dep in file.readlines() if dep.strip()]

        # 创建一个列表来存储需要安装的依赖
        missing_packages = []

        # 遍历每个依赖并检查是否已经安装
        for dep in dependencies:
            try:
                # 检查依赖是否已安装
                pkg_resources.require(dep)
            except pkg_resources.DistributionNotFound:
                # 如果未找到依赖，添加到 missing_packages 列表中
                missing_packages.append(dep)

        # 如果有缺失的依赖，安装它们
        if missing_packages:
            print(f"发现缺少的依赖包: {missing_packages}")
            for package in missing_packages:
                install_package(package)
            print("所有缺失的依赖包已成功安装。")
        else:
            print("所有依赖包均已安装，无需更新。")

    except Exception as e:
        print(f"检查或安装依赖时发生错误: {e}")
        sys.exit(1)  # 以错误状态退出

if __name__ == '__main__':
    install_missing_packages()
