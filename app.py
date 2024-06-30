import random
from datetime import datetime
from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_apscheduler import APScheduler
import subprocess
import os
import logging
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)



app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/config.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SCHEDULER_API_ENABLED'] = True

db = SQLAlchemy(app)
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

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

class UserTask(db.Model):
    id = db.Column(db.String(6), primary_key=True, default=lambda: str(random.randint(100000, 999999)))
    cron_expression = db.Column(db.String(100), nullable=False)
    enabled = db.Column(db.Boolean, default=False)
    configs = db.relationship('Config', secondary=task_config, lazy='subquery',
        backref=db.backref('tasks', lazy=True))

# 初始化数据库
with app.app_context():
    db.create_all()

def cron_parser(cron_expression):
    fields = cron_expression.split()
    if len(fields) != 5:
        raise ValueError("Cron expression must have 5 fields")
    return {
        'minute': fields[0],
        'hour': fields[1],
        'day': fields[2],
        'month': fields[3],
        'day_of_week': fields[4]
    }

def scheduled_task(config_id, task_id):
    logger.info(f"Scheduled task triggered for config ID: {config_id}, task ID: {task_id}")
    run_task_with_logging(config_id, task_id)

def run_task_with_logging(config_id, task_id):
    with app.app_context():
        logger.info(f"Starting subprocess for config ID: {config_id}, task ID: {task_id}")
        log_dir = 'logs'
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        log_filename = os.path.join(log_dir, f'{task_id}.logs')
        try:
            with open(log_filename, 'w', encoding='utf-8') as log_file:
                log_file.write(f"Task for config {config_id} started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
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
                result = f"{timestamp} - Task for config {config_id} ended with return code {process.returncode}\n"
                logger.info(result)
                log_file.write(result)
                log_file.flush()
        except Exception as e:
            logger.error(f"Error running task for config {config_id}, task ID: {task_id}: {e}")
            if 'log_file' in locals():
                log_file.write(f"An error occurred: {e}\n")
                log_file.flush()
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
        config.update_existing = ('update_existing' in data)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('config_form.html', config=config)

@app.route('/config/<config_id>/delete', methods=['POST'])
def delete_config(config_id):
    config = db.session.get(Config, config_id)
    if not config:
        logger.info(f"Config with ID {config_id} not found")
        return jsonify({'message': '配置未找到'}), 404
    db.session.delete(config)
    db.session.commit()
    logger.info(f"Config with ID {config_id} deleted")
    return redirect(url_for('index'))


@app.route('/config/<config_id>/copy', methods=['POST'])
def copy_config(config_id):
    config = db.session.get(Config, config_id)
    if not config:
        logger.info(f"Config with ID {config_id} not found")
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
    logger.info(f"Config with ID {config_id} copied to new config with ID {new_config.id}")
    return jsonify({'success': True, 'new_config_id': new_config.id})


@app.route('/run', methods=['POST'])
def run_script():
    config_ids = request.form.getlist('config_ids')
    for config_id in config_ids:
        logger.info(f"Running script for config ID: {config_id}")
        thread = threading.Thread(target=run_script_with_logging, args=(config_id,))
        thread.start()
    return redirect(url_for('index'))

def run_script_with_logging(config_id):
    logger.info(f"Starting subprocess for config ID: {config_id}")
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_filename = os.path.join(log_dir, f'{config_id}.logs')
    with open(log_filename, 'w', encoding='utf-8') as log_file:
        process = subprocess.Popen(['python', 'main.py', config_id], stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1, universal_newlines=True, encoding='utf-8', errors='ignore')

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
        logger.info(f"Subprocess for config ID: {config_id} ended with return code {process.returncode}")
        log_file.write(f"Subprocess ended with return code {process.returncode}\n")
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
        logger.info(f"Task with ID {task_id} not found")
        return jsonify({'message': '任务未找到'}), 404
    remove_task_from_scheduler(task)
    db.session.delete(task)
    db.session.commit()
    logger.info(f"Task with ID {task_id} deleted")
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

def add_task_to_scheduler(task):
    for config in task.configs:
        job_id = f'task_{task.id}_config_{config.id}'
        # 确保任务未被添加
        if not scheduler.get_job(job_id):
            try:
                scheduler.add_job(
                    func=scheduled_task,
                    args=(config.id, task.id),
                    trigger='cron',
                    id=job_id,
                    **cron_parser(task.cron_expression)
                )
                logger.info(f"Task {task.id} for config {config.id} added to scheduler with cron expression: {task.cron_expression}")
            except Exception as e:
                logger.error(f"Failed to add job to scheduler: {e}")
        else:
            logger.info(f"Task {task.id} for config {config.id} already in scheduler, skipping.")



def remove_task_from_scheduler(task):
    for config in task.configs:
        job_id = f'task_{task.id}_config_{config.id}'
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info(f"Task {task.id} with job ID {job_id} removed from scheduler")

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
        tasks = UserTask.query.all()
        for task in tasks:
            if task.enabled:
                add_task_to_scheduler(task)




if __name__ == '__main__':

    with app.app_context():
        db.create_all()
        load_tasks_from_db()
    app.run(debug=True)  
