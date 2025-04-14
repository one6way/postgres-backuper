from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
import os
import shutil
from pathlib import Path

# Конфигурация
BACKUP_DIR = "/var/lib/postgresql/backups"
RETENTION_DAYS = 30

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

def ensure_backup_dir():
    """Создает директорию для бэкапов если её нет"""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    os.chmod(BACKUP_DIR, 0o700)
    # Устанавливаем владельца (требует прав root)
    os.system(f"chown postgres:postgres {BACKUP_DIR}")

def create_backup(**context):
    """Создает бэкап базы данных"""
    date = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"{BACKUP_DIR}/backup_{date}.sql.gz"
    
    # Получаем параметры подключения из переменных Airflow
    pg_host = context['var']['value'].get('pg_host')
    pg_port = context['var']['value'].get('pg_port', '5432')
    pg_db = context['var']['value'].get('pg_db')
    pg_user = context['var']['value'].get('pg_user')
    
    # Создаем бэкап
    cmd = f"pg_dump -h {pg_host} -p {pg_port} -U {pg_user} -d {pg_db} | gzip > {backup_file}"
    os.system(cmd)
    
    # Устанавливаем права на файл
    os.chmod(backup_file, 0o600)
    os.system(f"chown postgres:postgres {backup_file}")
    
    return backup_file

def rotate_backups():
    """Удаляет старые бэкапы"""
    cutoff_date = datetime.now() - timedelta(days=RETENTION_DAYS)
    for backup_file in Path(BACKUP_DIR).glob("backup_*.sql.gz"):
        if datetime.fromtimestamp(backup_file.stat().st_mtime) < cutoff_date:
            backup_file.unlink()

def check_disk_space():
    """Проверяет наличие свободного места"""
    total, used, free = shutil.disk_usage(BACKUP_DIR)
    required_space = 1024 * 1024 * 1024  # 1GB в байтах
    
    if free < required_space:
        raise Exception(f"Недостаточно свободного места. Требуется: {required_space/1024/1024}MB, Доступно: {free/1024/1024}MB")

with DAG(
    'postgres_backup_local',
    default_args=default_args,
    description='DAG для локального бэкапа PostgreSQL',
    schedule_interval='@daily',
    start_date=datetime(2024, 1, 1),
    catchup=False,
) as dag:

    ensure_dir = PythonOperator(
        task_id='ensure_backup_dir',
        python_callable=ensure_backup_dir,
    )

    check_space = PythonOperator(
        task_id='check_disk_space',
        python_callable=check_disk_space,
    )

    create_backup = PythonOperator(
        task_id='create_backup',
        python_callable=create_backup,
        provide_context=True,
    )

    rotate_backups = PythonOperator(
        task_id='rotate_backups',
        python_callable=rotate_backups,
    )

    # Определяем порядок выполнения задач
    ensure_dir >> check_space >> create_backup >> rotate_backups 