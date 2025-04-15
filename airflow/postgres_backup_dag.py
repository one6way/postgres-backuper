from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.exceptions import AirflowException
from airflow.models import Variable
from airflow.hooks.base import BaseHook
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
    """Получение параметров подключения из Airflow Connections"""
    try:
        # Получаем PostgreSQL connection
        pg_conn = BaseHook.get_connection('postgres_default')
        if not all([pg_conn.host, pg_conn.port, pg_conn.schema, pg_conn.login, pg_conn.password]):
            raise AirflowException("Не все параметры подключения к PostgreSQL указаны в Connection")
        
        # Получаем MinIO connection
        minio_conn = BaseHook.get_connection('minio_default')
        if not all([minio_conn.host, minio_conn.login, minio_conn.password]):
            raise AirflowException("Не все параметры подключения к MinIO указаны в Connection")
        
        return {
            'host': pg_conn.host,
            'port': pg_conn.port,
            'database': pg_conn.schema,
            'user': pg_conn.login,
            'password': pg_conn.password,
            'jdbc_url': pg_conn.get_uri(),  # Полный JDBC URL
            'minio_endpoint': minio_conn.host,
            'minio_bucket': Variable.get('MINIO_BUCKET', 'postgres-backup'),  # Бакет можно оставить в переменных
            'minio_access_key': minio_conn.login,
            'minio_secret_key': minio_conn.password,
        }
    except Exception as e:
        raise AirflowException(f"Ошибка при получении параметров подключения: {str(e)}")

def run_command(cmd):
    """Запуск команды с проверкой результата"""
    try:
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            error_msg = f"Ошибка выполнения команды: {cmd}\n{stderr.decode('utf-8')}"
            print(error_msg)
            raise Exception(error_msg)
        return stdout.decode('utf-8')
    except Exception as e:
        raise AirflowException(f"Ошибка при выполнении команды: {str(e)}")

def check_postgres(**context):
    """Проверка подключения к PostgreSQL"""
    print("Проверка подключения к PostgreSQL...")
    try:
        params = get_connection_params()
        cmd = f"pg_isready -h {params['host']} -p {params['port']} -d {params['database']} -U {params['user']}"
        run_command(cmd)
        print("Соединение с PostgreSQL успешно установлено.")
    except Exception as e:
        raise AirflowException(f"Не удалось подключиться к PostgreSQL: {str(e)}")

def setup_minio_config(**context):
    """Настройка конфигурации AWS CLI для MinIO"""
    try:
        params = get_connection_params()
        
        aws_dir = os.path.expanduser('~/.aws')
        os.makedirs(aws_dir, exist_ok=True)
        
        # Создаем credentials файл
        credentials_path = os.path.join(aws_dir, 'credentials')
        with open(credentials_path, 'w') as f:
            f.write(f"""[minio]
aws_access_key_id = {params['minio_access_key']}
aws_secret_access_key = {params['minio_secret_key']}
""")
        os.chmod(credentials_path, 0o600)  # Только владелец имеет доступ
        
        # Создаем config файл
        config_path = os.path.join(aws_dir, 'config')
        with open(config_path, 'w') as f:
            f.write("""[profile minio]
s3 =
    path_style_access = true
""")
        os.chmod(config_path, 0o600)  # Только владелец имеет доступ
        
    except Exception as e:
        raise AirflowException(f"Ошибка при настройке конфигурации MinIO: {str(e)}")

def create_backup(**context):
    """Создание бэкапа с поддержкой кастомных параметров"""
    try:
        params = get_connection_params()
        date = context['ds_nodash']
        backup_dir = '/tmp/postgres_backup'
        os.makedirs(backup_dir, exist_ok=True)
        
        # Формируем команду для бэкапа
        backup_cmd = f"pg_dump '{params['jdbc_url']}'"
        
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
        if 'backup_file' in locals() and os.path.exists(backup_file):
            os.remove(backup_file)
        raise AirflowException(f"Ошибка при создании бэкапа: {str(e)}")

def restore_backup(**context):
    """Восстановление из бэкапа с поддержкой кастомных параметров"""
    try:
        params = get_connection_params()
        backup_dir = '/tmp/postgres_backup'
        os.makedirs(backup_dir, exist_ok=True)
        
        # Получаем список бэкапов
        s3_ls_cmd = f"aws s3 ls s3://{params['minio_bucket']}/backups/ --endpoint-url {params['minio_endpoint']} --profile minio --no-verify-ssl"
        backups = run_command(s3_ls_cmd).strip().split('\n')
        
        if not backups or not any(backups):
            raise AirflowException("Нет доступных бэкапов для восстановления")
        
        # Находим нужный бэкап
        backup_date = context.get('params', {}).get('backup_date', None)
        if backup_date:
            # Ищем конкретный бэкап по дате
            backup_file = f"backup_{backup_date}.sql.gz"
            if not any(backup_file in b for b in backups):
                raise AirflowException(f"Бэкап за дату {backup_date} не найден")
        else:
            # Берем последний бэкап
            backup_file = backups[-1].split()[-1]
        
        # Скачиваем бэкап
        local_file = f"{backup_dir}/{backup_file}"
        s3_cp_cmd = f"aws s3 cp s3://{params['minio_bucket']}/backups/{backup_file} {local_file} --endpoint-url {params['minio_endpoint']} --profile minio --no-verify-ssl"
        run_command(s3_cp_cmd)
        
        # Выполняем восстановление
        restore_cmd = f"gunzip -c {local_file} | psql '{params['jdbc_url']}'"
        run_command(restore_cmd)
        
        # Очищаем временные файлы
        os.remove(local_file)
        
    except Exception as e:
        if 'local_file' in locals() and os.path.exists(local_file):
            os.remove(local_file)
        raise AirflowException(f"Ошибка при восстановлении из бэкапа: {str(e)}")

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
    trigger_rule='all_success',
    depends_on_past=False,
)

# Определяем зависимости
check_postgres_task >> setup_config_task >> backup_task >> restore_task 