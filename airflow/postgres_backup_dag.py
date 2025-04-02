from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.operators.bash_operator import BashOperator
from airflow.exceptions import AirflowException
from datetime import datetime, timedelta
import os
import subprocess
import sys

# Конфигурация
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Переменные окружения
PG_HOST = os.getenv('PG_HOST', 'localhost')
PG_PORT = os.getenv('PG_PORT', '5432')
PG_DB = os.getenv('PG_DB', 'postgres')
PG_USER = os.getenv('PG_USER', 'postgres')
MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'https://minio.vanek-test.com')
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'minioadmin')
MINIO_BUCKET = os.getenv('MINIO_BUCKET', 'postgres-backup')
BACKUP_DIR = '/tmp/postgres_backup'

# Создаем DAG
dag = DAG(
    'postgres_backup_dag',
    default_args=default_args,
    description='PostgreSQL backup and restore DAG',
    schedule_interval='0 0 * * *',  # Запуск каждый день в полночь
    catchup=False,
    tags=['postgres', 'backup'],
)

def run_command(cmd):
    """Запуск команды с проверкой результата"""
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        error_msg = f"Ошибка выполнения команды: {cmd}\n{stderr.decode('utf-8')}"
        print(error_msg)
        raise AirflowException(error_msg)
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

def setup_minio_config():
    """Настройка конфигурации AWS CLI для MinIO"""
    print("Настройка конфигурации AWS CLI для MinIO...")
    try:
        os.makedirs(os.path.expanduser('~/.aws'), exist_ok=True)
        
        # Создаем credentials
        with open(os.path.expanduser('~/.aws/credentials'), 'w') as f:
            f.write(f"""[minio]
aws_access_key_id = {MINIO_ACCESS_KEY}
aws_secret_access_key = {MINIO_SECRET_KEY}
""")
        
        # Создаем config с path-style access
        with open(os.path.expanduser('~/.aws/config'), 'w') as f:
            f.write("""[profile minio]
s3 =
    path_style_access = true
""")
        print("Конфигурация AWS CLI для MinIO успешно настроена.")
        
        # Проверяем доступность MinIO
        print("Проверка подключения к MinIO...")
        run_command(f"aws s3 ls --endpoint-url {MINIO_ENDPOINT} --profile minio --no-verify-ssl")
        print("Соединение с MinIO успешно установлено.")
        
        # Проверяем существование бакета
        try:
            run_command(f"aws s3 ls s3://{MINIO_BUCKET} --endpoint-url {MINIO_ENDPOINT} --profile minio --no-verify-ssl")
            print(f"Бакет {MINIO_BUCKET} существует.")
        except AirflowException:
            print(f"Бакет {MINIO_BUCKET} не существует. Создаем...")
            run_command(f"aws s3 mb s3://{MINIO_BUCKET} --endpoint-url {MINIO_ENDPOINT} --profile minio --no-verify-ssl")
            print(f"Бакет {MINIO_BUCKET} успешно создан.")
    except Exception as e:
        raise AirflowException(f"Ошибка настройки MinIO: {str(e)}")

# Функция для создания бэкапа
def create_backup(**context):
    print("Начинаем создание бэкапа...")
    
    # Проверяем подключение к PostgreSQL
    check_postgres()
    
    date = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = f"{BACKUP_DIR}/backup_{date}.sql.gz"
    
    # Создаем директорию для бэкапа
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    try:
        # Создаем бэкап
        print(f"Создание бэкапа PostgreSQL в {backup_file}...")
        backup_cmd = f"pg_dump -h {PG_HOST} -p {PG_PORT} -U {PG_USER} -d {PG_DB} | gzip > {backup_file}"
        run_command(backup_cmd)
        
        # Загружаем в MinIO S3
        print(f"Загрузка бэкапа в MinIO S3 bucket {MINIO_BUCKET}...")
        s3_cmd = f"aws s3 cp {backup_file} s3://{MINIO_BUCKET}/backups/backup_{date}.sql.gz --endpoint-url {MINIO_ENDPOINT} --profile minio --no-verify-ssl"
        run_command(s3_cmd)
        
        # Удаляем локальный файл
        os.remove(backup_file)
        print("Бэкап успешно создан и загружен в MinIO S3.")
    except Exception as e:
        if os.path.exists(backup_file):
            os.remove(backup_file)
        raise AirflowException(f"Ошибка создания бэкапа: {str(e)}")

# Функция для восстановления
def restore_backup(**context):
    print("Начинаем восстановление из бэкапа...")
    
    # Проверяем подключение к PostgreSQL
    check_postgres()
    
    try:
        # Получаем последний бэкап из MinIO S3
        print("Поиск последнего бэкапа в MinIO S3...")
        s3_ls_cmd = f"aws s3 ls s3://{MINIO_BUCKET}/backups/ --endpoint-url {MINIO_ENDPOINT} --profile minio --no-verify-ssl | sort | tail -n 1 | awk '{{print $4}}'"
        last_backup = run_command(s3_ls_cmd).strip()
        
        if not last_backup:
            raise AirflowException("Бэкапы не найдены в MinIO S3")
        
        print(f"Найден бэкап: {last_backup}")
        
        # Создаем директорию для временных файлов
        os.makedirs(BACKUP_DIR, exist_ok=True)
        
        # Скачиваем бэкап
        print(f"Скачивание бэкапа из MinIO S3...")
        s3_cp_cmd = f"aws s3 cp s3://{MINIO_BUCKET}/backups/{last_backup} {BACKUP_DIR}/{last_backup} --endpoint-url {MINIO_ENDPOINT} --profile minio --no-verify-ssl"
        run_command(s3_cp_cmd)
        
        # Распаковываем и восстанавливаем
        print("Восстановление базы данных из бэкапа...")
        restore_cmd = f"gunzip -c {BACKUP_DIR}/{last_backup} | psql -h {PG_HOST} -p {PG_PORT} -U {PG_USER} -d {PG_DB}"
        run_command(restore_cmd)
        
        # Удаляем локальный файл
        os.remove(f"{BACKUP_DIR}/{last_backup}")
        print("Восстановление из бэкапа успешно завершено.")
    except Exception as e:
        backup_path = os.path.join(BACKUP_DIR, last_backup) if 'last_backup' in locals() else None
        if backup_path and os.path.exists(backup_path):
            os.remove(backup_path)
        raise AirflowException(f"Ошибка восстановления из бэкапа: {str(e)}")

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
    trigger_rule='manual',  # Только ручной запуск
)

# Определяем зависимости
check_postgres_task >> setup_config_task >> backup_task >> restore_task 