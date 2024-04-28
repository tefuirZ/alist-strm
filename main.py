import urllib
from time import sleep
import requests
import configparser
import os
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import concurrent.futures
import sys



# 创建配置解析器
config = configparser.ConfigParser()

# 指定以 UTF-8 编码方式读取配置文件
with open('config.ini', 'r', encoding='utf-8') as configfile:
    config.read_file(configfile)

# 使用 get 方法从配置文件中获取配置值。第一个参数是段名，第二个参数是键名。
root_path = config.get('DEFAULT', 'RootPath', fallback="/path/to/root")
site_url = config.get('DEFAULT', 'SiteUrl', fallback='www.tefuir0829.cn')
target_directory = config.get('DEFAULT', 'TargetDirectory', fallback='E:\\cloud\\')
ignored_directories_str = config.get('DEFAULT', 'IgnoredDirectories', fallback='')
ignored_directories = [d.strip() for d in ignored_directories_str.split(',') if d.strip()]
token = config.get('DEFAULT', 'Token')  # 从配置文件读取固定的Token

api_base_url = site_url + "/api"
UserAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0"

traversed_paths = []



logger = logging.getLogger(__name__)
main_log_file_path = './log/main.log'  # main.py日志保存路径
main_logger = logging.getLogger(__name__)
main_logger.setLevel(logging.INFO)
main_handler = logging.FileHandler(main_log_file_path)
main_logger.addHandler(main_handler)

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


def list_directory(path):
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
        'User-Agent': UserAgent,
        'Content-Type': 'application/json'
    }
    response_list = requests_retry_session().post(url_list, headers=headers_list, json=payload_list)
    return response_list.json()


def traverse_directory(path, json_structure, base_url, target_directory, is_root=True):
    directory_info = list_directory(path)
    if directory_info.get('data') and directory_info['data'].get('content'):
        for item in directory_info['data']['content']:
            if item['name'] in ignored_directories:
                logger.info(f"跳过被忽略的目录: {item['name']}")
                continue

            if item['is_dir']:
                new_path = os.path.join(path, item['name'])
                sleep(5)  # 为了避免请求过快被服务器限制
                if new_path in traversed_paths:
                    continue
                traversed_paths.append(new_path)
                new_json_object = {}
                json_structure[item['name']] = new_json_object
                traverse_directory(new_path, new_json_object, base_url, target_directory, is_root=False)
            elif is_video_file(item['name']):
                json_structure[item['name']] = {
                    'type': 'file',
                    'size': item['size'],
                    'modified': item['modified']
                }

    if not is_root:  # 如果不是根目录，表示已达到末端，开始写入 .strm 文件
        create_strm_files(json_structure, target_directory, base_url,
                          path.replace(root_path, '').strip('/').replace('/', os.sep))


def is_video_file(filename):
    video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv']  # 添加更多的视频格式
    return any(filename.lower().endswith(ext) for ext in video_extensions)


def create_strm_files(json_structure, target_directory, base_url, current_path=''):
    for name, item in json_structure.items():
        full_path = os.path.join(target_directory, current_path)
        if isinstance(item, dict) and item.get('type') == 'file':
            if not item.get('created'):
                strm_filename = name.rsplit('.', 1)[0] + '.strm'
                strm_path = os.path.join(full_path, strm_filename)

                # 检查是否已存在同名的.strm文件
                if os.path.exists(strm_path):
                    logger.info(f"{strm_path} 已存在，跳过创建。")
                    continue

                # 确保目录存在
                os.makedirs(full_path, exist_ok=True)
                encoded_file_path = urllib.parse.quote(os.path.join(current_path.replace('\\', '/'), name))
                video_url = base_url + encoded_file_path
                item['created'] = True
                with open(strm_path, 'w', encoding='utf-8') as strm_file:
                    strm_file.write(video_url)
                    logger.info(f"{strm_path} 已创建。")
        elif isinstance(item, dict):  # 如果是一个目录，递归处理
            new_directory = os.path.join(full_path, name)
            os.makedirs(new_directory, exist_ok=True)
            create_strm_files(item, target_directory, base_url, os.path.join(current_path, name))


def process_config(config_file):
    # 创建配置解析器
    logger.info('脚本运行中,正在处理' +config_file)
    config = configparser.ConfigParser()

    # 使用 get 方法从配置文件中获取配置值。第一个参数是段名，第二个参数是键名。
    with open(config_file, 'r', encoding='utf-8') as configfile:
        config.read_file(configfile)

    # 从配置文件中读取配置信息
    root_path = config.get('DEFAULT', 'RootPath', fallback="/path/to/root")
    site_url = config.get('DEFAULT', 'SiteUrl', fallback='www.tefuir0829.cn')
    target_directory = config.get('DEFAULT', 'TargetDirectory', fallback='E:\\cloud\\')
    ignored_directories_str = config.get('DEFAULT', 'IgnoredDirectories', fallback='')
    ignored_directories = [d.strip() for d in ignored_directories_str.split(',') if d.strip()]
    token = config.get('DEFAULT', 'Token')  # 从配置文件读取固定的Token

    # 其他全局变量和函数的定义...

    # 初始化JSON结构体并进行目录遍历
    json_structure = {}

    # 组装基础URL用于访问视频文件
    base_url = site_url + '/d' + root_path + '/'

    traverse_directory(root_path, json_structure, base_url, target_directory)

    # 修改后的目标文件夹路径
    os.makedirs(target_directory, exist_ok=True)  # 确保目标文件夹存在

    # 创建 .strm 文件
    create_strm_files(json_structure, target_directory, base_url)

    logger.info(f"配置文件 {config_file} 下的strm文件已经创建完成")

def main():
    global ignored_directories


    # 从命令行参数获取配置文件列表
    config_files = sys.argv[1:]

    # 检查是否提供了配置文件
    if not config_files:
        logger.error("请提供至少一个配置文件路径作为命令行参数")
        return

    # 并发处理每个配置文件
    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.map(process_config, config_files)

    logger.info('所有strm文件创建完成')
    logger.info('热知识：')
    logger.info('strm文件可以直接在tmm挂削哦')
    logger.info('感谢使用，使用中有任何问题欢迎留言')
    logger.info('博客地址：www.tefuir0829.cn')

if __name__ == '__main__':
    main()
