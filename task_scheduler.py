import subprocess
import os
import sys
import uuid  # 用于生成唯一的 task_id

CRON_BACKUP_FILE = "/config/cron.bak"  # 备份文件路径


# 获取当前的 crontab 任务列表
def get_cron_jobs():
    result = subprocess.run(['crontab', '-l'], stdout=subprocess.PIPE, text=True)
    cron_jobs = result.stdout.strip().split('\n') if result.stdout else []
    return cron_jobs


# 备份当前的 cron 任务到 /config/cron.bak
def backup_cron_jobs(cron_jobs):
    cron_data = "\n".join(cron_jobs)
    with open(CRON_BACKUP_FILE, 'w') as f:
        f.write(cron_data)


# 从备份文件中读取 cron 任务
def get_cron_jobs_from_backup():
    if os.path.exists(CRON_BACKUP_FILE):
        with open(CRON_BACKUP_FILE, 'r') as f:
            cron_jobs = f.read().strip().split('\n')
            return cron_jobs
    return []


def extract_task_info(job_line):
    is_enabled = not job_line.strip().startswith('#')
    clean_job_line = job_line.lstrip('#').strip()
    parts = clean_job_line.split('#', 1)
    schedule_command = parts[0].strip()
    metadata = parts[1].strip() if len(parts) > 1 else ''

    cron_parts = schedule_command.split()
    if len(cron_parts) >= 6:
        cron_time = ' '.join(cron_parts[:5])
        command = ' '.join(cron_parts[5:])
    else:
        cron_time = ''
        command = ''

    task_info = {
        'cron_time': cron_time,
        'command': command,
        'is_enabled': is_enabled
    }
    for item in metadata.split():
        if '=' in item:
            key, value = item.split('=', 1)
            task_info[key] = value

    task_info['task_mode'] = determine_task_mode(command)
    interval_type, interval_value, description = parse_cron_time(cron_time)
    task_info['interval_type'] = interval_type
    task_info['interval_value'] = interval_value
    task_info['interval_description'] = description

    if 'config_id' in task_info:
        task_info['config_id'] = str(task_info['config_id'])

    return task_info


def list_tasks_in_cron():
    cron_jobs = get_cron_jobs()
    program_managed_tasks = []
    for job in cron_jobs:
        if "# task_id=" in job and "config_id=" in job:
            task_info = extract_task_info(job)
            program_managed_tasks.append(task_info)
    return program_managed_tasks


def add_tasks_to_cron(task_name, cron_time, config_ids, task_mode, is_enabled=True):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    task_ids = []
    cron_jobs = get_cron_jobs()

    for config_id in config_ids:
        task_id = str(uuid.uuid4())

        commands = []
        if task_mode == 'strm_creation':
            cmd_main = f'cd "{script_dir}" && /usr/local/bin/python3.9 "{script_dir}/main.py" {config_id} {task_id}'
            commands.append(cmd_main)
        elif task_mode == 'strm_validation_quick':
            cmd_validator = f'cd "{script_dir}" && /usr/local/bin/python3.9 "{script_dir}/strm_validator.py" {config_id} quick {task_id}'
            commands.append(cmd_validator)
        elif task_mode == 'strm_validation_slow':
            cmd_validator = f'cd "{script_dir}" && /usr/local/bin/python3.9 "{script_dir}/strm_validator.py" {config_id} slow {task_id}'
            commands.append(cmd_validator)
        else:
            raise ValueError('不支持的任务模式')

        command = ' && '.join(commands)
        cron_entry = f"{cron_time} {command} # task_id={task_id} task_name={task_name} config_id={config_id} task_mode={task_mode}"
        if not is_enabled:
            cron_entry = f"# {cron_entry}"
        cron_jobs.append(cron_entry)
        task_ids.append(task_id)

    update_crontab(cron_jobs)
    return task_ids


def update_tasks_in_cron(task_ids, cron_time=None, config_ids=None, task_mode=None, task_name=None, is_enabled=None):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cron_jobs = get_cron_jobs()
    updated_jobs = []
    task_ids_set = set(task_ids)
    task_found = False

    for job in cron_jobs:
        is_job_enabled = not job.strip().startswith('#')
        clean_job = job.lstrip('# ').strip()
        task_info = extract_task_info(clean_job)
        current_task_id = task_info.get('task_id')
        if current_task_id in task_ids_set:
            task_found = True
            if cron_time is None:
                cron_time = task_info['cron_time']
            if task_name is None:
                task_name = task_info.get('task_name', 'Updated Task')
            if config_ids is None:
                config_id = task_info.get('config_id')
            else:
                index = task_ids.index(current_task_id)
                config_id = config_ids[index] if index < len(config_ids) else task_info.get('config_id')
            if task_mode is None:
                task_mode = task_info.get('task_mode')
            if is_enabled is None:
                is_enabled = is_job_enabled

            commands = []
            if task_mode == 'strm_creation':
                cmd_main = f'cd "{script_dir}" && /usr/local/bin/python3.9 "main.py" {config_id} {current_task_id}'
                commands.append(cmd_main)
            elif task_mode == 'strm_validation_quick':
                cmd_validator = f'cd "{script_dir}" && /usr/local/bin/python3.9 "strm_validator.py" {config_id} quick {current_task_id}'
                commands.append(cmd_validator)
            elif task_mode == 'strm_validation_slow':
                cmd_validator = f'cd "{script_dir}" && /usr/local/bin/python3.9 "strm_validator.py" {config_id} slow {current_task_id}'
                commands.append(cmd_validator)
            else:
                raise ValueError('不支持的任务模式')

            command = ' && '.join(commands)
            job_line = f"{cron_time} {command} # task_id={current_task_id} task_name={task_name} config_id={config_id} task_mode={task_mode}"
            if not is_enabled:
                job_line = f"# {job_line}"
            updated_jobs.append(job_line)
        else:
            updated_jobs.append(job)

    if not task_found:
        raise ValueError('未找到指定的任务ID')

    update_crontab(updated_jobs)


