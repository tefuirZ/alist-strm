import random
import sys
import easywebdav
import json
import os
from urllib.parse import unquote
import requests
import time
from queue import Queue
from db_handler import DBHandler
from logger import setup_logger



# 初始化全局计数器
strm_file_counter = 0  # 总的 strm 文件数量
video_file_counter = 0  # 总的视频文件数量
download_file_counter = 0  # 已下载的文件数量
total_download_file_counter = 0  # 总共需要下载的文件数量
directory_strm_file_counter = {}  # 每个子目录下创建的 strm 文件数量
existing_strm_file_counter = 0  # 已存在的 .strm 文件数量
download_queue = Queue()  # 下载队列
found_video_files = set()

# 连接WebDAV服务器
def connect_webdav(config):
    return easywebdav.connect(
        host=config['host'],
        port=config['port'],
        username=config['username'],
        password=config['password'],
        protocol=config['protocol']
    )
    pass


def load_cached_tree(config_id):
    # 确保 cache 目录存在
    cache_dir = 'cache'
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)  # 自动创建 cache 目录

    # 设置缓存文件路径
    cache_file = os.path.join(cache_dir, f'webdav_directory_cache_{config_id}.json')

    # 加载缓存文件
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.info(f"加载缓存文件出错: {e}")
    return None
    pass


def save_tree_to_cache(file_tree, config_id):
    # 确保 cache 目录存在
    cache_dir = 'cache'
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)  # 自动创建 cache 目录

    # 设置缓存文件路径
    cache_file = os.path.join(cache_dir, f'webdav_directory_cache_{config_id}.json')

    # 保存缓存文件
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(file_tree, f, ensure_ascii=False, indent=4)
        logger.info(f"目录树缓存文件 '{cache_file}' 保存成功。")
    except Exception as e:
        logger.info(f"保存目录树缓存文件出错: {e}")
    pass

# 比较两个目录树，如果相同返回 True，否则返回 False
def compare_directory_trees(cached_tree, current_tree):
    if len(cached_tree) != len(current_tree):
        return False
    for cached_file, current_file in zip(cached_tree, current_tree):
        if cached_file['name'] != current_file['name'] or \
           cached_file['size'] != current_file['size'] or \
           cached_file['modified'] != current_file['modified']:
            return False
    return True
    pass





def list_files_recursive_with_cache(webdav, directory, config, script_config, size_threshold, visited=None):
    global video_file_counter, strm_file_counter, directory_strm_file_counter, total_download_file_counter
    decoded_directory = unquote(directory)

    if visited is None:
        visited = set()

    # 检查是否已经访问过该目录，避免循环递归
    if directory in visited:
        return []

    visited.add(directory)

    try:
        logger.info(f"尝试遍历目录: {decoded_directory}")
        files = webdav.ls(directory)  # 列出 WebDAV 中的文件
        file_tree = []

        # 解码URL编码的目录名称，确保中文正常显示

        # 处理本地目录路径，去掉 WebDAV 上的根目录部分
        local_relative_path = decoded_directory.replace(config['rootpath'], '').lstrip('/')
        local_directory = os.path.join(config['target_directory'], local_relative_path)
        os.makedirs(local_directory, exist_ok=True)  # 确保本地目录存在

        # 初始化该目录的 strm 文件计数器
        directory_strm_file_counter[decoded_directory] = 0

        for f in files:
            decoded_file_name = unquote(f.name)
            decoded_name = unquote(f.name)  # 解码文件或文件夹名称
            is_directory = f.name.endswith('/')
            file_info = {
                'name': decoded_name,  # 使用解码后的名称
                'size': f.size,
                'modified': f.mtime,
                'is_directory': is_directory,
                'children': [] if is_directory else None  # 如果是文件夹，初始化children为空列表
            }

            # 如果是文件夹，递归获取其子文件
            if is_directory:
                file_info['children'] = list_files_recursive_with_cache(webdav, f.name, config, script_config, size_threshold, visited)
            else:
                file_extension = os.path.splitext(f.name)[1].lower().lstrip('.')

                # 根据不同格式执行不同操作
                if file_extension in script_config['video_formats']:

                    logger.info(f"找到视频文件: {decoded_file_name}")
                    video_file_counter += 1  # 增加视频文件计数
                    create_strm_file(f.name, f.size, config, script_config['video_formats'], local_directory,
                                     decoded_directory, size_threshold)
                    # 全量更新时，直接创建 strm 文件，传入文件大小和阈值



                elif (
                        file_extension in script_config['subtitle_formats'] or \
                     file_extension in script_config['image_formats'] or \
                     file_extension in script_config['metadata_formats']):
                    logger.info(f"找到下载文件: {decoded_file_name}")

                    total_download_file_counter += 1  # 记录需要下载的文件总数
                    # 将下载任务加入队列（无需创建线程）
                    download_queue.put((webdav, f.name, local_directory, f.size, config))

            file_tree.append(file_info)

        return file_tree
    except Exception as e:
        logger.info(f"Error listing files: {e}")
        return []





