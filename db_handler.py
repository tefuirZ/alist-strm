import os
import sqlite3
from urllib.parse import urlparse
import  uuid
from urllib.parse import urlparse

class DBHandler:
    def __init__(self, db_file=None):
        # 如果 db_file 为空，则从环境变量中读取或使用默认值 '/config/config.db'
        self.db_file = db_file or os.getenv('DB_FILE', '/config/config.db')
        # 使用 check_same_thread=False 允许跨线程访问
        self.conn = sqlite3.connect(self.db_file, check_same_thread=False)
        self.cursor = self.conn.cursor()
        # 初始化表结构
        self.initialize_tables()


    def initialize_tables(self):
        # 初始化 config 表，添加 config_name 用于前端展示
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS config (
                                config_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                                config_name TEXT,  -- 配置名称，用于前端展示
                                url TEXT, 
                                username TEXT, 
                                password TEXT, 
                                rootpath TEXT,
                                target_directory TEXT,
                                download_enabled INTEGER DEFAULT 1,
                                download_interval_range TEXT
                                )''')

        # 初始化 user_config 表，用于存储脚本的全局配置
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS user_config (
                                video_formats TEXT,
                                subtitle_formats TEXT,
                                image_formats TEXT,
                                metadata_formats TEXT,
                                size_threshold INTEGER DEFAULT 100)''')



        self.conn.commit()

        # 动态检查并添加缺少的列
        self.add_column_if_not_exists('config', 'config_name', 'TEXT')  # 添加 'config_name' 列
        self.add_column_if_not_exists('config', 'url', 'TEXT')
        self.add_column_if_not_exists('config', 'download_enabled', 'INTEGER', default_value=1)
        self.add_column_if_not_exists('config', 'target_directory', 'TEXT')
        self.add_column_if_not_exists('config', 'update_mode', 'TEXT')
        self.add_column_if_not_exists('config', 'download_interval_range', 'TEXT', default_value='1-3')
        self.add_column_if_not_exists('user_config', 'size_threshold', 'INTEGER', default_value=100)
        self.add_column_if_not_exists('user_config', 'username', 'TEXT')
        self.add_column_if_not_exists('user_config', 'password', 'TEXT')

        # 如果 user_config 表为空，插入默认值
        self.insert_default_user_config()

    def add_column_if_not_exists(self, table_name, column_name, column_type, default_value=None):
        """
        检查表中是否存在某个列，如果不存在则添加它。
        """
        self.cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [column[1] for column in self.cursor.fetchall()]  # 获取所有列的名字

        if column_name not in columns:
            # 添加缺少的列，不指定默认值
            alter_query = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            self.cursor.execute(alter_query)
            self.conn.commit()
            print(f"列 '{column_name}' 已添加到 '{table_name}' 表中。")

            # 如果有默认值，手动更新该列的所有记录为默认值
            if default_value is not None:
                update_query = f"UPDATE {table_name} SET {column_name} = ?"
                self.cursor.execute(update_query, (default_value,))
                self.conn.commit()
                print(f"列 '{column_name}' 的默认值已设置为 '{default_value}'。")

    def insert_default_user_config(self):
        """
        如果 user_config 表为空，插入默认的脚本配置。
        """
        self.cursor.execute("SELECT COUNT(*) FROM user_config")
        if self.cursor.fetchone()[0] == 0:
            # 默认配置
            default_video_formats = 'mp4,mkv,avi,mov,flv,wmv,ts,m2ts'
            default_subtitle_formats = 'srt,ass,sub'
            default_image_formats = 'jpg,png,bmp'
            default_metadata_formats = 'nfo'
            default_size_threshold = 100  # 直接使用整数而不是字符串
            self.cursor.execute(
                '''INSERT INTO user_config (video_formats, subtitle_formats, image_formats, metadata_formats, size_threshold) 
                   VALUES (?, ?, ?, ?, ?)''',
                (default_video_formats, default_subtitle_formats, default_image_formats, default_metadata_formats,
                 default_size_threshold))
            self.conn.commit()

    def get_all_configurations(self):
                """
                获取所有配置文件的列表
                """
                query = "SELECT config_id, config_name FROM config"
                return self.execute_query(query, fetch_all=True)

    def execute_query(self, query, params=None, fetch_all=False, fetch_one=False):
        """
        通用的执行 SQL 查询的方法。
        :param query: SQL 查询字符串
        :param params: 查询参数 (可选)
        :param fetch_all: 如果为 True，返回所有结果
        :param fetch_one: 如果为 True，返回单个结果
        :return: 查询结果，或 None 如果没有 fetch_all 或 fetch_one
        """
        try:
            if params:
                self.cursor.execute(query, params)
            else:
                self.cursor.execute(query)

            if fetch_all:
                return self.cursor.fetchall()
            if fetch_one:
                return self.cursor.fetchone()

            self.conn.commit()
        except sqlite3.Error as e:
            print(f"SQLite 错误: {e}")
            return None



    def get_all_configurations(self):
        """
        获取所有配置文件的列表
        """
        self.cursor.execute("SELECT config_id, config_name FROM config")
        return self.cursor.fetchall()




    def get_webdav_config(self, config_id):
        self.cursor.execute('''
            SELECT config_name, url, username, password, rootpath, target_directory, download_enabled, update_mode,  download_interval_range
            FROM config
            WHERE config_id=? LIMIT 1
        ''', (config_id,))

        result = self.cursor.fetchone()

        if result:
            config_name, url, username, password, rootpath, target_directory, download_enabled, update_mode, download_interval_range = result
            parsed_url = urlparse(url)

            protocol = parsed_url.scheme
            host = parsed_url.hostname
            port = parsed_url.port if parsed_url.port else (80 if protocol == 'http' else 443)

            if download_enabled is None:
                download_enabled = 1



            # 解析下载间隔范围
            if download_interval_range:
                min_interval, max_interval = map(int, download_interval_range.replace(',', '-').split('-'))
            else:
                min_interval, max_interval = 1, 3  # 默认间隔

            return {
                'config_name': config_name,
                'host': host,
                'port': int(port),
                'username': username,
                'password': password,
                'rootpath': rootpath,
                'protocol': protocol,
                'target_directory': target_directory,
                'download_enabled': download_enabled,
                'update_mode': update_mode,
                'download_interval_range': (min_interval, max_interval)  # 返回最小和最大间隔
            }
        else:
            return None

    def get_script_config(self):
        # 获取脚本的配置（视频、图片、字幕、元数据格式，以及大小阈值）
        self.cursor.execute(
            "SELECT video_formats, subtitle_formats, image_formats, metadata_formats, size_threshold FROM user_config LIMIT 1")
        result = self.cursor.fetchone()

        # 检查是否获取到数据，如果没有获取到，返回默认配置
        if result is None:
            # 插入默认配置，如果数据不存在
            self.insert_default_user_config()
            result = ('mp4,mkv,avi', 'srt,ass,sub', 'jpg,png', 'nfo', 100)  # 默认格式和默认大小阈值

        video_formats, subtitle_formats, image_formats, metadata_formats, size_threshold = result

        # 获取 download_enabled
        self.cursor.execute("SELECT download_enabled FROM config LIMIT 1")
        download_enabled = self.cursor.fetchone()

        # 检查 download_enabled 是否存在
        if download_enabled is None:
            download_enabled = (1,)  # 默认启用下载功能

        # 返回脚本配置
        return {
            'video_formats': video_formats.split(','),
            'subtitle_formats': subtitle_formats.split(','),
            'image_formats': image_formats.split(','),
            'metadata_formats': metadata_formats.split(','),
            'size_threshold': size_threshold,  # 直接返回以MB为单位的大小阈值
            'download_enabled': bool(download_enabled[0])
        }

    def get_user_credentials(self):
        """
        获取存储在 user_config 表中的用户名和密码哈希值。
        """
        self.cursor.execute('SELECT username, password FROM user_config LIMIT 1')
        result = self.cursor.fetchone()
        if result:
            return result[0], result[1]
        else:
            return None, None

    def set_user_credentials(self, username, password_hash):
        """
        设置用户的用户名和密码哈希值。如果记录不存在，则插入；否则更新。
        """
        # 检查 user_config 表中是否有记录
        self.cursor.execute('SELECT COUNT(*) FROM user_config')
        count = self.cursor.fetchone()[0]
        if count == 0:
            # 如果没有记录，插入新记录
            self.cursor.execute('''
                INSERT INTO user_config (username, password) VALUES (?, ?)
            ''', (username, password_hash))
        else:
            # 如果有记录，更新现有记录
            self.cursor.execute('''
                UPDATE user_config SET username = ?, password = ?
            ''', (username, password_hash))
        self.conn.commit()



    def close(self):
        # 关闭数据库连接
        self.conn.close()