def delete_tasks_from_cron(task_ids):
    cron_jobs = get_cron_jobs()
    task_ids_set = set(task_ids)
    updated_jobs = []
    for job in cron_jobs:
        clean_job = job.lstrip('# ').strip()
        task_info = extract_task_info(clean_job)
        current_task_id = task_info.get('task_id')
        if current_task_id not in task_ids_set:
            updated_jobs.append(job)
    update_crontab(updated_jobs)


def update_crontab(cron_jobs):
    cron_data = "\n".join(cron_jobs)
    subprocess.run(f'(echo "{cron_data}") | crontab -', shell=True)

    # 同步到备份文件
    backup_cron_jobs(cron_jobs)


# 将间隔类型转换为 cron 时间
def convert_to_cron_time(interval_type, interval_value):
    interval_value = int(interval_value)
    if interval_type == 'minute':
        if not 1 <= interval_value <= 59:
            raise ValueError('分钟间隔值必须在 1 到 59 之间')
        return f'*/{interval_value} * * * *'
    elif interval_type == 'hourly':
        if not 1 <= interval_value <= 23:
            raise ValueError('小时间隔值必须在 1 到 23 之间')
        return f'0 */{interval_value} * * *'
    elif interval_type == 'daily':
        if not 1 <= interval_value <= 31:
            raise ValueError('天数间隔值必须在 1 到 31 之间')
        return f'0 0 */{interval_value} * *'
    elif interval_type == 'weekly':
        if not 0 <= interval_value <= 6:
            raise ValueError('星期值必须在 0（周日）到 6（周六）之间')
        return f'0 0 * * {interval_value}'
    elif interval_type == 'monthly':
        if not 1 <= interval_value <= 12:
            raise ValueError('月份间隔值必须在 1 到 12 之间')
        return f'0 0 1 */{interval_value} *'
    else:
        raise ValueError('不支持的间隔类型')


def determine_task_mode(command):
    if 'main.py' in command:
        return 'strm_creation'
    elif 'strm_validator.py' in command:
        if 'quick' in command:
            return 'strm_validation_quick'
        elif 'slow' in command:
            return 'strm_validation_slow'
    return None


def parse_cron_time(cron_time):
    cron_parts = cron_time.split()
    if len(cron_parts) != 5:
        return 'custom', '', '自定义时间'

    minute, hour, day, month, weekday = cron_parts

    if minute.startswith('*/') and hour == '*' and day == '*' and month == '*' and weekday == '*':
        interval_value = minute[2:]
        interval_type = 'minute'
        description = f"每 {interval_value} 分钟"
        return interval_type, interval_value, description
    elif minute == '0' and hour.startswith('*/') and day == '*' and month == '*' and weekday == '*':
        interval_value = hour[2:]
        interval_type = 'hourly'
        description = f"每 {interval_value} 小时"
        return interval_type, interval_value, description
    elif minute == '0' and hour == '0' and day.startswith('*/') and month == '*' and weekday == '*':
        interval_value = day[2:]
        interval_type = 'daily'
        description = f"每 {interval_value} 天"
        return interval_type, interval_value, description
    elif minute == '0' and hour == '0' and day == '*' and month == '*' and weekday != '*':
        interval_value = weekday
        interval_type = 'weekly'
        weekdays = {
            '0': '星期日',
            '1': '星期一',
            '2': '星期二',
            '3': '星期三',
            '4': '星期四',
            '5': '星期五',
            '6': '星期六'
        }
        weekday_name = weekdays.get(interval_value, interval_value)
        description = f"每周的 {weekday_name}"
        return interval_type, interval_value, description
    elif minute == '0' and hour == '0' and day == '1' and month.startswith('*/') and weekday == '*':
        interval_value = month[2:]
        interval_type = 'monthly'
        description = f"每 {interval_value} 个月"
        return interval_type, interval_value, description
    else:
        return 'custom', '', '自定义时间'


def run_task_immediately(task_id):
    tasks = list_tasks_in_cron()

    task_to_run = next((task for task in tasks if task.get('task_id') == task_id), None)

    if task_to_run:
        command = task_to_run.get('command')
        if not command:
            raise ValueError('找不到该任务的命令，无法运行。')

        try:
            subprocess.Popen(command, shell=True)
            print(f"任务 {task_id} 已立即运行。")
        except Exception as e:
            print(f"运行任务 {task_id} 时发生错误: {e}")
    else:
        raise ValueError(f"找不到 task_id 为 {task_id} 的任务。")
