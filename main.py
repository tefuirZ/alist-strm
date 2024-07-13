import json
import os
import shutil
import sqlite3
import urllib
from datetime import datetime
import requests
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import concurrent.futures

# 配置日志记录器，添加时间戳
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 获取配置路径，默认值为 /config
config_path = os.getenv('CONFIG_PATH', '/config')

# 确保数据库路径存在
db_dir = Path(config_path)
db_dir.mkdir(parents=True, exist_ok=True)

# 数据库连接
db_path = db_dir / 'config.db'
db_path_str = str(db_path)  # 将 Path 对象转换为字符串
logger.debug(f"数据库路径: {db_path_str}")  # 添加调试信息

conn = sqlite3.connect(db_path_str)
cursor = conn.cursor()
# 创建配置表
cursor.execute('''
CREATE TABLE IF NOT EXISTS config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    root_path TEXT NOT NULL,
    site_url TEXT NOT NULL,
    target_directory TEXT NOT NULL,
    ignored_directories TEXT,
    token TEXT NOT NULL,
    update_existing INTEGER NOT NULL
)
''')
conn.commit()

# 创建用户配置表
cursor.execute('''
CREATE TABLE IF NOT EXISTS user_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_formats TEXT,
    subtitle_formats TEXT,
    image_formats TEXT,
    download_threads INTEGER,
    enable_metadata_download INTEGER,
    enable_invalid_link_check INTEGER,
    enable_nfo_download INTEGER,
    enable_subtitle_download INTEGER,
    enable_image_download INTEGER,
    enable_refresh INTEGER  -- 添加此行
)
''')
conn.commit()

# 检查并插入默认用户配置
cursor.execute('SELECT COUNT(*) FROM user_config')
user_count = cursor.fetchone()[0]
if user_count == 0:
    cursor.execute('''
    INSERT INTO user_config (video_formats, subtitle_formats, image_formats, download_threads, enable_metadata_download, enable_invalid_link_check, enable_nfo_download, enable_subtitle_download, enable_image_download, enable_refresh)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)  -- 添加 enable_refresh 的值
    ''', (
        '.mp4,.mkv,.avi,.mov,.flv,.wmv,.ts,.m2ts',  # 默认视频格式
        '.srt,.ass,.ssa,.vtt',  # 默认字幕格式
        '.jpg,.jpeg,.png,.bmp,.gif,.tiff,.webp',  # 默认图片格式
        5,  # 默认下载线程数
        1,  # 默认开启元数据下载
        1,  # 默认开启失效文件对比
        1,  # 默认开启nfo文件下载
        1,  # 默认开启字幕下载
        1,  # 默认开启图片下载
        1   # 默认开启刷新
    ))
    conn.commit()

# 确保插入默认配置后关闭数据库连接
conn.close()

total_valid_count = 0
total_invalid_count = 0
total_created_count = 0

# 重新打开数据库连接
conn = sqlite3.connect(db_path_str)
cursor = conn.cursor()

# 从数据库获取用户配置
def get_user_config():
    cursor.execute('SELECT * FROM user_config WHERE id = 1')
    user_config = cursor.fetchone()
    if user_config and len(user_config) == 11:  # 更新长度检查
        logger.debug(f"用户配置: {user_config}")  # 增加调试信息
        return {
            'video_formats': user_config[1].split(','),
            'subtitle_formats': user_config[2].split(','),
            'image_formats': user_config[3].split(','),
            'download_threads': user_config[4],
            'enable_metadata_download': bool(user_config[5]),
            'enable_invalid_link_check': bool(user_config[6]),
            'enable_nfo_download': bool(user_config[7]),
            'enable_subtitle_download': bool(user_config[8]),
            'enable_image_download': bool(user_config[9]),
            'enable_refresh': bool(user_config[10]),  # 添加此行
        }
    else:
        logger.error("用户配置不完整或未找到用户配置")
        sys.exit(1)

user_config = get_user_config()

