from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.exceptions import AirflowException
from airflow.models import Variable
from airflow.hooks.base import BaseHook
import os
import shutil
from pathlib import Path
import subprocess
import psycopg2
import platform

# Конфигурация по умолчанию
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Путь к директории с бэкапами
BACKUP_DIR = '/var/lib/postgresql/backups'
RETENTION_DAYS = 30

# Функция для получения параметров подключения
def get_connection_params():
    """Получение параметров подключения из Airflow Connections"""
    try:
        # Получаем PostgreSQL connection
        pg_conn = BaseHook.get_connection('postgres_default')
        
        if not all([pg_conn.host, pg_conn.port, pg_conn.schema, pg_conn.login, pg_conn.password]):
            raise AirflowException("Не все параметры подключения к PostgreSQL указаны в Connection")
        
        return {
            'host': pg_conn.host,
            'port': pg_conn.port,
            'database': pg_conn.schema,
            'user': pg_conn.login,
            'password': pg_conn.password,
            'backup_dir': BACKUP_DIR,
            'retention_days': RETENTION_DAYS
        }
    except Exception as e:
        raise AirflowException(f"Ошибка при получении параметров подключения: {str(e)}")

def ensure_backup_dir():
    """Создание директории для бэкапов"""
    try:
        params = get_connection_params()
        backup_dir = Path(params['backup_dir'])
        
        if not backup_dir.exists():
            backup_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(backup_dir, 0o700)  # Только владелец имеет доступ
    except Exception as e:
        raise AirflowException(f"Ошибка при создании директории для бэкапов: {str(e)}")

def create_backup(**context):
    """Создание бэкапа базы данных"""
    try:
        params = get_connection_params()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = f"{params['backup_dir']}/backup_{timestamp}.sql"
        
        # Команда для создания бэкапа
        cmd = [
            'pg_dump',
            '-h', params['host'],
            '-p', str(params['port']),
            '-U', params['user'],
            '-d', params['database'],
            '-f', backup_file
        ]
        
        # Устанавливаем переменную окружения с паролем
        env = os.environ.copy()
        env['PGPASSWORD'] = params['password']
        
        result = subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
        context['ti'].xcom_push(key='backup_file', value=backup_file)
        return f"Backup created successfully: {backup_file}"
    except subprocess.CalledProcessError as e:
        raise AirflowException(f"Backup failed: {str(e)}\nOutput: {e.output}\nError: {e.stderr}")
    except Exception as e:
        raise AirflowException(f"Unexpected error during backup: {str(e)}")

def rotate_backups(**context):
    """Удаление старых бэкапов"""
    try:
        params = get_connection_params()
        backup_dir = Path(params['backup_dir'])
        retention_days = params['retention_days']
        
        current_time = datetime.now()
        for backup_file in backup_dir.glob('backup_*.sql'):
            file_time = datetime.fromtimestamp(backup_file.stat().st_mtime)
            if (current_time - file_time).days > retention_days:
                backup_file.unlink()
    except Exception as e:
        raise AirflowException(f"Ошибка при ротации бэкапов: {str(e)}")

def check_disk_space(**context):
    """Проверка свободного места на диске"""
    try:
        params = get_connection_params()
        backup_dir = Path(params['backup_dir'])
        
        if platform.system() == 'Windows':
            # Для Windows используем другой метод
            total, used, free = shutil.disk_usage(backup_dir)
            free_space_gb = free / (1024 * 1024 * 1024)
        else:
            # Для Unix-подобных систем используем statvfs
            stat = os.statvfs(backup_dir)
            free_space_gb = (stat.f_bavail * stat.f_frsize) / (1024 * 1024 * 1024)
        
        if free_space_gb < 5:  # Минимум 5GB свободного места
            raise AirflowException(f"Insufficient disk space: {free_space_gb:.2f}GB available")
    except Exception as e:
        raise AirflowException(f"Ошибка при проверке свободного места: {str(e)}")

# Определение DAG
dag = DAG(
    'postgres_backup_local',
    default_args=default_args,
    description='Local PostgreSQL backup DAG',
    schedule_interval='@daily',
    catchup=False,
    tags=['postgres', 'backup', 'local'],
)

# Задачи DAG
ensure_dir_task = PythonOperator(
    task_id='ensure_backup_dir',
    python_callable=ensure_backup_dir,
    dag=dag
)

check_space_task = PythonOperator(
    task_id='check_disk_space',
    python_callable=check_disk_space,
    provide_context=True,
    dag=dag
)

create_backup_task = PythonOperator(
    task_id='create_backup',
    python_callable=create_backup,
    provide_context=True,
    dag=dag
)

rotate_backups_task = PythonOperator(
    task_id='rotate_backups',
    python_callable=rotate_backups,
    provide_context=True,
    dag=dag
)

# Определение порядка выполнения задач
ensure_dir_task >> check_space_task >> create_backup_task >> rotate_backups_task 