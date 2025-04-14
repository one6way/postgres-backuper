from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash_operator import BashOperator
from airflow.operators.python_operator import PythonOperator
from airflow.utils.dates import days_ago
import os

# Default arguments for the DAG
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': True,
    'email_on_retry': True,
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'start_date': days_ago(1),
}

# Define the DAG
dag = DAG(
    'postgres_backup_restore',
    default_args=default_args,
    description='PostgreSQL backup and restore operations',
    schedule_interval='0 0 * * *',  # Run daily at midnight
    catchup=False,
    tags=['postgres', 'backup', 'restore'],
)

# Environment variables for sensitive data
env_vars = {
    'PGPASSWORD': '{{ var.value.postgres_password }}',
    'MINIO_ACCESS_KEY': '{{ var.value.minio_access_key }}',
    'MINIO_SECRET_KEY': '{{ var.value.minio_secret_key }}',
}

# Backup task
backup_task = BashOperator(
    task_id='backup_postgres',
    bash_command="""
    python {{ params.script_path }}/postgres_backup_restore.py \
        --mode backup \
        --host {{ params.postgres_host }} \
        --port {{ params.postgres_port }} \
        --user {{ params.postgres_user }} \
        --password $PGPASSWORD \
        --database {{ params.postgres_database }} \
        --minio-endpoint {{ params.minio_endpoint }} \
        --minio-access-key $MINIO_ACCESS_KEY \
        --minio-secret-key $MINIO_SECRET_KEY \
        --minio-bucket {{ params.minio_bucket }} \
        --backup-name backup_{{ ts_nodash }} \
        --schemas {{ params.schemas }} \
        --exclude-schemas {{ params.exclude_schemas }}
    """,
    env=env_vars,
    params={
        'script_path': '/opt/airflow/dags/scripts',
        'postgres_host': '{{ var.value.postgres_host }}',
        'postgres_port': '{{ var.value.postgres_port }}',
        'postgres_user': '{{ var.value.postgres_user }}',
        'postgres_database': '{{ var.value.postgres_database }}',
        'minio_endpoint': '{{ var.value.minio_endpoint }}',
        'minio_bucket': '{{ var.value.minio_bucket }}',
        'schemas': 'public',
        'exclude_schemas': 'information_schema,pg_catalog',
    },
    dag=dag,
)

# Restore task (optional, can be triggered manually)
restore_task = BashOperator(
    task_id='restore_postgres',
    bash_command="""
    python {{ params.script_path }}/postgres_backup_restore.py \
        --mode restore \
        --host {{ params.postgres_host }} \
        --port {{ params.postgres_port }} \
        --user {{ params.postgres_user }} \
        --password $PGPASSWORD \
        --database {{ params.postgres_database }} \
        --minio-endpoint {{ params.minio_endpoint }} \
        --minio-access-key $MINIO_ACCESS_KEY \
        --minio-secret-key $MINIO_SECRET_KEY \
        --minio-bucket {{ params.minio_bucket }} \
        --backup-name {{ params.backup_name }} \
        --force
    """,
    env=env_vars,
    params={
        'script_path': '/opt/airflow/dags/scripts',
        'postgres_host': '{{ var.value.postgres_host }}',
        'postgres_port': '{{ var.value.postgres_port }}',
        'postgres_user': '{{ var.value.postgres_user }}',
        'postgres_database': '{{ var.value.postgres_database }}',
        'minio_endpoint': '{{ var.value.minio_endpoint }}',
        'minio_bucket': '{{ var.value.minio_bucket }}',
        'backup_name': 'backup_{{ ts_nodash }}',
    },
    dag=dag,
)

# Set task dependencies
backup_task >> restore_task 