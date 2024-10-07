#!/usr/bin/env python3
import sys
import os
import fnmatch

# 添加项目根目录到 sys.path，以便导入项目模块
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.append(project_root)

# 导入项目的日志模块
from logger import setup_logger

def replace_domain_in_strm_files(target_directory, old_domain, new_domain):
    """
    遍历目标目录及其子目录下的所有 .strm 文件，替换其中的域名。
    """
    for root, dirs, files in os.walk(target_directory):
        for filename in files:
            if fnmatch.fnmatch(filename, '*.strm'):
                file_path = os.path.join(root, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if old_domain in content:
                        new_content = content.replace(old_domain, new_domain)
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(new_content)
                        logger.info(f"已更新文件：{file_path}")
                    else:
                        logger.info(f"文件中未找到旧域名，跳过：{file_path}")
                except Exception as e:
                    logger.error(f"处理文件时出错：{file_path}，错误信息：{e}")

def main():
    if len(sys.argv) != 4:
        print("用法：python replace_domain.py <target_directory> <old_domain> <new_domain>")
        sys.exit(1)

    target_directory = sys.argv[1]
    old_domain = sys.argv[2]
    new_domain = sys.argv[3]

    if not os.path.isdir(target_directory):
        print(f"指定的目标目录不存在或不是一个目录：{target_directory}")
        sys.exit(1)

    # 获取脚本名（不含扩展名）
    script_name = os.path.splitext(os.path.basename(__file__))[0]
    # 将目标目录名添加到日志名中，避免日志文件名重复
    directory_name = os.path.basename(os.path.normpath(target_directory))
    log_name = f"{script_name}"

    # 初始化日志记录，使用组合后的 log_name
    global logger
    logger, log_file = setup_logger(log_name)
    logger.info(f"日志文件已创建：{log_file}")

    logger.info(f"开始替换目录 {target_directory} 下的 .strm 文件中的域名...")
    replace_domain_in_strm_files(target_directory, old_domain, new_domain)
    logger.info("替换完成。")

if __name__ == "__main__":
    main()
