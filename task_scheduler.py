import subprocess
import os
import sys
import uuid  # 用于生成唯一的 task_id

# 获取当前的 crontab 任务列表
def get_cron_jobs():
    result = subprocess.run(['crontab', '-l'], stdout=subprocess.PIPE, text=True)
    cron_jobs = result.stdout.strip().split('\n') if result.stdout else []
    return cron_jobs

def extract_task_info(job_line):
    # Determine if the job is enabled
    is_enabled = not job_line.strip().startswith('#')
    # Remove any leading '#' and whitespace
    clean_job_line = job_line.lstrip('#').strip()
    parts = clean_job_line.split('#', 1)
    schedule_command = parts[0].strip()
    metadata = parts[1].strip() if len(parts) > 1 else ''

    # 提取 cron_time 和 command
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
    # 确定任务模式
    task_info['task_mode'] = determine_task_mode(command)
    # 解析 interval_type 和 interval_value 和 description
    interval_type, interval_value, description = parse_cron_time(cron_time)
    task_info['interval_type'] = interval_type
    task_info['interval_value'] = interval_value
    task_info['interval_description'] = description  # 添加描述

    # 将 config_id 转换为字符串
    if 'config_id' in task_info:
        task_info['config_id'] = str(task_info['config_id'])

    return task_info



def list_tasks_in_cron():
    cron_jobs = get_cron_jobs()
    program_managed_tasks = []
    for job in cron_jobs:
        # 检查任务是否包含 task_id 和 config_id
        if "# task_id=" in job and "config_id=" in job:
            task_info = extract_task_info(job)
            program_managed_tasks.append(task_info)
    return program_managed_tasks




# 添加任务到 crontab，接收多个 config_id，返回生成的 task_id 列表
def add_tasks_to_cron(task_name, cron_time, config_ids, task_mode, is_enabled=True):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    task_ids = []  # 用于保存生成的 task_id 列表
    cron_jobs = get_cron_jobs()

    for config_id in config_ids:
        task_id = str(uuid.uuid4())  # 自动生成唯一的 task_id

        # 构建命令
        commands = []
        if task_mode == 'strm_creation':
            # 运行 main.py，传入 task_id
            cmd_main = f'cd "{script_dir}" && /usr/local/bin/python3.9 "{script_dir}/main.py" {config_id} {task_id}'
            commands.append(cmd_main)
        elif task_mode == 'strm_validation_quick':
            # 运行 strm_validator.py，快速扫描，传入 task_id
            cmd_validator = f'cd "{script_dir}" && /usr/local/bin/python3.9 "{script_dir}/strm_validator.py" {config_id} quick {task_id}'
            commands.append(cmd_validator)
        elif task_mode == 'strm_validation_slow':
            # 运行 strm_validator.py，慢速扫描，传入 task_id
            cmd_validator = f'cd "{script_dir}" && /usr/local/bin/python3.9 "{script_dir}/strm_validator.py" {config_id} slow {task_id}'
            commands.append(cmd_validator)
        else:
            raise ValueError('不支持的任务模式')

        # 将命令组合起来
        command = ' && '.join(commands)
        # 新的 cron 任务格式：cron_time command # task_id=xxx task_name=xxx config_id=xxx
        cron_entry = f"{cron_time} {command} # task_id={task_id} task_name={task_name} config_id={config_id} task_mode={task_mode}"
        # 如果任务被禁用，添加注释符号
        if not is_enabled:
            cron_entry = f"# {cron_entry}"
        cron_jobs.append(cron_entry)
        task_ids.append(task_id)

    # 更新 crontab
    update_crontab(cron_jobs)
    return task_ids  # 返回生成的 task_id 列表

# 更新 cron 中的任务，接收多个 task_id
def update_tasks_in_cron(task_ids, cron_time=None, config_ids=None, task_mode=None, task_name=None, is_enabled=None):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cron_jobs = get_cron_jobs()
    updated_jobs = []
    task_ids_set = set(task_ids)
    task_found = False

    for job in cron_jobs:
        # 保留原始的注释状态
        is_job_enabled = not job.strip().startswith('#')
        clean_job = job.lstrip('# ').strip()
        task_info = extract_task_info(clean_job)
        current_task_id = task_info.get('task_id')
        if current_task_id in task_ids_set:
            task_found = True
            # 使用新的参数更新任务信息，如果提供了新的参数
            if cron_time is None:
                cron_time = task_info['cron_time']
            if task_name is None:
                task_name = task_info.get('task_name', 'Updated Task')
            if config_ids is None:
                # 使用原有的 config_id
                config_id = task_info.get('config_id')
            else:
                # 根据 task_id 找到对应的 config_id
                index = task_ids.index(current_task_id)
                config_id = config_ids[index] if index < len(config_ids) else task_info.get('config_id')
            if task_mode is None:
                task_mode = task_info.get('task_mode')
            if is_enabled is None:
                is_enabled = is_job_enabled  # 保持原有的启用状态

            # 重新构建命令
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
            # 根据 is_enabled 设置注释符号
            if not is_enabled:
                job_line = f"# {job_line}"
            updated_jobs.append(job_line)
        else:
            updated_jobs.append(job)

    if not task_found:
        raise ValueError('未找到指定的任务ID')

    update_crontab(updated_jobs)

# 删除 cron 中的任务，接收多个 task_id
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

# 写入新的 crontab 配置
def update_crontab(cron_jobs):
    cron_data = "\n".join(cron_jobs)
    subprocess.run(f'(echo "{cron_data}") | crontab -', shell=True)

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

# 辅助函数：确定任务模式
def determine_task_mode(command):
    if 'main.py' in command:
        return 'strm_creation'
    elif 'strm_validator.py' in command:
        if 'quick' in command:
            return 'strm_validation_quick'
        elif 'slow' in command:
            return 'strm_validation_slow'
    return None

# 辅助函数：解析 cron_time 为 interval_type 和 interval_value
def parse_cron_time(cron_time):
    cron_parts = cron_time.split()
    if len(cron_parts) != 5:
        return 'custom', '', '自定义时间'  # 返回一个描述

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
