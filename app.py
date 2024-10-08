import os
import sys
import random
import glob
import json
import subprocess
import zipfile
import requests
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session, g, abort, jsonify
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from db_handler import DBHandler
from logger import setup_logger
from task_scheduler import add_tasks_to_cron, update_tasks_in_cron, delete_tasks_from_cron, list_tasks_in_cron, convert_to_cron_time, run_task_immediately


app = Flask(__name__)
app.secret_key = 'www.tefuir0829.cn'


# 定义图片文件夹路径
IMAGE_FOLDER = 'static/images'


db_handler = DBHandler()

local_version = "6.0.3"



logger, log_file = setup_logger('app')



@app.before_request
def check_user_config():
    # 跳过以下端点的检查
    if request.endpoint in ['login', 'register', 'static', 'random_image']:
        return

    # 确保 user_config 表中有用户名和密码
    username, password = db_handler.get_user_credentials()
    if not username or not password:
        # 重定向到注册页面
        return redirect(url_for('register'))

    # 检查用户是否已登录
    if 'logged_in' not in session:
        return redirect(url_for('login'))

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('请先登录', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # 获取表单数据
        username = request.form['username']
        password = request.form['password']
        # 对密码进行哈希处理
        password_hash = generate_password_hash(password)

        # 存储用户凭证
        db_handler.set_user_credentials(username, password_hash)

        flash('注册成功，请登录', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # 获取表单数据
        username = request.form['username']
        password = request.form['password']

        # 获取存储的用户凭证
        stored_username, stored_password_hash = db_handler.get_user_credentials()

        # 检查用户名和密码
        if username == stored_username and check_password_hash(stored_password_hash, password):
            # 登录成功
            session['logged_in'] = True
            session['username'] = username
            flash('登录成功', 'success')
            return redirect(url_for('index'))
        else:
            flash('用户名或密码错误', 'error')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('您已退出登录', 'success')
    return redirect(url_for('login'))


# 首页
@app.route('/')
@login_required
def index():
    invalid_file_trees = []
    invalid_tree_dir = 'invalid_file_trees'

    if os.path.exists(invalid_tree_dir):
        for json_file in os.listdir(invalid_tree_dir):
            if json_file.endswith('.json'):
                with open(os.path.join(invalid_tree_dir, json_file), 'r', encoding='utf-8') as file:
                    invalid_file_trees.append({
                        'name': json_file,  # 保留完整的文件名，包括 .json
                        'structure': json.load(file)
                    })

    return render_template('home.html', invalid_file_trees=invalid_file_trees)

@app.route('/view_invalid_directory/<path:directory_name>', methods=['GET'])
def view_invalid_directory(directory_name):
    try:
        invalid_file_tree_path = os.path.join('invalid_file_trees', f'{directory_name}.json')
        if not os.path.exists(invalid_file_tree_path):
            return jsonify({"error": "未找到目录树"}), 404

        with open(invalid_file_tree_path, 'r', encoding='utf-8') as file:
            directory_structure = json.load(file)

        # 将目录树返回给前端
        return jsonify({"structure": json.dumps(directory_structure, ensure_ascii=False, indent=4)})
    except Exception as e:
        logger.error(f"查看目录树时出错: {e}")
        return jsonify({"error": "查看目录树时出错"}), 500

def get_target_directory_by_config_id(config_id):
    """
    根据 config_id 从数据库获取 target_directory
    """
    config = db_handler.get_webdav_config(config_id)
    if config:
        return config['target_directory']
    return None

@app.route('/delete_invalid_directory/<path:json_filename>', methods=['POST'])
def delete_invalid_directory(json_filename):
    try:
        # 确保文件名以 'invalid_file_trees_' 开头并以 '.json' 结尾
        if not json_filename.startswith('invalid_file_trees_') or not json_filename.endswith('.json'):
            return jsonify({"error": "无效的文件名"}), 400

        # 从文件名中提取 config_id
        config_id_str = json_filename.replace('invalid_file_trees_', '').replace('.json', '')
        if not config_id_str.isdigit():
            return jsonify({"error": "无效的配置 ID"}), 400

        config_id = int(config_id_str)

        # 从数据库中获取 target_directory
        target_directory = get_target_directory_by_config_id(config_id)
        if not target_directory:
            return jsonify({"error": "未找到对应的配置"}), 404

        # 构建 JSON 文件的路径
        json_file_path = os.path.join('invalid_file_trees', json_filename)
        if not os.path.exists(json_file_path):
            return jsonify({"error": "未找到指定的 JSON 文件"}), 404

        # 读取 JSON 文件，获取目录树
        with open(json_file_path, 'r', encoding='utf-8') as file:
            directory_tree = json.load(file)

        # 遍历目录树，删除所有列出的 .strm 文件
        def delete_strm_files(base_path, tree):
            for name, content in tree.items():
                current_path = os.path.join(base_path, name)
                if isinstance(content, dict):
                    # 如果是目录，递归遍历
                    delete_strm_files(current_path, content)
                    # 删除空目录
                    if os.path.exists(current_path) and not os.listdir(current_path):
                        os.rmdir(current_path)
                        logger.info(f"删除空目录: {current_path}")
                elif content == "invalid" and name.endswith('.strm'):
                    # 删除文件
                    if os.path.exists(current_path):
                        os.remove(current_path)
                        logger.info(f"删除文件: {current_path}")

        # 开始删除
        delete_strm_files(target_directory, directory_tree)

        # 删除对应的失效目录树 JSON 文件
        os.remove(json_file_path)
        logger.info(f"删除失效目录树 JSON 文件: {json_file_path}")

        flash('目录及其 .strm 文件已成功删除！', 'success')
        return jsonify({"message": "目录和失效目录树已成功删除"}), 200

    except Exception as e:
        logger.error(f"删除目录时出错: {e}")
        return jsonify({"error": "删除目录时出错"}), 500

@app.route('/invalid_file_trees')
def invalid_file_trees():
    invalid_file_trees = []
    invalid_tree_dir = 'invalid_file_trees'

    if os.path.exists(invalid_tree_dir):
        for json_file in os.listdir(invalid_tree_dir):
            if json_file.endswith('.json'):
                invalid_file_trees.append({
                    'name': json_file,  # 保留完整的文件名，包括 .json
                })

    return render_template('invalid_file_trees.html', invalid_file_trees=invalid_file_trees)

@app.route('/get_invalid_file_tree/<path:json_filename>', methods=['GET'])
def get_invalid_file_tree(json_filename):
    try:
        # 构建 JSON 文件的路径
        json_file_path = os.path.join('invalid_file_trees', json_filename)
        if not os.path.exists(json_file_path):
            return jsonify({"error": "未找到指定的 JSON 文件"}), 404

        # 读取 JSON 文件，获取目录树
        with open(json_file_path, 'r', encoding='utf-8') as file:
            directory_tree = json.load(file)

        # 返回目录树结构
        return jsonify({"structure": directory_tree}), 200

    except Exception as e:
        logger.error(f"获取目录树时出错: {e}")
        return jsonify({"error": "获取目录树时出错"}), 500


# 配置文件页面
@app.route('/configs')
@login_required
def configs():
    try:
        # 查询数据库
        db_handler.cursor.execute("SELECT config_id, config_name, url, username, rootpath, target_directory FROM config")
        configs = db_handler.cursor.fetchall()

        # 调试输出
        print(f"从数据库中读取的配置: {configs}")

        return render_template('configs.html', configs=configs)
    except Exception as e:
        flash(f"加载配置时出错: {e}", 'error')
        return render_template('configs.html', configs=[])

@app.route('/random_image')
def random_image():
    # 获取目录中的所有图片文件
    images = os.listdir(IMAGE_FOLDER)
    # 随机选择一张图片
    random_image = random.choice(images)
    # 返回该图片
    return send_from_directory(IMAGE_FOLDER, random_image)

@app.before_request
def before_request():
    g.local_version = local_version  # 动态获取版本号的逻辑


@app.route('/edit/<int:config_id>', methods=['GET', 'POST'])
def edit_config(config_id):
    try:
        if request.method == 'POST':
            # 打印表单数据，调试用途
            print(f"收到的表单数据: {request.form}")

            config_name = request.form['config_name']
            url = request.form['url']
            username = request.form['username']
            password = request.form['password']
            rootpath = request.form['rootpath']
            target_directory = request.form['target_directory']
            download_interval_range = request.form.get('download_interval_range', '1-3')  # 保持为字符串
            download_enabled = int(request.form.get('download_enabled', 0))  # 获取是否启用下载功能，默认0（禁用）
            update_mode = request.form['update_mode']  # 获取更新模式

            # 自动为 rootpath 添加 /dav/ 前缀（如果没有）
            if not rootpath.startswith('/dav/'):
                rootpath = '/dav/' + rootpath.lstrip('/')

            # 更新配置，包括下载启用状态、更新模式和大小阈值
            db_handler.cursor.execute('''
                UPDATE config 
                SET config_name = ?, url = ?, username = ?, password = ?, rootpath = ?, target_directory = ?, download_enabled = ?, update_mode = ?, download_interval_range = ?
                WHERE config_id = ?
            ''', (config_name, url, username, password, rootpath, target_directory, download_enabled, update_mode, download_interval_range, config_id))
            db_handler.conn.commit()

            flash('配置已成功更新！', 'success')
            return redirect(url_for('configs'))

        # GET 请求时，获取并显示现有的配置项
        db_handler.cursor.execute('''
            SELECT config_name, url, username, password, rootpath, target_directory, download_enabled, update_mode, download_interval_range 
            FROM config 
            WHERE config_id = ?
        ''', (config_id,))
        config = db_handler.cursor.fetchone()

        if config and config[8] is None:
            config = list(config)  # 转换为列表以进行修改
            config[8] = '1-3'  # 默认值为字符串 '1-3'

        return render_template('edit_config.html', config=config)
    except Exception as e:
        flash(f"编辑配置时出错: {e}", 'error')
        return redirect(url_for('configs'))







@app.route('/new', methods=['GET', 'POST'])
def new_config():
    if request.method == 'POST':
        try:
            # 从表单中获取用户输入的数据
            config_name = request.form['config_name']
            url = request.form['url']
            username = request.form['username']
            password = request.form['password']
            rootpath = request.form['rootpath']
            target_directory = request.form['target_directory']
            download_interval_range = request.form.get('download_interval_range', '1-3')  # 保持为字符串
            download_enabled = int(request.form.get('download_enabled', 0))  # 获取是否启用下载功能，默认0（禁用）
            update_mode = request.form['update_mode']  # 获取更新模式

            # 自动为 rootpath 添加 /dav/ 前缀（如果没有）
            if not rootpath.startswith('/dav/'):
                rootpath = '/dav/' + rootpath.lstrip('/')

            # 插入新配置到数据库，确保所有字段都被插入
            db_handler.cursor.execute('''
                INSERT INTO config (config_name, url, username, password, rootpath, target_directory, download_interval_range, download_enabled, update_mode) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (config_name, url, username, password, rootpath, target_directory, download_interval_range, download_enabled, update_mode))
            db_handler.conn.commit()

            flash('新配置已成功添加！', 'success')
            return redirect(url_for('configs'))
        except Exception as e:
            flash(f"添加新配置时出错: {e}", 'error')

    return render_template('new_config.html')




@app.route('/copy_config/<int:config_id>', methods=['GET'])
def copy_config(config_id):
    try:
        # 查询要复制的配置
        db_handler.cursor.execute('SELECT config_name, url, username, password, rootpath, target_directory, download_interval_range, download_enabled, update_mode FROM config WHERE config_id = ?', (config_id,))
        config = db_handler.cursor.fetchone()

        if not config:
            flash(f"未找到配置 ID 为 {config_id} 的配置文件。", 'error')
            return render_template('404.html'), 404  # 返回404页面

        # 生成新名称，确保唯一性
        new_name = config[0] + " - 复制"

        db_handler.cursor.execute('''
            INSERT INTO config (config_name, url, username, password, rootpath, target_directory, download_interval_range, download_enabled, update_mode) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (new_name, config[1], config[2], config[3], config[4], config[5], config[6], config[7], config[8]))

        # 提交事务
        db_handler.conn.commit()

        # 添加日志输出，确认插入成功
        print(f"新配置已插入数据库: {new_name}")
        flash(f"配置已成功复制！", 'success')

    except Exception as e:
        flash(f"复制配置时出错: {e}", 'error')
        return render_template('500.html'), 500  # 返回500错误

    return redirect(url_for('configs'))



@app.route('/delete/<int:config_id>')
def delete_config(config_id):
    try:
        db_handler.cursor.execute("DELETE FROM config WHERE config_id = ?", (config_id,))
        db_handler.conn.commit()
        flash('配置已成功删除！', 'success')
    except Exception as e:
        flash(f"删除配置时出错: {e}", 'error')
        return render_template('500.html'), 500  # 返回500错误

    return redirect(url_for('configs'))



# 设置页面
@app.route('/settings', methods=['GET', 'POST'])
def settings():

    if request.method == 'POST':
        try:
            video_formats = request.form['video_formats']
            subtitle_formats = request.form['subtitle_formats']
            image_formats = request.form['image_formats']
            metadata_formats = request.form['metadata_formats']
            size_threshold = int(request.form['size_threshold'])
            # 使用现有的 db_handler 进行数据库更新
            db_handler.cursor.execute('''
                UPDATE user_config 
                SET video_formats = ?, subtitle_formats = ?, image_formats = ?, metadata_formats = ?,size_threshold = ?
            ''', (video_formats, subtitle_formats, image_formats, metadata_formats, size_threshold))
            db_handler.conn.commit()


            flash('设置已成功更新！', 'success')
        except Exception as e:
            flash(f"更新设置时出错: {e}", 'error')
        return redirect(url_for('settings'))

    # 显示当前的脚本配置
    script_config = db_handler.get_script_config()

    # 获取当前的 download_enabled 值
    db_handler.cursor.execute('SELECT download_enabled FROM config LIMIT 1')
    result = db_handler.cursor.fetchone()

    # 检查是否有返回结果
    if result is None:
        # 如果查询结果为 None，则设置 download_enabled 为默认值 (1)
        download_enabled = 1
    else:
        # 否则获取数据库中的值
        download_enabled = result[0]

    script_config['download_enabled'] = bool(download_enabled)  # 将 download_enabled 传递给前端

    return render_template('settings.html', script_config=script_config)





@app.route('/logs/<int:config_id>')
def logs(config_id):
    log_dir = os.path.join(os.getcwd(), 'logs')

    # 获取指定config_id的所有日志文件（以config_id为前缀）
    log_files = [f for f in os.listdir(log_dir) if f.startswith(f'config_{config_id}') and f.endswith('.log')]

    if not log_files:
        # 如果没有找到相关日志文件，返回404错误
        abort(404, description=f"没有找到与配置 ID {config_id} 相关的日志文件")

    # 按文件修改时间倒序排列，获取最新的日志文件
    latest_log_file = max(log_files, key=lambda f: os.path.getmtime(os.path.join(log_dir, f)))
    log_file_path = os.path.join(log_dir, latest_log_file)

    # 读取日志文件并按行倒序排列
    with open(log_file_path, 'r', encoding='utf-8') as log_file:
        log_content = log_file.readlines()
        log_content.reverse()  # 倒序排列日志行

    # 将倒序后的日志内容转换成字符串，确保每行都以 <br> 分隔
    log_content = '<br>'.join(log_content)

    # 渲染日志页面并显示日志内容
    return render_template('logs_single.html', log_content=log_content, config_id=config_id)







# 定义函数来运行 main.py
def run_config(config_id):
    # 获取当前文件的目录路径
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # 使用绝对路径指定 main.py 的位置
    main_script_path = os.path.join(current_dir, 'main.py')

    if os.path.exists(main_script_path):
        command = f"python3.9 {main_script_path} {config_id}"
        logger.info(f"启动配置ID: {config_id} 的命令: {command}")
        subprocess.Popen(command, shell=True)
    else:
        logger.error(f"无法找到 main.py 文件: {main_script_path}")

@app.route('/run_selected_configs', methods=['POST'])
def run_selected_configs():
    selected_configs = request.form.getlist('selected_configs')
    action = request.form.get('action')

    if not selected_configs:
        flash('请选择至少一个配置', 'error')
        return redirect(url_for('configs'))

    if action == 'copy_selected':
        # 处理复制选定配置
        for config_id in selected_configs:
            copy_config(int(config_id))  # 你可以直接调用之前定义的 `copy_config` 函数
        flash('选定的配置已成功复制！', 'success')

    elif action == 'delete_selected':
        # 处理删除选定配置
        for config_id in selected_configs:
            db_handler.cursor.execute('DELETE FROM config WHERE config_id = ?', (config_id,))
        db_handler.conn.commit()
        flash('选定的配置已成功删除！', 'success')

    elif action == 'run_selected':
        for config_id in selected_configs:
            run_config(int(config_id))  # 调用 `run_config` 函数来运行 main.py
        flash('选定的配置已开始运行！', 'success')

    return redirect(url_for('configs'))

@app.route('/scheduled_tasks')
def scheduled_tasks():
    try:
        # 从定时任务模块中获取所有定时任务
        tasks = list_tasks_in_cron()  # 调用 task_scheduler.py 的 list_tasks_in_cron 方法
        return render_template('scheduled_tasks.html', tasks=tasks)
    except Exception as e:
        flash(f'获取定时任务时出错: {e}', 'error')
        return redirect(url_for('index'))
@app.route('/new_task', methods=['GET', 'POST'])
def new_task():
    if request.method == 'POST':
        task_name = request.form['task_name']
        config_ids = request.form.getlist('config_ids')  # 获取选择的配置文件 ID，列表形式
        interval_type = request.form['interval_type']
        interval_value = request.form['interval_value']
        task_mode = request.form['task_mode']
        is_enabled = request.form['is_enabled'] == '1'  # 将字符串转换为布尔值

        # 验证间隔值
        try:
            interval_value_int = int(interval_value)
            if interval_type == 'minute' and not (1 <= interval_value_int <= 59):
                raise ValueError('分钟间隔值必须在 1 到 59 之间')
            elif interval_type == 'hourly' and not (1 <= interval_value_int <= 23):
                raise ValueError('小时间隔值必须在 1 到 23 之间')
            elif interval_type == 'daily' and not (1 <= interval_value_int <= 31):
                raise ValueError('天数间隔值必须在 1 到 31 之间')
            elif interval_type == 'weekly' and not (0 <= interval_value_int <= 6):
                raise ValueError('星期值必须在 0（周日）到 6（周六）之间')
            elif interval_type == 'monthly' and not (1 <= interval_value_int <= 12):
                raise ValueError('月份间隔值必须在 1 到 12 之间')
        except ValueError as ve:
            flash(str(ve), 'error')
            return redirect(url_for('new_task'))

        # 将间隔类型和间隔值转换为 cron 时间格式
        cron_time = convert_to_cron_time(interval_type, interval_value)

        # 调用定时任务模块的函数添加任务
        task_ids = add_tasks_to_cron(
            task_name=task_name,
            cron_time=cron_time,
            config_ids=config_ids,
            task_mode=task_mode,
            is_enabled=is_enabled
        )

        flash('任务已成功添加！', 'success')
        return redirect(url_for('scheduled_tasks'))

    # 从数据库中读取配置文件列表
    configs = db_handler.get_all_configurations()
    return render_template('new_task.html', configs=configs)

@app.route('/update_task/<task_id>', methods=['GET', 'POST'])
def update_task(task_id):
    if request.method == 'POST':
        task_name = request.form['task_name']
        config_ids = request.form.getlist('config_ids')
        interval_type = request.form['interval_type']
        interval_value = request.form['interval_value']
        task_mode = request.form['task_mode']
        is_enabled = request.form['is_enabled'] == '1'

        # 验证间隔值
        try:
            interval_value_int = int(interval_value)
            if interval_type == 'minute' and not (1 <= interval_value_int <= 59):
                raise ValueError('分钟间隔值必须在 1 到 59 之间')
            elif interval_type == 'hourly' and not (1 <= interval_value_int <= 23):
                raise ValueError('小时间隔值必须在 1 到 23 之间')
            elif interval_type == 'daily' and not (1 <= interval_value_int <= 31):
                raise ValueError('天数间隔值必须在 1 到 31 之间')
            elif interval_type == 'weekly' and not (0 <= interval_value_int <= 6):
                raise ValueError('星期值必须在 0（周日）到 6（周六）之间')
            elif interval_type == 'monthly' and not (1 <= interval_value_int <= 12):
                raise ValueError('月份间隔值必须在 1 到 12 之间')
        except ValueError as ve:
            flash(str(ve), 'error')
            return redirect(url_for('update_task', task_id=task_id))

        # 将间隔类型和间隔值转换为 cron 时间格式
        cron_time = convert_to_cron_time(interval_type, interval_value)

        # 更新任务信息
        update_tasks_in_cron(
            task_ids=[task_id],
            cron_time=cron_time,
            config_ids=config_ids,
            task_mode=task_mode,
            task_name=task_name,
            is_enabled=is_enabled
        )

        flash('任务已成功更新！', 'success')
        return redirect(url_for('scheduled_tasks'))

    # GET 请求时，加载任务信息
    tasks = list_tasks_in_cron()  # 调用 task_scheduler.py 的 list_tasks_in_cron 方法
    task = next((t for t in tasks if t.get('task_id') == task_id), None)
    configs = db_handler.get_all_configurations()

    if not task:
        flash('未找到指定的任务', 'error')
        return redirect(url_for('scheduled_tasks'))

    # 获取已有的配置文件 ID，并确保它们是字符串
    selected_config_ids = [str(task.get('config_id'))]
    app.logger.debug(f"Selected Config IDs: {selected_config_ids}")

    return render_template('edit_task.html', task=task, configs=configs, selected_config_ids=selected_config_ids)


@app.route('/delete_task/<task_id>', methods=['POST'])
def delete_task(task_id):
    try:
        # 删除定时任务
        delete_tasks_from_cron([task_id])  # 调用 task_scheduler.py 的 delete_tasks_from_cron 方法

        flash('任务已成功删除！', 'success')
    except Exception as e:
        flash(f"删除任务时出错: {e}", 'error')
        print(f"删除任务时出现错误: {e}")

    return redirect(url_for('scheduled_tasks'))

@app.route('/delete_selected_tasks', methods=['POST'])
def delete_selected_tasks():
    try:
        data = request.get_json()
        task_ids = data.get('task_ids', [])
        if not task_ids:
            return jsonify({'success': False, 'error': '未提供任务ID'})

        delete_tasks_from_cron(task_ids)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/view_logs/<task_id>')
def view_logs(task_id):
    # 日志文件的路径
    log_dir = os.path.join(os.getcwd(), 'logs')
    # 构建日志文件的搜索模式
    log_pattern = os.path.join(log_dir, f'task_{task_id}_*.log')
    log_files = glob.glob(log_pattern)

    if log_files:
        # 按照文件修改时间排序，最新的文件排在第一个
        log_files.sort(key=os.path.getmtime, reverse=True)

        # 只读取最新的日志文件
        latest_log_file = log_files[0]
        with open(latest_log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        log_contents = [{
            'filename': os.path.basename(latest_log_file),
            'content': content
        }]
    else:
        log_contents = None

    return render_template('view_logs.html', log_contents=log_contents, task_id=task_id)


def restart_app():
    print("重启应用...")
    # 重启当前应用

    os.execv(sys.executable, ['python'] + sys.argv)


def download_and_extract(url, extract_to='.'):
    try:
        # 下载文件
        local_filename = url.split('/')[-1]
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        # 解压缩文件
        if local_filename.endswith('.zip'):
            with zipfile.ZipFile(local_filename, 'r') as zip_ref:
                zip_ref.extractall(extract_to)

        # 删除压缩包
        os.remove(local_filename)

        return True
    except Exception as e:
        print(f"下载或解压时出错: {e}")
        return False

def check_for_updates(source, channel):
    sources = {
        'domestic': 'https://www.tefuir0829.cn/version.json',
        'github': 'https://raw.githubusercontent.com/tefuirZ/alist-strm/refs/heads/main/version.json'
    }

    channels = {
        'stable': 'stable',
        'beta': 'beta'
    }

    try:
        # 选择源和通道
        source_url = sources.get(source)
        channel = channels.get(channel, 'stable')  # 默认选择正式版

        # 获取版本信息
        response = requests.get(source_url)
        response.raise_for_status()  # 检查是否有请求错误

        version_data = response.json()
        latest_version_info = version_data.get(channel)

        # 本地版本号


        # 比较远端版本号与本地版本号
        latest_version = latest_version_info.get('version')
        if latest_version > local_version:
            # 返回更新信息
            return {
                "new_version": True,
                "latest_version": latest_version,
                "download_url": latest_version_info.get('download_url'),
                "changelog": latest_version_info.get('changelog')
            }
        else:
            # 已是最新版本
            return {"new_version": False}

    except Exception as e:
        # 出错时返回字典结构，而不是字符串
        return {
            "new_version": False,
            "error": f"检查更新时出错: {e}"
        }





@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

@app.errorhandler(400)
def bad_request_error(e):
    return render_template('400.html'), 400




@app.route('/other', methods=['GET', 'POST'])
@login_required  # 如果需要登录才能访问
def other():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'edit':
            # 获取用户输入的变量
            target_directory = request.form.get('target_directory')
            old_domain = request.form.get('old_domain')
            new_domain = request.form.get('new_domain')
            # 保存变量到会话
            session['script_params'] = {
                'target_directory': target_directory,
                'old_domain': old_domain,
                'new_domain': new_domain
            }
            flash('参数已保存。', 'success')
            return redirect(url_for('other'))
        elif action == 'run':
            # 从会话中获取变量
            script_params = session.get('script_params')
            if not script_params:
                flash('请先设置脚本参数。', 'error')
                return redirect(url_for('other'))
            # 运行脚本
            result = run_replace_domain_script(
                script_params['target_directory'],
                script_params['old_domain'],
                script_params['new_domain']
            )
            if result:
                flash('脚本已启动！请查看日志。', 'success')
            else:
                flash('脚本启动失败。', 'error')
            return redirect(url_for('other'))
    else:
        # GET 请求，渲染页面并传递日志内容
        script_params = session.get('script_params', {})
        log_content = get_script_log()  # 获取日志内容
        return render_template('other.html',
                               script_params=script_params,
                               log_content=log_content)


def run_task_immediately(task_id):
    # 获取所有任务
    tasks = list_tasks_in_cron()

    # 查找指定 task_id 对应的任务
    task_to_run = next((task for task in tasks if task.get('task_id') == task_id), None)

    if task_to_run:
        # 获取任务命令
        command = task_to_run.get('command')
        if not command:
            raise ValueError('找不到该任务的命令，无法运行。')

        try:
            # 使用 subprocess 来运行任务的命令
            subprocess.Popen(command, shell=True)
            print(f"任务 {task_id} 已立即运行。")
        except Exception as e:
            print(f"运行任务 {task_id} 时发生错误: {e}")
    else:
        raise ValueError(f"找不到 task_id 为 {task_id} 的任务。")

@app.route('/run_task_now/<task_id>', methods=['POST'])
def run_task_now(task_id):
    try:
        # 调用立即运行任务的函数
        run_task_immediately(task_id)
        flash(f"任务 {task_id} 已成功运行！", 'success')
    except Exception as e:
        flash(f"运行任务 {task_id} 时出错: {e}", 'error')

    return redirect(url_for('scheduled_tasks'))




# 辅助函数：运行脚本
def run_replace_domain_script(target_directory, old_domain, new_domain):
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'replace_domain.py')
    try:
        # 构建命令
        command = [
            'python3',
            script_path,
            target_directory,
            old_domain,
            new_domain
        ]
        # 后台运行脚本
        subprocess.Popen(command)
        app.logger.info(f"已启动脚本: {' '.join(command)}")
        return True
    except Exception as e:
        app.logger.error(f"运行脚本时出错：{e}")
        return False

def get_script_log():
    log_dir = os.path.join(os.getcwd(), 'logs')
    log_file_name = 'replace_domain.log'
    log_file = os.path.join(log_dir, log_file_name)
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            # 只返回最后 1000 行
            return ''.join(lines[-1000:])
    else:
        return '日志文件不存在。'

@app.route('/about', methods=['GET', 'POST'])
def about():
    if request.method == 'POST':
        source = request.form.get('source', 'github')
        channel = request.form.get('channel', 'stable')

        # 检查更新
        update_info = check_for_updates(source, channel)

        if "error" in update_info:
            return jsonify(error=update_info["error"])
        elif update_info.get("new_version"):
            return jsonify(new_version=True,
                           latest_version=update_info.get('latest_version'),
                           changelog=update_info.get('changelog'))
        else:
            return jsonify(new_version=False)

    return render_template('about.html')

def update_version():
    source = request.form.get('source', 'github')
    channel = request.form.get('channel', 'stable')

    # 检查更新
    update_info = check_for_updates(source, channel)

    if update_info.get("new_version"):
        download_url = update_info.get('download_url')

        # 下载并解压新版本
        success = download_and_extract(download_url)

        if success:
            try:
                # 运行 check_and_install.py 来检查和安装依赖
                subprocess.check_call([sys.executable, "check_and_install.py"])

                # 安装完成后，重启应用
                return jsonify(message="新版本下载并安装成功！应用即将重启。")
            except subprocess.CalledProcessError as e:
                return jsonify(message=f"更新失败，依赖安装时出错：{e}")
        else:
            return jsonify(message="更新失败，下载或解压时出错。")
    else:
        return jsonify(message="当前已是最新版本，无需更新。")






if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)



