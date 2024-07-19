from datetime import datetime
import random
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_apscheduler import APScheduler
from werkzeug.security import generate_password_hash, check_password_hash
import subprocess
import os
import logging
import threading
from croniter import croniter
from sqlalchemy import inspect, Column, Boolean, String, Integer
from sqlalchemy.exc import OperationalError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'www.tefuir08029.cn'  # 必须设置一个密钥用于 session 加密

# 获取配置路径，默认值为 /config
config_path = os.getenv('CONFIG_PATH', '/config')

# 确保配置目录存在
if not os.path.exists(config_path):
    os.makedirs(config_path)

# 设置SQLAlchemy数据库URI
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(config_path, "config.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SCHEDULER_API_ENABLED'] = True
db = SQLAlchemy(app)
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()  # 启动调度器


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)


class Config(db.Model):
    id = db.Column(db.String(6), primary_key=True, default=lambda: str(random.randint(100000, 999999)))
    name = db.Column(db.String(100), nullable=False)
    root_path = db.Column(db.String(200), nullable=False)
    site_url = db.Column(db.String(200), nullable=False)
    target_directory = db.Column(db.String(200), nullable=False)
    ignored_directories = db.Column(db.String(200), nullable=True)
    token = db.Column(db.String(200), nullable=False)
    update_existing = db.Column(db.Boolean, default=False)


task_config = db.Table('task_config',
                       db.Column('task_id', db.String(6), db.ForeignKey('user_task.id'), primary_key=True),
                       db.Column('config_id', db.String(6), db.ForeignKey('config.id'), primary_key=True)
                       )


class UserConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_formats = db.Column(db.String(200), nullable=False, default='.mp4,.mkv,.avi,.mov,.flv,.wmv,.ts,.m2ts')
    subtitle_formats = db.Column(db.String(200), nullable=False, default='.srt,.ass,.ssa,.vtt')
    image_formats = db.Column(db.String(200), nullable=False, default='.jpg,.jpeg,.png,.bmp,.gif,.tiff,.webp')
    download_threads = db.Column(db.Integer, nullable=False, default=5)
    enable_metadata_download = db.Column(db.Boolean, nullable=False, default=True)
    enable_invalid_link_check = db.Column(db.Boolean, nullable=False, default=True)
    enable_nfo_download = db.Column(db.Boolean, nullable=False, default=True)
    enable_subtitle_download = db.Column(db.Boolean, nullable=False, default=True)
    enable_image_download = db.Column(db.Boolean, nullable=False, default=True)
    enable_refresh = db.Column(db.Boolean, nullable=False, default=True)


class UserTask(db.Model):
    id = db.Column(db.String(6), primary_key=True, default=lambda: str(random.randint(100000, 999999)))
    cron_expression = db.Column(db.String(100), nullable=False)
    enabled = db.Column(db.Boolean, default=False)
    configs = db.relationship('Config', secondary=task_config, lazy='subquery',
                              backref=db.backref('tasks', lazy=True))


def add_missing_column(engine, table_name, column, default_value):
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    if column.name not in columns:
        with engine.connect() as conn:
            try:
                conn.execute(f'ALTER TABLE {table_name} ADD COLUMN {column.compile(dialect=engine.dialect)}')
                conn.execute(f'UPDATE {table_name} SET {column.name} = {default_value}')
            except OperationalError as e:
                logger.error(f"添加列 {column.name} 时出错: {e}")


def add_task_to_scheduler(task):
    for config in task.configs:  # 遍历任务关联的所有配置
        job_id = f'task_{task.id}_config_{config.id}'
        if not scheduler.get_job(job_id):
            try:
                # 为每个任务添加日志处理程序
                log_dir = 'logs'
                if not os.path.exists(log_dir):
                    os.makedirs(log_dir)
                log_filename = os.path.join(log_dir, f'{task.id}.logs')

                handler = logging.FileHandler(log_filename, encoding='utf-8')
                handler.setLevel(logging.INFO)
                formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                handler.setFormatter(formatter)

                apscheduler_logger = logging.getLogger('apscheduler')
                apscheduler_logger.setLevel(logging.INFO)
                apscheduler_logger.addHandler(handler)

                scheduler.add_job(
                    func=scheduled_task,
                    args=(config.id, task.id),
                    trigger='cron',
                    id=job_id,
                    **cron_parser(task.cron_expression)
                )
                logger.info(f"任务 {task.id} 的配置 {config.id} 已添加到调度器，cron 表达式: {task.cron_expression}")

                # 移除处理程序
                apscheduler_logger.removeHandler(handler)
            except Exception as e:
                logger.error(f"添加任务到调度器失败: {e}")
        else:
            logger.info(f"任务 {task.id} 的配置 {config.id} 已存在于调度器中，跳过添加。")