def validate_config_item(name, value):
    if value.endswith('/'):
        raise ValueError(f"{name} 配置项不能以 '/' 结尾: {value}")

def validate_config(root_path, site_url, target_directory, ignored_directories):
    validate_config_item("root_path", root_path)
    validate_config_item("site_url", site_url)
    validate_config_item("target_directory", target_directory)
    for directory in ignored_directories:
        validate_config_item("ignored_directories", directory)

def requests_retry_session(
        retries=3,
        backoff_factor=0.3,
        status_forcelist=(500, 502, 504),
        session=None,
):
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def list_directory(path, api_base_url, token, user_agent):
    try:
        url_list = api_base_url + "/fs/list"
        payload_list = {
            "path": path,
            "password": "",
            "page": 1,
            "per_page": 0,
            "refresh": bool(user_config['enable_refresh'])  # 动态设置 refresh 值为布尔值
        }
        headers_list = {
            'Authorization': token,
            'User-Agent': user_agent,
            'Content-Type': 'application/json'
        }
        response_list = requests_retry_session().post(url_list, headers=headers_list, json=payload_list)
        response_list.raise_for_status()  # 确保请求成功

        response_data = response_list.json()

        # 检查返回的JSON内容
        if response_data.get('code') == 401:
            raise Exception("无效的token")

        return response_data

    except requests.RequestException as e:
        logger.error(f"请求错误: {e}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析错误: {e}")
        logger.error(f"响应内容: {response_list.text}")
        raise

def traverse_directory(path, json_structure, api_base_url, token, user_agent, ignored_directories):
    try:
        directory_info = list_directory(path, api_base_url, token, user_agent)
        logger.info(f"遍历目录: {path}")  # 添加日志记录

        if directory_info.get('data') and directory_info['data'].get('content'):
            with concurrent.futures.ThreadPoolExecutor(max_workers=user_config['download_threads']) as executor:
                futures = []
                for item in directory_info['data'].get('content'):
                    if item['name'] in ignored_directories:
                        continue

                    if item['is_dir']:
                        new_path = os.path.join(path, item['name'])
                        new_json_object = {}
                        json_structure[item['name']] = new_json_object
                        futures.append(executor.submit(traverse_directory, new_path, new_json_object, api_base_url, token, user_agent, ignored_directories))
                    else:
                        json_structure[item['name']] = {
                            'type': 'file',
                            'size': item['size'],
                            'modified': item['modified'],
                            'sign': item.get('sign')
                        }
                
                # 等待所有任务完成
                for future in concurrent.futures.as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        logger.error(f"遍历目录时出错: {e}")

    except Exception as e:
        raise  # 确保异常被抛出以终止脚本

def is_video_file(filename):
    return any(filename.lower().endswith(ext) for ext in user_config['video_formats'])

def is_subtitle_file(filename):
    if user_config['enable_subtitle_download']:
        return any(filename.lower().endswith(ext) for ext in user_config['subtitle_formats'])
    return False

def is_metadata_file(filename):
    metadata_extensions = []
    if user_config['enable_nfo_download']:
        metadata_extensions.append('.nfo')
    if user_config['enable_metadata_download']:
        metadata_extensions.append('.xml')
    return any(filename.lower().endswith(ext) for ext in metadata_extensions)

def is_image_file(filename):
    if user_config['enable_image_download']:
        return any(filename.lower().endswith(ext) for ext in user_config['image_formats'])
    return False

