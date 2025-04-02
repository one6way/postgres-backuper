#!/bin/bash

# Скрипт для установки всех необходимых зависимостей
echo "Установка зависимостей для PostgreSQL backup/restore решения..."

# Проверка наличия pip
if ! command -v pip &> /dev/null; then
    echo "pip не найден. Устанавливаем pip..."
    sudo apt-get update
    sudo apt-get install -y python3-pip
fi

# Проверка наличия PostgreSQL клиента
if ! command -v pg_dump &> /dev/null; then
    echo "PostgreSQL клиент не найден. Устанавливаем..."
    sudo apt-get update
    sudo apt-get install -y postgresql-client
fi

# Проверка наличия AWS CLI
if ! command -v aws &> /dev/null; then
    echo "AWS CLI не найден. Устанавливаем..."
    pip install awscli
fi

# Установка Python зависимостей
echo "Установка Python зависимостей..."
pip install -r requirements.txt

# Делаем скрипты исполняемыми
chmod +x teamcity/backup_restore.sh

echo "Проверка конфигурации..."
# Проверка настроек и подключений
./teamcity/backup_restore.sh check

echo "Установка завершена."
echo "Для использования с TeamCity разместите файлы из директории teamcity/ в вашем проекте TeamCity."
echo "Для использования с Airflow разместите файл airflow/postgres_backup_dag.py в директории DAGs вашего Airflow." 