def download_files_with_interval(min_interval, max_interval):
    global download_file_counter, total_download_file_counter
    while not download_queue.empty():
        webdav, file_name, local_path, expected_size, config = download_queue.get()
        try:
            download_file(webdav, file_name, local_path, expected_size, config)
        finally:
            download_file_counter += 1
            logger.info(f"文件下载进度: {download_file_counter}/{total_download_file_counter}")
            download_queue.task_done()

        # 使用从数据库读取的随机下载间隔范围
        interval = random.randint(min_interval, max_interval)
        time.sleep(interval)



def create_strm_file(file_name, file_size, config, video_formats, local_directory, directory, size_threshold):
    global strm_file_counter, directory_strm_file_counter, existing_strm_file_counter
    size_threshold_bytes = size_threshold * (1024 * 1024)

    # 获取文件扩展名并判断是否生成strm文件
    file_extension = os.path.splitext(file_name)[1].lower().lstrip('.')
    if file_extension not in video_formats:
        decoded_name = unquote(file_name)
        logger.info(f"跳过文件: {decoded_name}（不是视频格式）")
        return

    # 如果视频文件大小小于用户设定的阈值，则跳过创建
    if file_size < size_threshold_bytes:
        decoded_name = unquote(file_name)
        logger.info(f"跳过生成 .strm 文件: {decoded_name}（文件大小小于 {size_threshold } MB）")
        return

    clean_file_name = file_name.replace('/dav', '')  # 去掉 /dav/ 前缀
    # 根据 protocol 参数生成相应的链接，http 或 https
    http_link = f"{config['protocol']}://{config['host']}:{config['port']}/d{clean_file_name}"

    decoded_file_name = unquote(file_name).replace('/dav/', '')  # 解码为中文
    strm_file_name = os.path.splitext(os.path.basename(decoded_file_name))[0] + ".strm"
    strm_file_path = os.path.join(local_directory, strm_file_name)

    # 检查本地是否已存在 .strm 文件
    if os.path.exists(strm_file_path):
        logger.info(f"跳过生成 .strm 文件: {strm_file_path}（本地已存在）")
        existing_strm_file_counter += 1  # 计数已存在的 .strm 文件

        return

    try:
        logger.info(f"创建 .strm 文件: {strm_file_path}")
        with open(strm_file_path, 'w', encoding='utf-8') as strm_file:
            strm_file.write(http_link)  # 写入链接
            decoded_name = unquote(strm_file_path)
        logger.info(f".strm 文件已创建: {decoded_name}")

        # 更新计数器
        strm_file_counter += 1
        directory_strm_file_counter[directory] += 1  # 更新子目录下的 strm 文件数量
    except Exception as e:
        logger.info(f"创建 .strm 文件时出错: {file_name}，错误: {e}")
    pass