def create_strm_files(json_structure, target_directory, base_url, update_existing, current_path=''):
    global total_created_count
    created_count = 0

    full_path = Path(target_directory) / current_path

    for name, item in json_structure.items():
        if isinstance(item, dict) and item.get('type') == 'file' and is_video_file(name):
            try:
                strm_filename = name.rsplit('.', 1)[0] + '.strm'
                strm_path = full_path / strm_filename

                if not strm_path.exists():
                    if not full_path.exists():
                        full_path.mkdir(parents=True, exist_ok=True)
                    sign = item.get('sign') if update_existing else None  # 根据 update_existing 决定是否使用签名
                    create_strm_file(strm_path, base_url, name, current_path, json_structure, sign)
                    created_count += 1
                    total_created_count += 1
            except Exception as e:
                logger.error(f"创建 .strm 文件时出错: {e}")
                continue

        elif isinstance(item, dict) and item.get('type') != 'file':
            try:
                new_directory = full_path / name
                if not new_directory.exists():
                    new_directory.mkdir(parents=True, exist_ok=True)
                create_strm_files(item, target_directory, base_url, update_existing, (Path(current_path) / name).as_posix())
            except Exception as e:
                logger.error(f"处理子目录时出错: {e}")
                continue

    if created_count > 0:
        logger.info(f"创建了 {created_count} 个 .strm 文件在目录 {current_path}")

    if user_config['enable_metadata_download']:
        try:
            if not full_path.exists():
                full_path.mkdir(parents=True, exist_ok=True)
            download_image_files(json_structure, base_url, current_path, full_path)
        except Exception as e:
            logger.error(f"下载图片文件时出错: {e}")


def download_image_files(json_structure, base_url, current_path, full_path):
    with ThreadPoolExecutor(max_workers=user_config['download_threads']) as executor:
        futures = []
        for name, item in json_structure.items():
            if isinstance(item, dict) and item.get('type') == 'file' and is_image_file(name):
                futures.append(executor.submit(download_file, base_url, current_path, name, full_path))

        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logger.error(f"下载图片文件时出错: {e}")

def create_strm_file(strm_path, base_url, name, current_path, json_structure, sign=None):
    try:
        encoded_file_path = urllib.parse.quote((Path(current_path) / name).as_posix(), safe='')
        video_url = base_url + encoded_file_path
        
        if sign:
            video_url += "?sign=" + sign

        with open(strm_path, 'w', encoding='utf-8') as strm_file:
            strm_file.write(video_url)

        if (user_config['enable_nfo_download'] or user_config['enable_subtitle_download'] or user_config['enable_image_download']) and has_related_files(json_structure, name):
            download_related_files(json_structure, name, base_url, strm_path.parent, current_path)
    except Exception as e:
        logger.error(f"创建 .strm 文件时出错: {e}")


def has_related_files(json_structure, video_name):
    base_name = video_name.rsplit('.', 1)[0]
    for name in json_structure:
        if name.startswith(base_name) and (is_subtitle_file(name) or is_metadata_file(name) or is_image_file(name)):
            return True
    return False

def download_related_files(json_structure, video_name, base_url, full_path, current_path):
    base_name = video_name.rsplit('.', 1)[0]
    with ThreadPoolExecutor(max_workers=user_config['download_threads']) as executor:
        futures = []
        for name, item in json_structure.items():
            if (is_subtitle_file(name) or is_metadata_file(name) or is_image_file(name)) and name.startswith(base_name):
                futures.append(executor.submit(download_file, base_url, current_path, name, full_path))

        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logger.error(f"下载相关文件时出错: {e}")

def download_file(base_url, current_path, name, full_path):
    file_path = full_path / name

    if file_path.exists():
        return

    encoded_file_path = urllib.parse.quote((Path(current_path) / name).as_posix(), safe='')
    file_url = base_url + encoded_file_path

    try:
        response = requests_retry_session().get(file_url, stream=True)
        response.raise_for_status()

        with open(file_path, 'wb') as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
    except Exception as e:
        logger.error(f"下载文件时出错: {e}")

def check_path_exists(path):
    return Path(path).exists()