def init_app(app):
    with app.app_context():
        engine = db.get_engine()
        # 添加所有缺失的列
        add_missing_column(engine, 'user_config', Column('enable_refresh', Boolean, nullable=False, server_default='1'),
                           '1')
        add_missing_column(engine, 'user_config',
                           Column('enable_nfo_download', Boolean, nullable=False, server_default='1'), '1')
        add_missing_column(engine, 'user_config',
                           Column('enable_subtitle_download', Boolean, nullable=False, server_default='1'), '1')
        add_missing_column(engine, 'user_config',
                           Column('enable_image_download', Boolean, nullable=False, server_default='1'), '1')
        add_missing_column(engine, 'user_config',
                           Column('enable_metadata_download', Boolean, nullable=False, server_default='1'), '1')
        add_missing_column(engine, 'user_config',
                           Column('enable_invalid_link_check', Boolean, nullable=False, server_default='1'), '1')
        db.create_all()


def scheduled_task(config_id, task_id):
    logger.info(f"定时任务触发，配置ID: {config_id}, 任务ID: {task_id}")
    run_task_with_logging(config_id, task_id)


def run_task_with_logging(config_id, task_id):
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_filename = os.path.join(log_dir, f'{task_id}.logs')

    # 设置日志处理程序
    handler = logging.FileHandler(log_filename, encoding='utf-8')
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(message)s')
    handler.setFormatter(formatter)

    # 添加日志处理程序到 apscheduler.logger
    apscheduler_logger = logging.getLogger('apscheduler')
    apscheduler_logger.setLevel(logging.INFO)
    apscheduler_logger.addHandler(handler)

    with open(log_filename, 'a', encoding='utf-8') as log_file:
        log_file.write(f"定时任务启动，配置ID {config_id} 启动于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_file.flush()

        process = subprocess.Popen(['python', 'main.py', config_id], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, bufsize=1, universal_newlines=True, encoding='utf-8',
                                   errors='ignore')

        def read_output(pipe):
            for line in iter(pipe.readline, ''):
                if line:
                    logger.info(line.strip())
                    log_file.write(line)
                    log_file.flush()
            pipe.close()

        stdout_thread = threading.Thread(target=read_output, args=(process.stdout,))
        stderr_thread = threading.Thread(target=read_output, args=(process.stderr,))

        stdout_thread.start()
        stderr_thread.start()

        stdout_thread.join()
        stderr_thread.join()

        process.wait()

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        result = f"{timestamp} - 定时任务：配置 {config_id} 运行结束 ，返回代码 {process.returncode}\n"
        logger.info(result)
        log_file.write(result)
        log_file.flush()

        # 获取下次运行时间
        job_id = f'task_{task_id}_config_{config_id}'
        job = scheduler.get_job(job_id)
        if job:
            next_run_time = job.next_run_time.strftime('%Y-%m-%d %H:%M:%S')
            log_file.write(f"下次运行时间：{next_run_time}\n")
            logger.info(f"下次运行时间：{next_run_time}")

    # 移除处理程序
    apscheduler_logger.removeHandler(handler)


@app.before_first_request
def before_first_request():
    init_app(app)  # 在第一次请求之前初始化应用，确保缺失的字段被添加
    if not UserConfig.query.first():
        default_user_config = UserConfig()
        db.session.add(default_user_config)
        db.session.commit()


@app.before_request
def before_request():
    if not User.query.first() and request.endpoint != 'register':
        return redirect(url_for('register'))
    elif 'user_id' not in session and request.endpoint not in ['login', 'register', 'static']:
        return redirect(url_for('login'))


@app.route('/')
def index():
    configs = Config.query.all()
    tasks = UserTask.query.all()
    return render_template('index.html', configs=configs, tasks=tasks)


@app.route('/config/new', methods=['GET', 'POST'])
def add_config():
    if request.method == 'POST':
        data = request.form
        new_config = Config(
            name=data['name'],
            root_path=data['root_path'],
            site_url=data['site_url'],
            target_directory=data['target_directory'],
            ignored_directories=data['ignored_directories'],
            token=data['token'],
            update_existing=('update_existing' in data)
        )
        db.session.add(new_config)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('config_form.html', config=None)


@app.route('/config/<config_id>/edit', methods=['GET', 'POST'])
def edit_config(config_id):
    config = db.session.get(Config, config_id)
    if request.method == 'POST':
        data = request.form
        config.name = data['name']
        config.root_path = data['root_path']
        config.site_url = data['site_url']
        config.target_directory = data['target_directory']
        config.ignored_directories = data['ignored_directories']
        config.token = data['token']
        config.update_existing = int(data['update_existing'])  # 处理下拉框提交的值
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('config_form.html', config=config)


@app.route('/config/<config_id>/delete', methods=['POST'])
def delete_config(config_id):
    config = db.session.get(Config, config_id)
    if not config:
        logger.info(f"配置ID {config_id} 未找到")
        return jsonify({'message': '配置未找到'}), 404
    db.session.delete(config)
    db.session.commit()
    logger.info(f"配置ID {config_id} 已删除")
    return redirect(url_for('index'))


@app.route('/run', methods=['POST'])
def run_script():
    config_ids = request.form.getlist('config_ids')
    for config_id in config_ids:
        logger.info(f"运行脚本，配置ID: {config_id}")
        thread = threading.Thread(target=run_script_with_logging, args=(config_id,))
        thread.start()
    return redirect(url_for('index'))


def run_script_with_logging(config_id):
    logger.info(f"启动子进程，配置ID: {config_id}")
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_filename = os.path.join(log_dir, f'{config_id}.logs')
    with open(log_filename, 'w', encoding='utf-8') as log_file:
        process = subprocess.Popen(['python', 'main.py', config_id], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   bufsize=1, universal_newlines=True, encoding='utf-8', errors='ignore')

        def read_output(pipe):
            for line in iter(pipe.readline, ''):
                if line:
                    log_file.write(line)
                    log_file.flush()
            pipe.close()

        stdout_thread = threading.Thread(target=read_output, args=(process.stdout,))
        stderr_thread = threading.Thread(target=read_output, args=(process.stderr,))

        stdout_thread.start()
        stderr_thread.start()

        stdout_thread.join()
        stderr_thread.join()

        process.wait()
        logger.info(f"子进程结束，配置ID: {config_id}, 返回码: {process.returncode}")
        log_file.write(f"子进程结束，返回码: {process.returncode}\n")
        log_file.flush()


@app.route('/task/new', methods=['GET', 'POST'])
def add_task():
    configs = Config.query.all()
    if request.method == 'POST':
        data = request.form
        selected_config_ids = request.form.getlist('config_ids')
        new_task = UserTask(
            cron_expression=data['cron_expression'],
            enabled=('enabled' in data)
        )
        for config_id in selected_config_ids:
            config = db.session.get(Config, config_id)
            if config:
                new_task.configs.append(config)
        db.session.add(new_task)
        db.session.commit()
        if new_task.enabled:
            add_task_to_scheduler(new_task)
        return redirect(url_for('index'))
    return render_template('task_form.html', configs=configs, selected_config_ids=[])


@app.route('/task/<task_id>/edit', methods=['GET', 'POST'])
def edit_task(task_id):
    task = db.session.get(UserTask, task_id)
    configs = Config.query.all()
    if request.method == 'POST':
        data = request.form
        selected_config_ids = request.form.getlist('config_ids')
        task.cron_expression = data['cron_expression']
        task.enabled = ('enabled' in data)
        task.configs = []
        for config_id in selected_config_ids:
            config = db.session.get(Config, config_id)
            if config:
                task.configs.append(config)
        db.session.commit()
        remove_task_from_scheduler(task)
        if task.enabled:
            add_task_to_scheduler(task)
        return redirect(url_for('index'))
    selected_config_ids = [config.id for config in task.configs]
    return render_template('task_form.html', task=task, configs=configs, selected_config_ids=selected_config_ids)


@app.route('/task/<task_id>/delete', methods=['POST'])
def delete_task(task_id):
    task = db.session.get(UserTask, task_id)
    if not task:
        logger.info(f"任务ID {task_id} 未找到")
        return jsonify({'message': '任务未找到'}), 404
    remove_task_from_scheduler(task)
    db.session.delete(task)
    db.session.commit()
    logger.info(f"任务ID {task_id} 已删除")
    return redirect(url_for('index'))


@app.route('/task/<task_id>/toggle', methods=['POST'])
def toggle_task(task_id):
    task = db.session.get(UserTask, task_id)
    if task:
        task.enabled = not task.enabled
        db.session.commit()
        if task.enabled:
            add_task_to_scheduler(task)
        else:
            remove_task_from_scheduler(task)
        return jsonify({'success': True, 'enabled': task.enabled})
    return jsonify({'success': False, 'error': '任务未找到'}), 404


@app.route('/test_cron', methods=['POST'])
def test_cron_expression():
    data = request.json
    cron_expression = data.get('cron_expression')

    try:
        iter = croniter(cron_expression, datetime.now())
        next_run_times = [iter.get_next(datetime).strftime('%Y-%m-%d %H:%M:%S') for _ in range(5)]
        return jsonify({'valid': True, 'next_run_times': next_run_times})
    except (ValueError, KeyError) as e:
        return jsonify({'valid': False, 'error': str(e)})


def cron_parser(cron_expression):
    fields = cron_expression.split()
    if len(fields) != 5:
        raise ValueError("无效的 cron 表达式。期望 5 个字段，但得到 {len(fields)}")
    return {
        'minute': fields[0],
        'hour': fields[1],
        'day': fields[2],
        'month': fields[3],
        'day_of_week': fields[4]
    }


@app.route('/config/<config_id>/copy', methods=['POST'])
def copy_config(config_id):
    config = db.session.get(Config, config_id)
    if not config:
        logger.info(f"配置ID {config_id} 未找到")
        return jsonify({'success': False, 'error': '配置未找到'}), 404

    new_config = Config(
        id=str(random.randint(100000, 999999)),
        name=f"{config.name} 副本",
        root_path=config.root_path,
        site_url=config.site_url,
        target_directory=config.target_directory,
        ignored_directories=config.ignored_directories,
        token=config.token,
        update_existing=config.update_existing
    )
    db.session.add(new_config)
    db.session.commit()
    logger.info(f"配置ID {config_id} 复制到新配置，ID: {new_config.id}")
    return jsonify({'success': True, 'new_config_id': new_config.id})


def remove_task_from_scheduler(task):
    for config in task.configs:
        job_id = f'task_{task.id}_config_{config.id}'
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info(f"任务 {task.id} 的作业 ID {job_id} 已从调度器中移除")


@app.route('/logs/<config_id>', methods=['GET'])
def get_logs(config_id):
    log_filename = os.path.join('logs', f'{config_id}.logs')
    if not os.path.exists(log_filename):
        return "该配置文件没有运行过，请返回首页运行该配置文件后查看日志。"
    with open(log_filename, 'r', encoding='utf-8') as log_file:
        log_content = log_file.read()
    return log_content


@app.route('/task_logs/<task_id>', methods=['GET'])
def get_task_logs(task_id):
    log_filename = os.path.join('logs', f'{task_id}.logs')
    if not os.path.exists(log_filename):
        return "该任务没有运行记录。"
    with open(log_filename, 'r', encoding='utf-8', errors='ignore') as log_file:
        log_content = log_file.read()
    return log_content


def load_tasks_from_db():
    with app.app_context():
        tasks = UserTask.query.all()  # 从 UserTask 表中读取所有任务
        for task in tasks:
            if task.enabled == 1:  # 检查任务是否启用
                add_task_to_scheduler(task)  # 将启用的任务添加到调度器


# 注册用户
@app.route('/register', methods=['GET', 'POST'])
def register():
    if User.query.first():  # 如果已经有用户存在，则跳转到登录页面
        return redirect(url_for('login'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password_hash=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        session['user_id'] = new_user.id
        return redirect(url_for('index'))
    return render_template('register.html')


# 登录用户
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            return redirect(url_for('index'))
        flash('用户名或密码错误')
    return render_template('login.html')


# 登出用户
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))


@app.route('/user_config', methods=['GET', 'POST'])
def user_config():
    user_config = UserConfig.query.first()
    if not user_config:
        flash('脚本配置未初始化，请联系管理员')
        return redirect(url_for('index'))

    if request.method == 'POST':
        logger.info("接收到 POST 请求，数据: %s", request.form)
        try:
            user_config.video_formats = request.form['video_formats']
            user_config.subtitle_formats = request.form['subtitle_formats']
            user_config.image_formats = request.form['image_formats']
            user_config.download_threads = int(request.form['download_threads'])
            user_config.enable_metadata_download = request.form['enable_metadata_download'] == '1'
            user_config.enable_invalid_link_check = request.form['enable_invalid_link_check'] == '1'
            user_config.enable_nfo_download = request.form['enable_nfo_download'] == '1'
            user_config.enable_subtitle_download = request.form['enable_subtitle_download'] == '1'
            user_config.enable_image_download = request.form['enable_image_download'] == '1'
            user_config.enable_refresh = request.form['enable_refresh'] == '1'

            db.session.commit()
            flash('配置已更新')
            logger.info("配置更新成功")
        except Exception as e:
            db.session.rollback()
            logger.error("配置更新失败: %s", str(e))
            flash('更新失败: ' + str(e))
        return redirect(url_for('user_config'))
    return render_template('user_config.html', user_config=user_config)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # 确保数据库表被创建
        init_app(app)  # 初始化应用
        load_tasks_from_db()  # 加载数据库中的任务并添加到调度器

    app.run(debug=False)

