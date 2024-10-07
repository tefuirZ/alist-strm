import logging
import os
import glob
from datetime import datetime

def setup_logger(log_name, task_id=None):
    log_dir = os.path.join(os.getcwd(), 'logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 如果传入 task_id，则创建定时任务的日志文件
    if task_id:
        base_log_file = os.path.join(log_dir, f'task_{task_id}_{log_name}.log')
    else:
        base_log_file = os.path.join(log_dir, f'{log_name}.log')

    # 如果日志文件已经存在，重命名旧日志文件，加上时间戳
    if os.path.exists(base_log_file):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        new_log_file = base_log_file.replace('.log', f'_{timestamp}.log')
        os.rename(base_log_file, new_log_file)

    # 新日志文件路径
    log_file = base_log_file

    # 创建新的日志文件
    logger = logging.getLogger(log_name)
    logger.setLevel(logging.DEBUG)

    # 清理旧的日志文件，保留最近的 5 个
    cleanup_old_logs(log_dir, log_name, task_id, max_log_files=5)

    # 避免重复添加处理器
    if not logger.handlers:
        # 创建文件处理器
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger, log_file

def cleanup_old_logs(log_dir, log_name, task_id=None, max_log_files=5):
    """
    清理旧的日志文件，确保每个日志文件最多保留 max_log_files 份
    """
    if task_id:
        log_files = glob.glob(os.path.join(log_dir, f'task_{task_id}_{log_name}_*.log'))
    else:
        log_files = glob.glob(os.path.join(log_dir, f'{log_name}_*.log'))

    # 按修改时间倒序排序
    log_files.sort(key=os.path.getmtime, reverse=True)

    # 删除多余的日志文件，保留最新的 max_log_files 个
    for log_file in log_files[max_log_files:]:
        if os.path.exists(log_file):  # 检查文件是否存在
            try:
                os.remove(log_file)
                print(f"删除旧日志文件: {log_file}")
            except Exception as e:
                print(f"删除日志文件时出错: {log_file}，错误: {e}")
        else:
            print(f"日志文件不存在: {log_file}")
