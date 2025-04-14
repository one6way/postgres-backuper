#!/usr/bin/env python3
import os
import sys
import logging
import argparse
import subprocess
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
import boto3
from botocore.exceptions import ClientError
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class PostgresBackupRestore:
    def __init__(self, args):
        self.args = args
        self.temp_dir = tempfile.mkdtemp()
        self.backup_path = os.path.join(self.temp_dir, f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        # Инициализация MinIO клиента
        self.s3_client = boto3.client(
            's3',
            endpoint_url=args.minio_endpoint,
            aws_access_key_id=args.minio_access_key,
            aws_secret_access_key=args.minio_secret_key,
            region_name='us-east-1'  # Минимальное значение для MinIO
        )
        
        # Проверка подключения к MinIO
        try:
            self.s3_client.head_bucket(Bucket=args.minio_bucket)
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.info(f"Bucket {args.minio_bucket} не существует, создаю...")
                self.s3_client.create_bucket(Bucket=args.minio_bucket)
            else:
                raise

    def __del__(self):
        # Очистка временных файлов
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def backup(self):
        """Создание бэкапа базы данных"""
        try:
            # Создание директории для бэкапа
            os.makedirs(self.backup_path, exist_ok=True)
            
            # Формирование команды pg_dump
            cmd = [
                'pg_dump',
                '-h', self.args.host,
                '-p', str(self.args.port),
                '-U', self.args.user,
                '-d', self.args.database,
                '-F', 'd',  # Directory format
                '-f', self.backup_path,
                '-v'  # Verbose output
            ]
            
            # Добавление дополнительных опций
            if self.args.schemas:
                cmd.extend(['-n', self.args.schemas])
            if self.args.exclude_schemas:
                cmd.extend(['-N', self.args.exclude_schemas])
            if self.args.tables:
                cmd.extend(['-t', self.args.tables])
            if self.args.exclude_tables:
                cmd.extend(['-T', self.args.exclude_tables])
            
            # Установка переменной окружения для пароля
            env = os.environ.copy()
            env['PGPASSWORD'] = self.args.password
            
            # Выполнение команды
            logger.info(f"Выполняю бэкап: {' '.join(cmd)}")
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"Ошибка при создании бэкапа: {result.stderr}")
            
            # Загрузка в MinIO
            self._upload_to_minio()
            
            logger.info("Бэкап успешно создан и загружен в MinIO")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при создании бэкапа: {str(e)}")
            return False

    def restore(self):
        """Восстановление базы данных из бэкапа"""
        try:
            # Скачивание бэкапа из MinIO
            self._download_from_minio()
            
            # Проверка существования базы данных
            conn = psycopg2.connect(
                host=self.args.host,
                port=self.args.port,
                user=self.args.user,
                password=self.args.password,
                database='postgres'  # Подключаемся к системной БД
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cur = conn.cursor()
            
            # Проверяем существование базы данных
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (self.args.database,))
            if cur.fetchone():
                if self.args.force:
                    logger.info(f"База данных {self.args.database} существует, удаляю...")
                    cur.execute(f"DROP DATABASE {self.args.database}")
                else:
                    raise Exception(f"База данных {self.args.database} уже существует. Используйте --force для перезаписи.")
            
            # Создаем новую базу данных
            logger.info(f"Создаю базу данных {self.args.database}")
            cur.execute(f"CREATE DATABASE {self.args.database}")
            cur.close()
            conn.close()
            
            # Формирование команды восстановления
            cmd = [
                'pg_restore',
                '-h', self.args.host,
                '-p', str(self.args.port),
                '-U', self.args.user,
                '-d', self.args.database,
                '-v',  # Verbose output
                self.backup_path
            ]
            
            # Установка переменной окружения для пароля
            env = os.environ.copy()
            env['PGPASSWORD'] = self.args.password
            
            # Выполнение команды
            logger.info(f"Выполняю восстановление: {' '.join(cmd)}")
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"Ошибка при восстановлении: {result.stderr}")
            
            logger.info("Восстановление успешно завершено")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при восстановлении: {str(e)}")
            return False

    def _upload_to_minio(self):
        """Загрузка бэкапа в MinIO"""
        try:
            # Создаем архив бэкапа
            backup_archive = f"{self.backup_path}.tar.gz"
            shutil.make_archive(self.backup_path, 'gztar', self.backup_path)
            
            # Загружаем в MinIO
            s3_key = f"postgres_backup/{os.path.basename(backup_archive)}"
            logger.info(f"Загружаю бэкап в MinIO: {s3_key}")
            
            with open(backup_archive, 'rb') as f:
                self.s3_client.upload_fileobj(
                    f,
                    self.args.minio_bucket,
                    s3_key
                )
            
            logger.info(f"Бэкап успешно загружен в MinIO: {s3_key}")
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке в MinIO: {str(e)}")
            raise

    def _download_from_minio(self):
        """Скачивание бэкапа из MinIO"""
        try:
            # Получаем список объектов в bucket
            response = self.s3_client.list_objects_v2(
                Bucket=self.args.minio_bucket,
                Prefix="postgres_backup/"
            )
            
            if 'Contents' not in response:
                raise Exception("В MinIO нет доступных бэкапов")
            
            # Сортируем по дате создания (новейший первый)
            objects = sorted(response['Contents'], key=lambda x: x['LastModified'], reverse=True)
            
            # Если указан конкретный бэкап, ищем его
            if self.args.backup_name:
                backup_found = False
                for obj in objects:
                    if self.args.backup_name in obj['Key']:
                        backup_key = obj['Key']
                        backup_found = True
                        break
                if not backup_found:
                    raise Exception(f"Бэкап {self.args.backup_name} не найден в MinIO")
            else:
                # Берем последний бэкап
                backup_key = objects[0]['Key']
            
            # Скачиваем бэкап
            backup_archive = os.path.join(self.temp_dir, os.path.basename(backup_key))
            logger.info(f"Скачиваю бэкап из MinIO: {backup_key}")
            
            self.s3_client.download_file(
                self.args.minio_bucket,
                backup_key,
                backup_archive
            )
            
            # Распаковываем архив
            shutil.unpack_archive(backup_archive, self.temp_dir)
            self.backup_path = os.path.splitext(backup_archive)[0]
            
            logger.info(f"Бэкап успешно скачан и распакован: {self.backup_path}")
            
        except Exception as e:
            logger.error(f"Ошибка при скачивании из MinIO: {str(e)}")
            raise

