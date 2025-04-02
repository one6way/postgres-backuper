from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.operators.bash_operator import BashOperator
from airflow.exceptions import AirflowException
from airflow.models import Variable
from datetime import datetime, timedelta
import os
import subprocess
import sys

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

# Функция для получения параметров подключения
def get_connection_params():
    """Получение параметров подключения из переменных Airflow"""
    return {
        'host': Variable.get('PG_HOST', 'localhost'),
        'port': Variable.get('PG_PORT', '5432'),
        'database': Variable.get('PG_DB', 'postgres'),
        'user': Variable.get('PG_USER', 'postgres'),
        'jdbc_url': Variable.get('PG_JDBC_URL', None),  # Опциональный JDBC URL
        'minio_endpoint': Variable.get('MINIO_ENDPOINT', 'https://minio.vanek-test.com'),
        'minio_bucket': Variable.get('MINIO_BUCKET', 'postgres-backup'),
        'minio_access_key': Variable.get('MINIO_ACCESS_KEY', 'minioadmin'),
        'minio_secret_key': Variable.get('MINIO_SECRET_KEY', 'minioadmin'),
    }

def run_command(cmd):
    """Запуск команды с проверкой результата"""
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        error_msg = f"Ошибка выполнения команды: {cmd}\n{stderr.decode('utf-8')}"
        print(error_msg)
        raise Exception(error_msg)
    return stdout.decode('utf-8')

def check_postgres():
    """Проверка подключения к PostgreSQL"""
    print("Проверка подключения к PostgreSQL...")
    try:
        cmd = f"pg_isready -h {PG_HOST} -p {PG_PORT} -d {PG_DB} -U {PG_USER}"
        run_command(cmd)
        print("Соединение с PostgreSQL успешно установлено.")
    except Exception as e:
        raise AirflowException(f"Не удалось подключиться к PostgreSQL: {str(e)}")

def setup_minio_config(**context):
    """Настройка конфигурации AWS CLI для MinIO"""
    params = get_connection_params()
    
    os.makedirs(os.path.expanduser('~/.aws'), exist_ok=True)
    
    with open(os.path.expanduser('~/.aws/credentials'), 'w') as f:
        f.write(f"""[minio]
aws_access_key_id = {params['minio_access_key']}
aws_secret_access_key = {params['minio_secret_key']}
""")
    
    with open(os.path.expanduser('~/.aws/config'), 'w') as f:
        f.write("""[profile minio]
s3 =
    path_style_access = true
""")

def create_backup(**context):
    """Создание бэкапа с поддержкой кастомных параметров"""
    params = get_connection_params()
    date = context['ds_nodash']
    backup_dir = '/tmp/postgres_backup'
    os.makedirs(backup_dir, exist_ok=True)
    
    try:
        # Формируем команду для бэкапа
        if params['jdbc_url']:
            # Используем JDBC URL если он предоставлен
            backup_cmd = f"pg_dump '{params['jdbc_url']}'"
        else:
            # Используем отдельные параметры подключения
            backup_cmd = f"pg_dump -h {params['host']} -p {params['port']} -U {params['user']} -d {params['database']}"
        
        # Добавляем сжатие и сохранение
        backup_file = f"{backup_dir}/backup_{date}.sql.gz"
        backup_cmd = f"{backup_cmd} | gzip > {backup_file}"
        
        # Выполняем бэкап
        run_command(backup_cmd)
        
        # Загружаем в MinIO
        s3_cmd = f"aws s3 cp {backup_file} s3://{params['minio_bucket']}/backups/backup_{date}.sql.gz --endpoint-url {params['minio_endpoint']} --profile minio --no-verify-ssl"
        run_command(s3_cmd)
        
        # Очищаем временные файлы
        os.remove(backup_file)
        
    except Exception as e:
        if os.path.exists(backup_file):
            os.remove(backup_file)
        raise e

def restore_backup(**context):
    """Восстановление из бэкапа с поддержкой кастомных параметров"""
    params = get_connection_params()
    backup_dir = '/tmp/postgres_backup'
    os.makedirs(backup_dir, exist_ok=True)
    
    try:
        # Получаем список бэкапов
        s3_ls_cmd = f"aws s3 ls s3://{params['minio_bucket']}/backups/ --endpoint-url {params['minio_endpoint']} --profile minio --no-verify-ssl"
        backups = run_command(s3_ls_cmd).strip().split('\n')
        
        # Находим нужный бэкап
        backup_date = context.get('params', {}).get('backup_date', None)
        if backup_date:
            # Ищем конкретный бэкап по дате
            backup_file = f"backup_{backup_date}.sql.gz"
            if not any(backup_file in b for b in backups):
                raise Exception(f"Бэкап за дату {backup_date} не найден")
        else:
            # Берем последний бэкап
            backup_file = backups[-1].split()[-1]
        
        # Скачиваем бэкап
        local_file = f"{backup_dir}/{backup_file}"
        s3_cp_cmd = f"aws s3 cp s3://{params['minio_bucket']}/backups/{backup_file} {local_file} --endpoint-url {params['minio_endpoint']} --profile minio --no-verify-ssl"
        run_command(s3_cp_cmd)
        
        # Формируем команду для восстановления
        if params['jdbc_url']:
            restore_cmd = f"psql '{params['jdbc_url']}'"
        else:
            restore_cmd = f"psql -h {params['host']} -p {params['port']} -U {params['user']} -d {params['database']}"
        
        # Выполняем восстановление
        restore_cmd = f"gunzip -c {local_file} | {restore_cmd}"
        run_command(restore_cmd)
        
        # Очищаем временные файлы
        os.remove(local_file)
        
    except Exception as e:
        if 'local_file' in locals() and os.path.exists(local_file):
            os.remove(local_file)
        raise e

# Создаем DAG
dag = DAG(
    'postgres_backup_dag',
    default_args=default_args,
    description='PostgreSQL backup and restore DAG with custom parameters support',
    schedule_interval='0 0 * * *',
    catchup=False,
    tags=['postgres', 'backup'],
)

# Задача проверки подключения к PostgreSQL
check_postgres_task = PythonOperator(
    task_id='check_postgres',
    python_callable=check_postgres,
    dag=dag,
)

# Задача настройки MinIO
setup_config_task = PythonOperator(
    task_id='setup_minio_config',
    python_callable=setup_minio_config,
    dag=dag,
)

# Задача создания бэкапа
backup_task = PythonOperator(
    task_id='backup_postgres',
    python_callable=create_backup,
    dag=dag,
)

# Задача восстановления с поддержкой параметра даты
restore_task = PythonOperator(
    task_id='restore_postgres',
    python_callable=restore_backup,
    dag=dag,
    trigger_rule='manual',  # Только ручной запуск
)

# Определяем зависимости
check_postgres_task >> setup_config_task >> backup_task >> restore_task 