def check_and_delete_invalid_links(json_structure, target_directory, current_path=''):
    global total_valid_count, total_invalid_count

    video_files_set = set()

    def collect_video_files(json_structure, current_path):
        for name, item in json_structure.items():
            if isinstance(item, dict) and item.get('type') == 'file' and is_video_file(name):
                video_files_set.add((Path(current_path) / name).stem)
            elif isinstance(item, dict) and item.get('type') != 'file':
                collect_video_files(item, (Path(current_path) / name).as_posix())

    collect_video_files(json_structure, current_path)

    for root, dirs, files in os.walk(Path(target_directory) / current_path, topdown=False):
        for file in files:
            if file.endswith('.strm'):
                strm_path = Path(root) / file
                video_filename = strm_path.stem

                if video_filename not in video_files_set:
                    strm_path.unlink()
                    total_invalid_count += 1

        for dir in dirs:
            dir_path = Path(root) / dir
            if not any(f.suffix == '.strm' for f in dir_path.rglob('*')):
                try:
                    shutil.rmtree(dir_path)
                except Exception as e:
                    logger.error(f"删除目录 {dir_path} 时出错: {e}")

    for root, dirs, files in os.walk(Path(target_directory) / current_path, topdown=False):
        for file in files:
            if file.endswith('.strm'):
                total_valid_count += 1

def delete_directory_contents(directory):
    if not check_path_exists(directory):
        logger.error(f"目录不存在: {directory}")
        return

    try:
        for item in Path(directory).iterdir():
            if item.is_dir():
                delete_directory_contents(item)
                item.rmdir()
            else:
                item.unlink()
    except Exception as e:
        logger.error(f"删除目录内容时出错: {e}")

def process_config(config_id):
    try:
        cursor.execute('SELECT * FROM config WHERE id=?', (config_id,))
        config = cursor.fetchone()

        if config is None:
            logger.error(f"未找到ID为{config_id}的配置")
            return

        id, name, root_path, site_url, target_directory, ignored_directories_str, token, update_existing = config
        ignored_directories = [d.strip() for d in ignored_directories_str.split(',') if d.strip()]

        # 验证配置项
        validate_config(root_path, site_url, target_directory, ignored_directories)

        logger.info(f"正在运行配置文件：{name}")
        logger.info(f"目标目录路径: {target_directory}")
        logger.info('记得去alist把设置中的签名关闭，否则链接无法访问')

        json_structure = {}
        base_url = site_url + '/d' + urllib.parse.quote(root_path) + '/'
        api_base_url = site_url + '/api'
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

        traverse_directory(root_path, json_structure, api_base_url, token, user_agent, ignored_directories)

        # 修正部分，将 base_dir 替换为 db_dir
        temp_file = db_dir / 'directory_tree.json'
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(json_structure, f, ensure_ascii=False, indent=4)
        logger.info('正在创建alist目录树')

        with open(temp_file, 'r', encoding='utf-8') as f:
            json_structure = json.load(f)
        logger.info('正在创建本地目录树')

        if user_config['enable_invalid_link_check']:
            check_and_delete_invalid_links(json_structure, target_directory)
            logger.info('正在检测strm文件链接有效性')

        create_strm_files(json_structure, target_directory, base_url, update_existing)

        logger.info(f"配置 {name} 下的strm文件已经创建完成")
    except ValueError as e:
        logger.error(f"配置项错误: {e}")
        sys.exit(1)
    except sqlite3.Error as e:
        logger.error(f"处理配置时出错: {e}")
        sys.exit(1)


def main():
    logger.info('脚本运行中。。。。。。。')

    if len(sys.argv) < 2:
        logger.error("请提供配置ID作为命令行参数")
        return

    config_id = sys.argv[1]
    try:
        process_config(config_id)
        logger.info(f'有效的 strm 文件总数量: {total_valid_count}')
        logger.info(f'删除的 strm 文件总数量: {total_invalid_count}')
        logger.info(f'本次运行创建的 strm 文件总数量: {total_created_count}')
        logger.info('所有strm文件创建完成')
    except Exception as e:
        if "无效的token" in str(e):
            logger.error("无效的token，脚本将终止运行")
        else:
            logger.error(f"脚本运行过程中发生错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