def main():
    parser = argparse.ArgumentParser(description='PostgreSQL Backup and Restore Tool')
    
    # Общие параметры
    parser.add_argument('--host', required=True, help='PostgreSQL host')
    parser.add_argument('--port', type=int, default=5432, help='PostgreSQL port')
    parser.add_argument('--user', required=True, help='PostgreSQL user')
    parser.add_argument('--password', required=True, help='PostgreSQL password')
    parser.add_argument('--database', required=True, help='PostgreSQL database name')
    
    # Параметры MinIO
    parser.add_argument('--minio-endpoint', required=True, help='MinIO endpoint URL')
    parser.add_argument('--minio-access-key', required=True, help='MinIO access key')
    parser.add_argument('--minio-secret-key', required=True, help='MinIO secret key')
    parser.add_argument('--minio-bucket', default='postgres-backups', help='MinIO bucket name')
    
    # Параметры бэкапа
    parser.add_argument('--schemas', help='Схемы для бэкапа (через запятую)')
    parser.add_argument('--exclude-schemas', help='Схемы для исключения (через запятую)')
    parser.add_argument('--tables', help='Таблицы для бэкапа (через запятую)')
    parser.add_argument('--exclude-tables', help='Таблицы для исключения (через запятую)')
    
    # Параметры восстановления
    parser.add_argument('--backup-name', help='Имя бэкапа для восстановления')
    parser.add_argument('--force', action='store_true', help='Принудительное восстановление (с удалением существующей БД)')
    
    # Режим работы
    parser.add_argument('--mode', choices=['backup', 'restore'], required=True, help='Режим работы: backup или restore')
    
    args = parser.parse_args()
    
    try:
        backup_restore = PostgresBackupRestore(args)
        
        if args.mode == 'backup':
            success = backup_restore.backup()
        else:
            success = backup_restore.restore()
        
        sys.exit(0 if success else 1)
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main() 