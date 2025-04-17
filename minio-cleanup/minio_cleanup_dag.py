from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.hooks.base import BaseHook
import boto3
import logging
from typing import List, Dict

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

def clean_old_files(**context):
    # Получаем коннектор MinIO
    minio_conn = BaseHook.get_connection('minio_conn')
    
    # Получаем параметры из контекста
    bucket_name = context['params'].get('bucket_name', 'your-bucket')
    folders_config = context['params'].get('folders', [])
    
    # Создаем клиент S3 с учетными данными из коннектора
    s3_client = boto3.client(
        's3',
        endpoint_url=minio_conn.host,
        aws_access_key_id=minio_conn.login,
        aws_secret_access_key=minio_conn.password,
        config=boto3.session.Config(signature_version='s3v4')
    )
    
    # Общая статистика
    total_stats = {
        'total_files': 0,
        'deleted_files': 0,
        'total_size': 0,
        'deleted_size': 0,
        'start_time': datetime.now(),
        'largest_file': {
            'key': None,
            'size': 0,
            'last_modified': None
        }
    }
    
    logger.info(f"Starting cleanup in bucket '{bucket_name}'")
    
    # Обрабатываем каждую папку
    for folder_config in folders_config:
        prefix = folder_config.get('prefix', '')
        days_old = folder_config.get('days_old', 2)
        delete_before = datetime.now() - timedelta(days=days_old)
        
        # Статистика для текущей папки
        folder_stats = {
            'total_files': 0,
            'deleted_files': 0,
            'total_size': 0,
            'deleted_size': 0,
            'largest_file': {
                'key': None,
                'size': 0,
                'last_modified': None
            }
        }
        
        logger.info(f"\nProcessing folder '{prefix}' (files older than {days_old} days)")
        
        # Получаем список объектов
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
        
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    folder_stats['total_files'] += 1
                    folder_stats['total_size'] += obj['Size']
                    
                    last_modified = obj['LastModified'].replace(tzinfo=None)
                    
                    # Если файл старше указанного количества дней, удаляем его
                    if last_modified < delete_before:
                        try:
                            s3_client.delete_object(Bucket=bucket_name, Key=obj['Key'])
                            folder_stats['deleted_files'] += 1
                            folder_stats['deleted_size'] += obj['Size']
                            
                            # Обновляем информацию о самом большом файле в папке
                            if obj['Size'] > folder_stats['largest_file']['size']:
                                folder_stats['largest_file'] = {
                                    'key': obj['Key'],
                                    'size': obj['Size'],
                                    'last_modified': last_modified
                                }
                            
                            # Обновляем информацию о самом большом файле в общей статистике
                            if obj['Size'] > total_stats['largest_file']['size']:
                                total_stats['largest_file'] = {
                                    'key': obj['Key'],
                                    'size': obj['Size'],
                                    'last_modified': last_modified
                                }
                            
                            logger.info(f"Deleted: {obj['Key']} (Size: {obj['Size'] / 1024 / 1024:.2f} MB, Last modified: {last_modified})")
                        except Exception as e:
                            logger.error(f"Error deleting {obj['Key']}: {str(e)}")
        
        # Обновляем общую статистику
        total_stats['total_files'] += folder_stats['total_files']
        total_stats['deleted_files'] += folder_stats['deleted_files']
        total_stats['total_size'] += folder_stats['total_size']
        total_stats['deleted_size'] += folder_stats['deleted_size']
        
        # Выводим статистику для текущей папки
        logger.info(f"\n=== Statistics for folder '{prefix}' ===")
        logger.info(f"Total files processed: {folder_stats['total_files']}")
        logger.info(f"Files deleted: {folder_stats['deleted_files']}")
        logger.info(f"Total size processed: {folder_stats['total_size'] / 1024 / 1024:.2f} MB")
        logger.info(f"Size deleted: {folder_stats['deleted_size'] / 1024 / 1024:.2f} MB")
        if folder_stats['largest_file']['key']:
            logger.info(f"Largest deleted file: {folder_stats['largest_file']['key']}")
            logger.info(f"Size: {folder_stats['largest_file']['size'] / 1024 / 1024:.2f} MB")
            logger.info(f"Last modified: {folder_stats['largest_file']['last_modified']}")
        logger.info("=========================")
    
    # Выводим итоговую статистику
    execution_time = (datetime.now() - total_stats['start_time']).total_seconds()
    logger.info("\n=== Overall Cleanup Statistics ===")
    logger.info(f"Total files processed: {total_stats['total_files']}")
    logger.info(f"Files deleted: {total_stats['deleted_files']}")
    logger.info(f"Total size processed: {total_stats['total_size'] / 1024 / 1024:.2f} MB")
    logger.info(f"Size deleted: {total_stats['deleted_size'] / 1024 / 1024:.2f} MB")
    if total_stats['largest_file']['key']:
        logger.info(f"Largest deleted file: {total_stats['largest_file']['key']}")
        logger.info(f"Size: {total_stats['largest_file']['size'] / 1024 / 1024:.2f} MB")
        logger.info(f"Last modified: {total_stats['largest_file']['last_modified']}")
    logger.info(f"Execution time: {execution_time:.2f} seconds")
    logger.info("=========================")

with DAG(
    'minio_cleanup',
    default_args=default_args,
    description='Clean old files from MinIO bucket',
    schedule_interval='0 0 * * *',  # Запускать каждый день в полночь
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['minio', 'cleanup'],
) as dag:

    clean_files = PythonOperator(
        task_id='clean_old_files',
        python_callable=clean_old_files,
        provide_context=True,
        params={
            'bucket_name': 'your-bucket',  # Имя бакета
            'folders': [  # Список папок с их настройками
                {
                    'prefix': 'logs/',  # Префикс папки
                    'days_old': 7,      # Удалять файлы старше 7 дней
                },
                {
                    'prefix': 'temp/',   # Другая папка
                    'days_old': 2,       # Удалять файлы старше 2 дней
                },
                # Можно добавить больше папок
            ],
        },
    ) 