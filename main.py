import urllib
from time import sleep
import requests
import json
import configparser
import os
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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

    response_list = requests_retry_session().post(url_list, headers=headers_list, data=payload_list)
    return json.loads(response_list.text)


def list_directory(path):
    url_list = api_base_url + "/fs/list"
    payload_list = json.dumps({
        "path": path,
        "password": "",
        "page": 1,
        "per_page": 0,
        "refresh": False
    })
    headers_list = {
        'Authorization': token,
        'User-Agent': UserAgent,
        'Content-Type': 'application/json'
    }
    # 使用重试逻辑的目录列表请求
    response_list = requests_retry_session().post(url_list, headers=headers_list, data=payload_list)
    return json.loads(response_list.text)


def traverse_directory(path, json_structure, base_url, target_directory, is_root=True):
    directory_info = list_directory(path)
    if directory_info.get('data') and directory_info['data'].get('content'):
        for item in directory_info['data']['content']:
            if item['name'] in ignored_directories:
                print(f"跳过被忽略的目录: {item['name']}")
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
        # 记录到 JSON 文件
        with open(os.path.join(target_directory, 'directory_structure.json'), 'a', encoding='utf-8') as f:
            json.dump(json_structure, f, indent=4)


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
                # 确保目录存在
                os.makedirs(full_path, exist_ok=True)
                encoded_file_path = urllib.parse.quote(os.path.join(current_path.replace('\\', '/'), name))
                video_url = base_url + encoded_file_path
                item['created'] = True
                with open(strm_path, 'w', encoding='utf-8') as strm_file:
                    strm_file.write(video_url)
                    print(f"{strm_path} 已创建。")
        elif isinstance(item, dict):  # 如果是一个目录，递归处理
            new_directory = os.path.join(full_path, name)
            os.makedirs(new_directory, exist_ok=True)
            create_strm_files(item, target_directory, base_url, os.path.join(current_path, name))


def load_json_structure(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_json_structure(filepath, json_structure):
    with open(filepath, 'a', encoding='utf-8') as f:
        json.dump(json_structure, f, indent=4)


def main():
    global ignored_directories
    print('脚本运行中。。。。。。。')

    # 初始化JSON结构体并进行目录遍历
    json_structure = {}

    # 组装基础URL用于访问视频文件
    base_url = site_url + '/d' + root_path + '/'

    traverse_directory(root_path, json_structure, base_url, target_directory)

    # 修改后的目标文件夹路径

    os.makedirs(target_directory, exist_ok=True)  # 确保目标文件夹存在

    json_structure = load_json_structure('directory_structure.json')

    # 假设固定的视频直链是 'http://a.c.com/d/'
    base_url = site_url + '/d' + root_path + '/'
    sleep(10)

    # 创建 .strm 文件
    create_strm_files(json_structure, target_directory, base_url)

    # 如果需要，可以将 json_structure 写入到 JSON 文件中
    save_json_structure('directory_structure.json', json_structure)

    print('所有strm文件创建完成')
    print('热知识：')
    print('strm文件可以直接在tmm挂削哦')
    print('感谢使用，使用中有任何问题欢迎留言')
    print('博客地址：www.tefuir0829.cn')


if __name__ == '__main__':
    main()
