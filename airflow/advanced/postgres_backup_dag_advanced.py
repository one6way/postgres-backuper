from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.operators.bash_operator import BashOperator
from airflow.exceptions import AirflowException
from airflow.models import Variable
from airflow.hooks.base import BaseHook
from datetime import datetime, timedelta
import os
import subprocess
import sys
import concurrent.futures
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

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
    # Получаем PostgreSQL connection
    pg_conn = BaseHook.get_connection('postgres_default')
    
    # Получаем MinIO connection
    minio_conn = BaseHook.get_connection('minio_default')
    
    return {
        'host': pg_conn.host,
        'port': pg_conn.port,
        'database': pg_conn.schema,
        'user': pg_conn.login,
        'password': pg_conn.password,
        'jdbc_url': pg_conn.get_uri(),  # Полный JDBC URL
        'minio_endpoint': minio_conn.host,
        'minio_bucket': Variable.get('MINIO_BUCKET', 'postgres-backup'),
        'minio_path': Variable.get('MINIO_BACKUP_PATH', 'backups/postgres'),  # Добавляем путь
        'minio_access_key': minio_conn.login,
        'minio_secret_key': minio_conn.password,
        'parallel_jobs': Variable.get('PARALLEL_JOBS', '4'),
        'incremental_backup': Variable.get('INCREMENTAL_BACKUP', 'false'),
        'last_full_backup': Variable.get('LAST_FULL_BACKUP', ''),
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

def get_schemas():
    """Получение списка схем из базы данных"""
    params = get_connection_params()
    conn = psycopg2.connect(
        host=params['host'],
        port=params['port'],
        database=params['database'],
        user=params['user']
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("""
        SELECT schema_name 
        FROM information_schema.schemata 
        WHERE schema_name NOT IN ('pg_catalog', 'information_schema');
    """)
    schemas = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return schemas

def backup_schema(schema, date):
    """Бэкап отдельной схемы"""
    params = get_connection_params()
    backup_dir = '/tmp/postgres_backup'
    os.makedirs(backup_dir, exist_ok=True)
    
    backup_file = f"{backup_dir}/{schema}_{date}.sql.gz"
    
    if params['jdbc_url']:
        backup_cmd = f"pg_dump '{params['jdbc_url']}' -n {schema}"
    else:
        backup_cmd = f"pg_dump -h {params['host']} -p {params['port']} -U {params['user']} -d {params['database']} -n {schema}"
    
    backup_cmd = f"{backup_cmd} | gzip > {backup_file}"
    run_command(backup_cmd)
    
    return backup_file

def validate_backup(backup_file):
    """Валидация бэкапа"""
    temp_file = f"/tmp/validate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
    
    try:
        # Распаковываем бэкап
        run_command(f"gunzip -c {backup_file} > {temp_file}")
        
        # Проверяем структуру SQL
        with open(temp_file, 'r') as f:
            content = f.read()
            if 'CREATE TABLE' not in content:
                raise Exception("Бэкап не содержит определения таблиц")
            if 'COPY' not in content:
                raise Exception("Бэкап не содержит данных")
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)

def rotate_backups():
    """Ротация старых бэкапов"""
    params = get_connection_params()
    current_date = datetime.now()
    retention_date = current_date - timedelta(days=params['backup_retention_days'])
    
    # Получаем список бэкапов
    s3_ls_cmd = f"aws s3 ls s3://{params['minio_bucket']}/{params['minio_path']}/ --endpoint-url {params['minio_endpoint']} --profile minio --no-verify-ssl"
    backups = run_command(s3_ls_cmd).strip().split('\n')
    
    for backup in backups:
        if not backup:
            continue
            
        backup_date_str = ' '.join(backup.split()[:2])
        backup_date = datetime.strptime(backup_date_str, '%Y-%m-%d %H:%M:%S')
        
        if backup_date < retention_date:
            backup_name = backup.split()[-1]
            print(f"Удаляем старый бэкап: {backup_name}")
            s3_rm_cmd = f"aws s3 rm s3://{params['minio_bucket']}/{params['minio_path']}/{backup_name} --endpoint-url {params['minio_endpoint']} --profile minio --no-verify-ssl"
            run_command(s3_rm_cmd)

def incremental_backup(**context):
    """Инкрементальный бэкап измененных таблиц"""
    params = get_connection_params()
    if not params['last_full_backup']:
        raise AirflowException("Не указана дата последнего полного бэкапа")
    
    conn = psycopg2.connect(
        host=params['host'],
        port=params['port'],
        database=params['database'],
        user=params['user']
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    
    # Получаем список измененных таблиц
    cur.execute("""
        SELECT schemaname || '.' || tablename 
        FROM pg_stat_user_tables 
        WHERE last_analyze > %s OR last_autoanalyze > %s;
    """, (params['last_full_backup'], params['last_full_backup']))
    
    changed_tables = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    
    backup_dir = '/tmp/postgres_backup'
    os.makedirs(backup_dir, exist_ok=True)
    date = context['ds_nodash']
    
    for table in changed_tables:
        print(f"Backing up changed table: {table}")
        backup_file = f"{backup_dir}/incremental_{table.replace('.', '_')}_{date}.sql.gz"
        
        if params['jdbc_url']:
            backup_cmd = f"pg_dump '{params['jdbc_url']}' -t {table}"
        else:
            backup_cmd = f"pg_dump -h {params['host']} -p {params['port']} -U {params['user']} -d {params['database']} -t {table}"
        
        backup_cmd = f"{backup_cmd} | gzip > {backup_file}"
        run_command(backup_cmd)
        
        # Валидируем и загружаем в MinIO
        validate_backup(backup_file)
        s3_cmd = f"aws s3 cp {backup_file} s3://{params['minio_bucket']}/{params['minio_path']}/$(basename {backup_file}) --endpoint-url {params['minio_endpoint']} --profile minio --no-verify-ssl"
        run_command(s3_cmd)
        
        os.remove(backup_file)

def parallel_backup(**context):
    """Параллельный бэкап схем"""
    params = get_connection_params()
    schemas = get_schemas()
    date = context['ds_nodash']
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=params['parallel_jobs']) as executor:
        future_to_schema = {
            executor.submit(backup_schema, schema, date): schema 
            for schema in schemas
        }
        
        for future in concurrent.futures.as_completed(future_to_schema):
            schema = future_to_schema[future]
            try:
                backup_file = future.result()
                # Валидируем и загружаем в MinIO
                validate_backup(backup_file)
                s3_cmd = f"aws s3 cp {backup_file} s3://{params['minio_bucket']}/{params['minio_path']}/$(basename {backup_file}) --endpoint-url {params['minio_endpoint']} --profile minio --no-verify-ssl"
                run_command(s3_cmd)
                os.remove(backup_file)
            except Exception as e:
                print(f"Ошибка при бэкапе схемы {schema}: {str(e)}")
                raise

def create_backup(**context):
    """Создание бэкапа с поддержкой инкрементального и параллельного режимов"""
    params = get_connection_params()
    
    if params['incremental_backup']:
        incremental_backup(**context)
    else:
        parallel_backup(**context)
    
    # Выполняем ротацию
    rotate_backups()

def restore_backup(**context):
    """Восстановление из бэкапа с валидацией"""
    params = get_connection_params()
    backup_dir = '/tmp/postgres_backup'
    os.makedirs(backup_dir, exist_ok=True)
    
    try:
        # Получаем список бэкапов
        s3_ls_cmd = f"aws s3 ls s3://{params['minio_bucket']}/{params['minio_path']}/ --endpoint-url {params['minio_endpoint']} --profile minio --no-verify-ssl"
        backups = run_command(s3_ls_cmd).strip().split('\n')
        
        # Находим нужный бэкап
        backup_date = context.get('params', {}).get('backup_date', None)
        if backup_date:
            backup_file = f"backup_{backup_date}.sql.gz"
            if not any(backup_file in b for b in backups):
                raise Exception(f"Бэкап за дату {backup_date} не найден")
        else:
            backup_file = backups[-1].split()[-1]
        
        # Скачиваем бэкап
        local_file = f"{backup_dir}/{backup_file}"
        s3_cp_cmd = f"aws s3 cp s3://{params['minio_bucket']}/{params['minio_path']}/{backup_file} {local_file} --endpoint-url {params['minio_endpoint']} --profile minio --no-verify-ssl"
        run_command(s3_cp_cmd)
        
        # Валидируем бэкап
        validate_backup(local_file)
        
        # Формируем команду для восстановления
        if params['jdbc_url']:
            restore_cmd = f"psql '{params['jdbc_url']}'"
        else:
            restore_cmd = f"psql -h {params['host']} -p {params['port']} -U {params['user']} -d {params['database']}"
        
        # Выполняем восстановление
        restore_cmd = f"gunzip -c {local_file} | {restore_cmd}"
        run_command(restore_cmd)
        
    finally:
        # Очищаем временные файлы
        if 'local_file' in locals() and os.path.exists(local_file):
            os.remove(local_file)

# Создаем DAG
dag = DAG(
    'postgres_backup_dag_advanced',
    default_args=default_args,
    description='Advanced PostgreSQL backup and restore DAG with parallel execution, incremental backup, and validation',
    schedule_interval='0 0 * * *',
    catchup=False,
    tags=['postgres', 'backup', 'advanced'],
)

# Задачи
check_postgres_task = PythonOperator(
    task_id='check_postgres',
    python_callable=lambda: run_command(f"pg_isready -h {get_connection_params()['host']} -p {get_connection_params()['port']}"),
    dag=dag,
)

setup_config_task = PythonOperator(
    task_id='setup_minio_config',
    python_callable=lambda: run_command("mkdir -p ~/.aws && echo '[minio]\naws_access_key_id = ${MINIO_ACCESS_KEY}\naws_secret_access_key = ${MINIO_SECRET_KEY}' > ~/.aws/credentials"),
    dag=dag,
)

backup_task = PythonOperator(
    task_id='backup_postgres',
    python_callable=create_backup,
    provide_context=True,
    dag=dag,
)

restore_task = PythonOperator(
    task_id='restore_postgres',
    python_callable=restore_backup,
    provide_context=True,
    dag=dag,
    trigger_rule='manual',
)

# Определяем зависимости
check_postgres_task >> setup_config_task >> backup_task >> restore_task 