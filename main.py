import os
import sqlite3
import urllib
from time import sleep
import requests
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import sys
from pathlib import Path

# 配置日志记录器
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 获取脚本文件所在的目录
base_dir = Path(__file__).resolve().parent

# 确保数据库路径存在
db_dir = base_dir / 'instance'
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
    url_list = api_base_url + "/fs/list"
    payload_list = {
        "path": path,
        "password": "",
        "page": 1,
        "per_page": 0,
        "refresh": False
    }
    headers_list = {
        'Authorization': token,
        'User-Agent': user_agent,
        'Content-Type': 'application/json'
    }
    response_list = requests_retry_session().post(url_list, headers=headers_list, json=payload_list)
    response_list.raise_for_status()  # 确保请求成功

    try:
        return response_list.json()
    except requests.exceptions.JSONDecodeError as e:
        logger.error(f"JSON解析错误: {e}")
        logger.error(f"响应内容: {response_list.text}")
        return {}

def traverse_directory(path, json_structure, base_url, api_base_url, target_directory, token, user_agent, root_path, ignored_directories, is_root=True):
    directory_info = list_directory(path, api_base_url, token, user_agent)
    if directory_info.get('data') and directory_info['data'].get('content'):
        for item in directory_info['data']['content']:
            if item['name'] in ignored_directories:
                logger.info(f"跳过被忽略的目录: {item['name']}")
                continue

            if item['is_dir']:
                new_path = os.path.join(path, item['name'])
                sleep(5)  # 为了避免请求过快被服务器限制
                new_json_object = {}
                json_structure[item['name']] = new_json_object
                traverse_directory(new_path, new_json_object, base_url, api_base_url, target_directory, token, user_agent, root_path, ignored_directories, is_root=False)
            elif is_video_file(item['name']) or is_subtitle_file(item['name']):
                json_structure[item['name']] = {
                    'type': 'file',
                    'size': item['size'],
                    'modified': item['modified'],
                    'sign': item['sign']
                }

    if not is_root:  # 如果不是根目录，表示已达到末端，开始写入 .strm 文件
        relative_path = Path(path).relative_to(root_path).as_posix()  # 获取相对于 root_path 的相对路径，并转换为 POSIX 风格
        create_strm_files(json_structure, target_directory, base_url, relative_path)

def is_video_file(filename):
    video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.ts']  # 添加更多的视频格式
    return any(filename.lower().endswith(ext) for ext in video_extensions)

def is_subtitle_file(filename):
    subtitle_extensions = ['.srt', '.ass', '.ssa', '.vtt']  # 添加更多的字幕格式
    return any(filename.lower().endswith(ext) for ext in subtitle_extensions)

def create_strm_files(json_structure, target_directory, base_url, current_path=''):
    for name, item in json_structure.items():
        full_path = Path(target_directory) / current_path
        if isinstance(item, dict) and item.get('type') == 'file':
            if not item.get('created'):
                if is_video_file(name):
                    strm_filename = name.rsplit('.', 1)[0] + '.strm'
                    strm_path = full_path / strm_filename

                    # 检查是否已存在同名的.strm文件
                    if strm_path.exists():
                        logger.info(f"{strm_path} 已存在，跳过创建。")
                        continue

                    # 确保目录存在
                    full_path.mkdir(parents=True, exist_ok=True)
                    encoded_file_path = urllib.parse.quote((Path(current_path) / name).as_posix())

                    # 获取文件签名
                    sign = item.get('sign')
                    if not sign:
                        logger.error(f"未找到文件 {name} 的签名")
                        continue

                    video_url = base_url + encoded_file_path + "?sign=" + sign
                    item['created'] = True
                    with open(strm_path, 'w', encoding='utf-8') as strm_file:
                        strm_file.write(video_url)
                        logger.info(f"{strm_path} 已创建。")

                    # 下载字幕文件
                    download_subtitle_files(json_structure, name, base_url, full_path, current_path)
        elif isinstance(item, dict):  # 如果是一个目录，递归处理
            new_directory = full_path / name
            new_directory.mkdir(parents=True, exist_ok=True)
            create_strm_files(item, target_directory, base_url, (Path(current_path) / name).as_posix())

def download_subtitle_files(json_structure, video_name, base_url, full_path, current_path):
    base_name = video_name.rsplit('.', 1)[0]
    for name, item in json_structure.items():
        if is_subtitle_file(name) and name.startswith(base_name):
            subtitle_path = full_path / name

            # 检查是否已存在同名的字幕文件
            if subtitle_path.exists():
                logger.info(f"{subtitle_path} 已存在，跳过下载。")
                continue

            encoded_file_path = urllib.parse.quote((Path(current_path) / name).as_posix())
            subtitle_url = base_url + encoded_file_path

            response = requests_retry_session().get(subtitle_url)
            response.raise_for_status()

            with open(subtitle_path, 'wb') as subtitle_file:
                subtitle_file.write(response.content)
                logger.info(f"{subtitle_path} 已下载。")

def process_config(config_id):
    # 从数据库中读取配置信息
    cursor.execute('SELECT * FROM config WHERE id=?', (config_id,))  # 确保表名是正确的
    config = cursor.fetchone()

    if config is None:
        logger.error(f"未找到ID为{config_id}的配置")
        return

    id, name, root_path, site_url, target_directory, ignored_directories_str, token, update_existing = config
    ignored_directories = [d.strip() for d in ignored_directories_str.split(',') if d.strip()]
    logger.info(f"正在运行配置文件：{name} ")
    # 打印目标目录路径以进行调试
    logger.info(f"目标目录路径: {target_directory}")

    # 初始化JSON结构体并进行目录遍历
    json_structure = {}

    # 组装基础URL用于访问视频文件
    base_url = site_url + '/d' + root_path + '/'
    api_base_url = site_url + '/api'
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0"

    traverse_directory(root_path, json_structure, base_url, api_base_url, target_directory, token, user_agent, root_path, ignored_directories)

    # 确保目标文件夹存在
    Path(target_directory).mkdir(parents=True, exist_ok=True)

    # 创建 .strm 文件
    create_strm_files(json_structure, target_directory, base_url)

    logger.info(f"配置 {name} 下的strm文件已经创建完成")

def main():
    logger.info('脚本运行中。。。。。。。')

    # 从命令行参数获取配置ID
    if len(sys.argv) < 2:
        logger.error("请提供配置ID作为命令行参数")
        return

    config_id = sys.argv[1]
    # 处理配置
    process_config(config_id)

    logger.info('所有strm文件创建完成')
    logger.info('热知识：')
    logger.info('')

if __name__ == "__main__":
    main()