# 下载文件并检查本地是否已存在
def download_file(webdav, file_name, local_path, expected_size, config):
    global download_file_counter, total_download_file_counter


    # 检查是否允许下载文件
    if config.get('download_enabled', 1) == 0:
        logger.info(f"下载功能已禁用，跳过下载文件: {file_name}")
        return

    try:
        # 本地文件路径，解码为中文文件名
        local_file_path = os.path.join(local_path, os.path.basename(unquote(file_name)))

        # 如果文件已存在，跳过下载
        if os.path.exists(local_file_path):
            logger.info(f"跳过文件下载: {local_file_path}（本地已存在）")
            return

        clean_file_name = file_name.replace('/dav', '')
        # 根据协议动态生成下载链接
        file_url = f"{config['protocol']}://{config['host']}:{config['port']}/d{clean_file_name}"

        logger.info(f"正在下载文件: {file_url}")
        response = requests.get(file_url, auth=(config['username'], config['password']), stream=True, allow_redirects=True)

        if response.status_code == 200:
            with open(local_file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info(f"文件下载成功: {local_file_path}")
        else:
            logger.info(f"下载失败: {file_name}，状态码: {response.status_code}")

        # 校验文件大小是否匹配
        actual_size = os.path.getsize(local_file_path)
        if actual_size == expected_size:
            logger.info(f"文件已成功下载: {local_file_path}（大小: {actual_size} 字节）")
            download_file_counter += 1
            logger.info(f"文件下载进度: {download_file_counter}/{total_download_file_counter}")
        else:
            logger.info(f"文件大小不匹配: {local_file_path}。预期: {expected_size}，实际: {actual_size}")
            os.remove(local_file_path)
    except Exception as e:
        logger.info(f"下载文件时出错: {file_name}，错误: {e}")
    pass

def process_with_cache(webdav, config, script_config, config_id, size_threshold):
    global video_file_counter, strm_file_counter, download_file_counter, total_download_file_counter

    cached_tree = load_cached_tree(config_id)

    root_directory = config['rootpath']
    current_tree = list_files_recursive_with_cache(webdav, root_directory, config, script_config, size_threshold)

    if config.get('update_mode') == 'incremental':
        logger.info("正在执行增量更新...")

        if cached_tree and compare_directory_trees(cached_tree, current_tree):
            logger.info("本地目录树与云端一致，跳过更新。")
            if config.get('download_enabled', 1) == 0:
                logger.info("下载功能已禁用，程序即将退出。")
                sys.exit(0)
        else:
            logger.info("目录树发生变化，进行增量更新。")

            save_tree_to_cache(current_tree, config_id)

    elif config.get('update_mode') == 'full':
        logger.info("正在执行全量更新...")

        save_tree_to_cache(current_tree, config_id)  # 保存全量更新后的目录树到缓存
    logger.info(f"总共创建了 {strm_file_counter} 个 .strm 文件")
    logger.info(f"总共发现了 {video_file_counter} 个视频文件")
    logger.info(f"总共需要下载 {total_download_file_counter} 个文件")

    if config.get('download_enabled', 1) == 0:
        logger.info("下载功能已禁用，跳过所有下载任务。程序即将退出。")
        sys.exit(0)

    # 传递下载间隔范围（最小值和最大值）
    min_interval, max_interval = config['download_interval_range']
    download_files_with_interval(min_interval, max_interval)

    logger.info(f"总共下载了 {download_file_counter} 个文件")


if __name__ == '__main__':
    db_handler = DBHandler()

    config_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    task_id = sys.argv[2] if len(sys.argv) > 2 else None  # 获取任务ID，如果存在

    # 设置日志
    if task_id:
        logger, log_file = setup_logger('config_' + str(config_id), task_id=task_id)
    else:
        logger, log_file = setup_logger('config_' + str(config_id))

    try:
        # 初始化数据库并获取配置
        db_handler.initialize_tables()
        config = db_handler.get_webdav_config(config_id)

        # 检查配置是否有效
        if not config:
            logger.error(f"无法获取配置ID {config_id} 的配置，程序终止。")
            sys.exit(1)

        # 输出配置信息到日志
        logger.info(
            f"正在使用配置ID: {config_id} 运行，目标地址: {config['protocol']}://{config['host']}:{config['port']}")

        # 获取视频、图片等格式和大小阈值
        script_config = db_handler.get_script_config()

        # 检查脚本配置是否有效
        if not script_config or 'video_formats' not in script_config or 'size_threshold' not in script_config:
            logger.error(f"脚本配置出错，缺少必要的配置项，程序终止。")
            sys.exit(1)

        # 连接 WebDAV 服务器
        try:
            webdav = connect_webdav(config)
        except Exception as e:
            logger.error(f"连接 WebDAV 服务器时出错: {e}")
            sys.exit(1)

        # 使用缓存策略处理文件，并传递 size_threshold
        try:
            process_with_cache(webdav, config, script_config, config_id, script_config['size_threshold'])
        except Exception as e:
            logger.error(f"处理文件时发生错误: {e}")
            sys.exit(1)

        logger.info("文件处理完成！")

    except Exception as e:
        logger.error(f"运行过程中出现未捕获的异常: {e}")

    finally:
        db_handler.close()

