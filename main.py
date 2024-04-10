import urllib
from time import sleep
import requests
import json
import configparser
import os
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# 创建配置解析器
config = configparser.ConfigParser()

# 指定以 UTF-8 编码方式读取配置文件
with open('config.ini', 'r', encoding='utf-8') as configfile:
    config.read_file(configfile)


# 使用 get 方法从配置文件中获取配置值。第一个参数是段名，第二个参数是键名。
root_path = config.get('DEFAULT', 'RootPath', fallback="/path/to/root")
site_url = config.get('DEFAULT', 'SiteUrl', fallback='www.tefuir0829.cn')
target_directory = config.get('DEFAULT', 'TargetDirectory', fallback='E:\\cloud\\')
username = config.get('DEFAULT', 'Username', fallback='admin')
password = config.get('DEFAULT', 'Password', fallback='password')

api_base_url = site_url + "/api"
UserAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0"
login_path = "/auth/login"
url_login = api_base_url + login_path
traversed_paths = []

payload_login = json.dumps({
    "username": username,
    "password": password
})

headers_login = {
    'User-Agent': UserAgent,
    'Content-Type': 'application/json'
}


response_login = requests.post(url_login, headers=headers_login, data=payload_login)
token = json.loads(response_login.text)['data']['token']


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
    try:
        response_list = requests_retry_session().post(url_list, headers=headers_list, data=payload_list)
        return json.loads(response_list.text)

    except Exception as x:
        print(f"遇到错误: {x.__class__.__name__}")
        print("正在重试...")
        sleep(5)
    response_list = requests.post(url_list, headers=headers_list, data=payload_list)
    return json.loads(response_list.text)



def traverse_directory(path, json_structure):
    print(f"正在遍历文件夹: {path}")  # 添加这一行来输出当前正在遍历的文件夹路径
    directory_info = list_directory(path)
    if directory_info.get('data') and directory_info['data'].get('content'):
        for item in directory_info['data']['content']:
            if item['is_dir']:  # 如果是文件夹
                new_path = os.path.join(path, item['name'])  # 使用 os.path.join 确保路径格式正确
                sleep(1)
                if new_path in traversed_paths:
                    continue
                traversed_paths.append(new_path)
                new_json_object = {}
                json_structure[item['name']] = new_json_object
                traverse_directory(new_path, new_json_object)  # 递归调用以遍历子文件夹
            elif is_video_file(item['name']):  # 如果是视频文件
                json_structure[item['name']] = {
                    'type': 'file',
                    'size': item['size'],
                    'modified': item['modified']
                }

def is_video_file(filename):
    video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv']  # 添加更多的视频格式
    return any(filename.lower().endswith(ext) for ext in video_extensions)


def create_strm_files(json_structure, target_directory, base_url, current_path=''):
    for name, item in json_structure.items():
        if isinstance(item, dict) and item.get('type') == 'file' and is_video_file(name):
            strm_filename = name.rsplit('.', 1)[0] + '.strm'
            strm_path = os.path.join(target_directory, current_path, strm_filename)

            # 对整个文件路径进行URL编码
            encoded_file_path = urllib.parse.quote(os.path.join(current_path.replace('\\', '/'), name))

            # 拼接完整的视频URL
            video_url = base_url + encoded_file_path

            with open(strm_path, 'w', encoding='utf-8') as strm_file:
                strm_file.write(video_url)
        elif isinstance(item, dict):  # 如果是一个目录，递归处理
            new_directory = os.path.join(target_directory, current_path, name)
            os.makedirs(new_directory, exist_ok=True)
            create_strm_files(item, target_directory, base_url, os.path.join(current_path, name))



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

def main():

    print('脚本运行中。。。。。。。')
    json_structure = {}
    traverse_directory(root_path, json_structure)

    # 修改后的目标文件夹路径

    os.makedirs(target_directory, exist_ok=True)  # 确保目标文件夹存在

    # 假设固定的视频直链是 'http://a.c.com/d/'
    base_url = site_url + '/d' + root_path + '/'
    sleep(10)
    # 创建 .strm 文件之前打印 json_structure 确认结构
    print('所有strm文件创建完成')
    print('热知识：')
    print('strm文件可以直接在tmm挂削哦')
    print('感谢使用，使用中有任何问题欢迎留言')
    print('博客地址：www.tefuir0829.cn')

    # 创建 .strm 文件
    create_strm_files(json_structure, target_directory, base_url)

    # 如果需要，可以将 json_structure 写入到 JSON 文件中
    with open('directory_structure.json', 'w') as f:
        json.dump(json_structure, f, indent=4)

if __name__ == '__main__':
    main()