#!/bin/bash

# Проверка наличия необходимых параметров
if [ $# -lt 4 ]; then
    echo "Usage: $0 <endpoint_url> <access_key> <secret_key> <bucket_name> [prefix]"
    exit 1
fi

# Параметры подключения
ENDPOINT_URL=$1
ACCESS_KEY=$2
SECRET_KEY=$3
BUCKET_NAME=$4
PREFIX=${5:-""}  # Необязательный параметр - префикс для фильтрации файлов

# Установка переменных окружения для AWS CLI
export AWS_ACCESS_KEY_ID=$ACCESS_KEY
export AWS_SECRET_ACCESS_KEY=$SECRET_KEY

# Дата, до которой нужно удалить файлы (2 дня назад)
DELETE_BEFORE=$(date -d "2 days ago" +%Y-%m-%d)

echo "Starting cleanup in bucket $BUCKET_NAME with prefix '$PREFIX'"
echo "Will delete files older than $DELETE_BEFORE"

# Получаем список объектов и фильтруем по дате
aws --endpoint-url $ENDPOINT_URL s3 ls "s3://$BUCKET_NAME/$PREFIX" | while read -r line; do
    # Извлекаем дату и имя файла
    createDate=$(echo $line | awk {'print $1" "$2'})
    createDate=$(date -d "$createDate" +%Y-%m-%d)
    fileName=$(echo $line | awk {'print $4'})
    
    # Если файл старше 2 дней, удаляем его
    if [[ $createDate < $DELETE_BEFORE ]]; then
        echo "Deleting $fileName (created on $createDate)"
        aws --endpoint-url $ENDPOINT_URL s3 rm "s3://$BUCKET_NAME/$fileName"
    fi
done

echo "Cleanup completed" 