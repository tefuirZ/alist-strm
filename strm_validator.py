import os
import sys
import json
import random
import time
import requests
import logging
from urllib.parse import unquote
from db_handler import DBHandler
from logger import setup_logger
import subprocess
import re  # 导入正则表达式模块


# 定义无效目录树存储的根目录
INVALID_FILE_TREES_DIR = 'invalid_file_trees'


class StrmValidator:
    def __init__(self, db_handler, scan_mode, config_id, task_id=None):
        self.db_handler = db_handler
        self.scan_mode = scan_mode
        self.config_id = config_id
        self.task_id = task_id
        self.logger, self.log_file = self.setup_logger()
        self.config = None
        self.script_config = None
        self.target_directory = ""
        self.remote_base = ""
        self.video_formats = set()

    def setup_logger(self):
        if self.task_id:
            logger, log_file = setup_logger(f'validate_strm_config_{self.config_id}', task_id=self.task_id)
        else:
            logger, log_file = setup_logger(f'validate_strm_config_{self.config_id}')
        return logger, log_file

    def set_target_directory(self, config_id):
        # 从数据库获取配置
        self.config = self.db_handler.get_webdav_config(config_id)
        if not self.config:
            self.logger.error(f"无法获取配置ID {config_id} 的配置，程序终止。")
            sys.exit(1)

        self.target_directory = self.config.get('target_directory', '')
        if not self.target_directory or not os.path.exists(self.target_directory):
            self.logger.error(f"目标目录不存在或未配置: {self.target_directory}")
            sys.exit(1)

        self.script_config = self.db_handler.get_script_config()
        if not self.script_config:
            self.logger.error("无法获取脚本配置，程序终止。")
            sys.exit(1)

        # 获取视频格式
        self.video_formats = set(fmt.lower() for fmt in self.script_config.get('video_formats', []))
        if not self.video_formats:
            self.logger.error("脚本配置中的 'video_formats' 为空或未配置，程序终止。")
            sys.exit(1)

        # 获取远程根路径
        self.remote_base = self.config.get('rootpath', '')
        if not self.remote_base:
            self.logger.error("配置中的 'rootpath' 未配置，程序终止。")
            sys.exit(1)
        # 确保 remote_base 以 '/' 结尾
        if not self.remote_base.endswith('/'):
            self.remote_base += '/'

    def load_cached_tree(self):
        cache_dir = 'cache'
        cache_file = os.path.join(cache_dir, f'webdav_directory_cache_{self.config_id}.json')
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    self.logger.info(f"加载缓存文件: {cache_file}")
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"加载缓存文件出错: {e}")
        else:
            self.logger.warning(f"缓存文件不存在: {cache_file}")
        return None

    def list_local_strm_files(self):
        strm_files = []
        for root, dirs, files in os.walk(self.target_directory):
            for file in files:
                if file.lower().endswith('.strm'):
                    full_path = os.path.abspath(os.path.join(root, file))
                    strm_files.append(full_path)
        self.logger.info(f"找到 {len(strm_files)} 个本地 .strm 文件")
        return strm_files

    def build_expected_strm_set(self, file_tree, current_path=''):
        expected_strm_set = set()
        for file in file_tree:
            file_name = file['name']
            if not file_name.startswith(self.remote_base):
                self.logger.warning(f"文件路径不以远程根路径开头: {file_name}")
                continue
            # 获取相对路径
            relative_path = os.path.relpath(file_name, self.remote_base)
            if file['is_directory']:
                children = file.get('children', [])
                if children:
                    expected_strm_set.update(self.build_expected_strm_set(children, relative_path))
            else:
                file_extension = os.path.splitext(file_name)[1].lower().lstrip('.')
                if file_extension in self.video_formats:
                    # 生成对应的 .strm 文件路径
                    video_relative_dir = os.path.dirname(relative_path)
                    video_base_name = os.path.splitext(os.path.basename(relative_path))[0]
                    strm_file_name = f"{video_base_name}.strm"
                    strm_file_path = os.path.abspath(
                        os.path.join(self.target_directory, video_relative_dir, strm_file_name))
                    expected_strm_set.add(strm_file_path)
                    self.logger.debug(f"预期的 .strm 文件路径: {strm_file_path}")
        return expected_strm_set

    def fast_scan(self, cached_tree, local_strm_files):
        self.logger.info("开始执行快扫模式...")
        expected_strm_files = self.build_expected_strm_set(cached_tree) if cached_tree else set()
        local_strm_files_set = set(local_strm_files)

        self.logger.debug(f"缓存中预期的 .strm 文件数量: {len(expected_strm_files)}")
        self.logger.debug(f"本地实际存在的 .strm 文件数量: {len(local_strm_files_set)}")

        # 本地存在但预期中不存在的 .strm 文件
        invalid_locally_extra = local_strm_files_set - expected_strm_files

        # 预期存在但本地不存在的 .strm 文件
        invalid_expected_missing = expected_strm_files - local_strm_files_set

        self.logger.debug(f"本地存在但预期中不存在的 .strm 文件数量: {len(invalid_locally_extra)}")
        self.logger.debug(f"预期存在但本地不存在的 .strm 文件数量: {len(invalid_expected_missing)}")

        # 记录具体的无效文件路径
        for f in invalid_locally_extra:
            self.logger.debug(f"本地存在但预期中不存在的 .strm 文件: {f}")
        for f in invalid_expected_missing:
            self.logger.debug(f"预期存在但本地不存在的 .strm 文件: {f}")

        invalid_files = list(invalid_locally_extra) + list(invalid_expected_missing)

        self.logger.info(f"快扫发现 {len(invalid_files)} 个无效的 .strm 文件")
        return invalid_files

    def slow_scan(self, local_strm_files):
        self.logger.info("开始执行慢扫模式...")
        invalid_files = []
        total_files = len(local_strm_files)

        # 获取下载间隔范围
        download_interval_range = self.config.get('download_interval_range', (1, 3))
        if not isinstance(download_interval_range, (list, tuple)) or len(download_interval_range) != 2:
            self.logger.error("配置中的 'download_interval_range' 无效，需为包含两个整数的列表或元组。")
            sys.exit(1)
        min_interval, max_interval = download_interval_range

        # 确保间隔值为整数
        try:
            min_interval = int(min_interval)
            max_interval = int(max_interval)
        except ValueError:
            self.logger.error("下载间隔范围的值必须为整数。")
            sys.exit(1)

        # 确保 min_interval <= max_interval
        if min_interval > max_interval:
            min_interval, max_interval = max_interval, min_interval

        for idx, strm_file in enumerate(local_strm_files, 1):
            try:
                # 读取 .strm 文件中的 URL
                with open(strm_file, 'r', encoding='utf-8') as f:
                    url = f.read().strip()

                if not url:
                    self.logger.warning(f"空的 .strm 文件: {strm_file}")
                    invalid_files.append(strm_file)
                    continue

                # 使用 curl 验证 URL
                self.logger.info(f"({idx}/{total_files}) 正在验证: {url}")
                result = subprocess.run(
                    ['curl', '-s', url],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )

                stdout_output = result.stdout
                stderr_output = result.stderr

                # 检查 stderr 中的警告信息
                if "Warning: Binary output can mess up your terminal" in stderr_output:
                    # 出现警告信息，认为链接有效
                    self.logger.info(f"有效的 .strm 文件: {strm_file}")
                # 检查 stdout 中是否包含 <a href="..."> 标签
                elif re.search(r'<a href=".*">.*</a>', stdout_output):
                    self.logger.info(f"有效的 .strm 文件: {strm_file}")
                # 检查 stdout 中是否包含 HTTP 错误消息（如 400 Bad Request、404 Not Found 等）
                elif re.search(r'\b\d{3}\s+\w+', stdout_output):
                    error_message = stdout_output.strip()
                    self.logger.warning(f"无效的 .strm 文件: {strm_file}，错误信息: {error_message}")
                    invalid_files.append(strm_file)
                else:
                    # 尝试解析 JSON，检查 'code' 字段
                    try:
                        response_json = json.loads(stdout_output)
                        if 'code' in response_json:
                            code_value = response_json['code']
                            self.logger.warning(f"无效的 .strm 文件: {strm_file}，返回的 code: {code_value}")
                            invalid_files.append(strm_file)
                        else:
                            # 如果没有 'code' 字段，认为链接有效
                            self.logger.info(f"有效的 .strm 文件: {strm_file}")
                    except json.JSONDecodeError:
                        # 不是有效的 JSON，认为链接有效
                        self.logger.info(f"有效的 .strm 文件: {strm_file}")

            except Exception as e:
                # 捕获异常并记录
                self.logger.error(f"验证 .strm 文件时出错: {strm_file}，错误: {e}")
                invalid_files.append(strm_file)

            # 随机等待
            interval = random.randint(min_interval, max_interval)
            self.logger.debug(f"等待 {interval} 秒后继续...")
            time.sleep(interval)

        self.logger.info(f"慢扫发现 {len(invalid_files)} 个无效的 .strm 文件")
        return invalid_files

    def save_invalid_trees(self, invalid_files):
        if not os.path.exists(INVALID_FILE_TREES_DIR):
            os.makedirs(INVALID_FILE_TREES_DIR)
            self.logger.info(f"创建目录: {INVALID_FILE_TREES_DIR}")

        invalid_tree = {}
        for file_path in invalid_files:
            relative_path = os.path.relpath(file_path, self.target_directory)
            parts = relative_path.split(os.sep)
            current = invalid_tree
            for part in parts[:-1]:
                current = current.setdefault(part, {})
            current[parts[-1]] = "invalid"

        output_file = os.path.join(INVALID_FILE_TREES_DIR, f'invalid_file_trees_{self.config_id}.json')
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(invalid_tree, f, ensure_ascii=False, indent=4)
            self.logger.info(f"无效的目录树已保存到: {output_file}")
        except Exception as e:
            self.logger.error(f"保存无效目录树时出错: {e}")

    def validate_all_strm_files(self):
        local_strm_files = self.list_local_strm_files()
        invalid_files = []

        if self.scan_mode == 'quick':
            cached_tree = self.load_cached_tree()
            if not cached_tree:
                self.logger.warning("未加载到缓存树，快扫将视为所有本地 .strm 文件无效。")
                invalid_files = local_strm_files
            else:
                invalid_files = self.fast_scan(cached_tree, local_strm_files)
        elif self.scan_mode == 'slow':
            invalid_files = self.slow_scan(local_strm_files)
        else:
            self.logger.error(f"未知的扫描模式: {self.scan_mode}")
            sys.exit(1)

        total_files = len(local_strm_files)
        invalid_count = len(invalid_files)
        valid_count = total_files - invalid_count

        if invalid_files:
            self.save_invalid_trees(invalid_files)

        self.logger.info(f"验证完成。有效的 .strm 文件数量: {valid_count}，无效的 .strm 文件数量: {invalid_count}")


def main():
    if len(sys.argv) < 3 or len(sys.argv) > 4:
        print("用法: python strm_validator.py <config_id> <scan_mode> [task_id]")
        print("示例: python strm_validator.py 1 quick [task_id]")
        sys.exit(1)

    try:
        config_id = int(sys.argv[1])
    except ValueError:
        print("config_id 必须是整数。")
        sys.exit(1)

    scan_mode = sys.argv[2].lower()
    task_id = sys.argv[3] if len(sys.argv) == 4 else None  # 获取 task_id，如果存在

    if scan_mode not in ['quick', 'slow']:
        print("扫描模式无效，请选择 'quick' 或 'slow'.")
        sys.exit(1)

    # 创建数据库处理实例
    db_handler = DBHandler()

    try:
        # 创建 StrmValidator 实例并执行校验
        validator = StrmValidator(db_handler, scan_mode, config_id, task_id=task_id)
        validator.set_target_directory(config_id)
        validator.validate_all_strm_files()
    except Exception as e:
        print(f"运行过程中出现未捕获的异常: {e}")
    finally:
        # 关闭数据库连接
        db_handler.close()


if __name__ == "__main__":
    main()
