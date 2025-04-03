from airflow import DAG
from airflow.operators.python_operator import PythonOperator, BranchPythonOperator
from airflow.operators.bash_operator import BashOperator
from airflow.exceptions import AirflowException
from airflow.hooks.base_hook import BaseHook
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

def get_connection_params():
    """Получение параметров подключения из коннекторов Airflow"""
    # Получаем параметры PostgreSQL из коннектора
    pg_conn = BaseHook.get_connection('postgres_backup_db')
    
    # Получаем параметры MinIO из коннектора
    minio_conn = BaseHook.get_connection('minio_backup')
    
    # Извлекаем дополнительные параметры из extras
    minio_extras = minio_conn.extra_dejson
    
    return {
        # PostgreSQL параметры
        'host': pg_conn.host or 'localhost',
        'port': pg_conn.port or 5432,
        'database': pg_conn.schema or 'postgres',
        'user': pg_conn.login or 'postgres',
        'password': pg_conn.password,
        'jdbc_url': pg_conn.extra_dejson.get('jdbc_url', None),
        
        # MinIO параметры
        'minio_endpoint': minio_conn.host or 'https://minio.vanek-test.com',
        'minio_port': minio_conn.port,
        'minio_bucket': minio_extras.get('bucket', 'postgres-backup'),
        'minio_access_key': minio_conn.login or 'minioadmin',
        'minio_secret_key': minio_conn.password or 'minioadmin',
    }

def choose_operation(**context):
    """Выбор операции на основе параметров запуска"""
    params = context['dag_run'].conf or {}
    operation = params.get('operation', 'backup')
    
    if operation == 'backup':
        return 'backup_postgres'
    elif operation == 'restore':
        return 'restore_postgres'
    elif operation == 'backup_and_restore':
        return 'backup_postgres'  # Начнем с бэкапа, потом перейдем к восстановлению
    else:
        raise AirflowException(f"Неизвестная операция: {operation}")

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
    params = get_connection_params()
    try:
        if params['jdbc_url']:
            cmd = f"pg_isready -d '{params['jdbc_url']}'"
        else:
            cmd = f"pg_isready -h {params['host']} -p {params['port']} -d {params['database']} -U {params['user']}"
        run_command(cmd)
        print("Соединение с PostgreSQL успешно установлено.")
    except Exception as e:
        raise AirflowException(f"Не удалось подключиться к PostgreSQL: {str(e)}")

def setup_minio_config(**context):
    """Настройка конфигурации AWS CLI для MinIO"""
    params = get_connection_params()
    
    os.makedirs(os.path.expanduser('~/.aws'), exist_ok=True)
    
    # Создаем конфигурацию с данными из коннектора
    with open(os.path.expanduser('~/.aws/credentials'), 'w') as f:
        f.write(f"""[minio]
aws_access_key_id = {params['minio_access_key']}
aws_secret_access_key = {params['minio_secret_key']}
""")
    
    endpoint = params['minio_endpoint']
    if params['minio_port']:
        endpoint = f"{endpoint}:{params['minio_port']}"
    
    with open(os.path.expanduser('~/.aws/config'), 'w') as f:
        f.write(f"""[profile minio]
s3 =
    path_style_access = true
    endpoint_url = {endpoint}
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
            backup_cmd = f"pg_dump '{params['jdbc_url']}'"
        else:
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
        
        # Если это часть операции backup_and_restore, продолжаем с восстановлением
        dag_conf = context['dag_run'].conf or {}
        if dag_conf.get('operation') == 'backup_and_restore':
            return 'restore_postgres'
        
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
        dag_conf = context['dag_run'].conf or {}
        backup_date = dag_conf.get('backup_date', None)
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
    schedule_interval='0 0 * * *',  # По умолчанию каждый день в полночь
    catchup=False,
    tags=['postgres', 'backup'],
)

# Задача выбора операции
choose_operation_task = BranchPythonOperator(
    task_id='choose_operation',
    python_callable=choose_operation,
    dag=dag,
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

# Задача восстановления
restore_task = PythonOperator(
    task_id='restore_postgres',
    python_callable=restore_backup,
    dag=dag,
)

# Определяем зависимости
check_postgres_task >> setup_config_task >> choose_operation_task
choose_operation_task >> [backup_task, restore_task]
backup_task >> restore_task
