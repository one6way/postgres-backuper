#!/bin/bash

# Конфигурация
PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-5432}"
PG_DB="${PG_DB:-postgres}"
PG_USER="${PG_USER:-postgres}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-https://minio.vanek-test.com}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-minioadmin}"
MINIO_BUCKET="${MINIO_BUCKET:-postgres-backup}"
BACKUP_DIR="/tmp/postgres_backup"
DATE=$(date +%Y%m%d_%H%M%S)

# Создаем директорию для временных файлов
mkdir -p $BACKUP_DIR

# Проверка подключения к PostgreSQL
check_postgres() {
    echo "Проверка подключения к PostgreSQL..."
    if ! pg_isready -h $PG_HOST -p $PG_PORT -d $PG_DB -U $PG_USER > /dev/null 2>&1; then
        echo "Ошибка: Не удалось подключиться к PostgreSQL по адресу $PG_HOST:$PG_PORT"
        echo "Убедитесь, что PostgreSQL работает и доступен."
        exit 1
    fi
    echo "Соединение с PostgreSQL успешно установлено."
}

# Проверка подключения к MinIO
check_minio() {
    echo "Проверка подключения к MinIO..."
    
    # Создаем конфигурацию AWS CLI для MinIO
    setup_aws_config
    
    # Проверяем доступность MinIO, пытаясь получить список бакетов
    if ! aws s3 ls --endpoint-url $MINIO_ENDPOINT --profile minio --no-verify-ssl > /dev/null 2>&1; then
        echo "Ошибка: Не удалось подключиться к MinIO по адресу $MINIO_ENDPOINT"
        echo "Убедитесь, что MinIO работает и доступен."
        exit 1
    fi
    
    # Проверяем существование бакета
    if ! aws s3 ls s3://$MINIO_BUCKET --endpoint-url $MINIO_ENDPOINT --profile minio --no-verify-ssl > /dev/null 2>&1; then
        echo "Внимание: Бакет $MINIO_BUCKET не существует. Создаем..."
        aws s3 mb s3://$MINIO_BUCKET --endpoint-url $MINIO_ENDPOINT --profile minio --no-verify-ssl
        if [ $? -ne 0 ]; then
            echo "Ошибка: Не удалось создать бакет $MINIO_BUCKET"
            exit 1
        fi
        echo "Бакет $MINIO_BUCKET успешно создан."
    else
        echo "Бакет $MINIO_BUCKET существует."
    fi
    
    echo "Соединение с MinIO успешно установлено."
}

# Создаем конфигурацию AWS CLI для MinIO
setup_aws_config() {
    mkdir -p ~/.aws
    cat > ~/.aws/credentials << EOF
[minio]
aws_access_key_id = $MINIO_ACCESS_KEY
aws_secret_access_key = $MINIO_SECRET_KEY
EOF

    cat > ~/.aws/config << EOF
[profile minio]
s3 =
    path_style_access = true
EOF
}

# Функция для бэкапа
backup() {
    echo "Starting backup of database $PG_DB..."
    
    # Проверяем подключения
    check_postgres
    check_minio
    
    # Создаем бэкап в сжатом виде
    pg_dump -h $PG_HOST -p $PG_PORT -U $PG_USER -d $PG_DB | gzip > "$BACKUP_DIR/backup_$DATE.sql.gz"
    if [ $? -ne 0 ]; then
        echo "Ошибка: Не удалось создать бэкап базы данных."
        exit 1
    fi
    
    # Загружаем бэкап в MinIO S3 с поддержкой path-style access
    aws s3 cp "$BACKUP_DIR/backup_$DATE.sql.gz" \
        "s3://$MINIO_BUCKET/backups/backup_$DATE.sql.gz" \
        --endpoint-url $MINIO_ENDPOINT \
        --profile minio \
        --no-verify-ssl
    if [ $? -ne 0 ]; then
        echo "Ошибка: Не удалось загрузить бэкап в MinIO."
        exit 1
    fi
    
    # Очищаем временные файлы
    rm -f "$BACKUP_DIR/backup_$DATE.sql.gz"
    
    echo "Backup completed and uploaded to MinIO S3"
}

# Функция для восстановления
restore() {
    echo "Starting restore of database $PG_DB..."
    
    # Проверяем подключения
    check_postgres
    check_minio
    
    # Получаем последний бэкап из MinIO S3
    LAST_BACKUP=$(aws s3 ls "s3://$MINIO_BUCKET/backups/" \
        --endpoint-url $MINIO_ENDPOINT \
        --profile minio \
        --no-verify-ssl | sort | tail -n 1 | awk '{print $4}')
    
    if [ -z "$LAST_BACKUP" ]; then
        echo "No backup found in MinIO S3"
        exit 1
    fi
    
    # Скачиваем бэкап
    aws s3 cp "s3://$MINIO_BUCKET/backups/$LAST_BACKUP" \
        "$BACKUP_DIR/$LAST_BACKUP" \
        --endpoint-url $MINIO_ENDPOINT \
        --profile minio \
        --no-verify-ssl
    if [ $? -ne 0 ]; then
        echo "Ошибка: Не удалось скачать бэкап из MinIO."
        exit 1
    fi
    
    # Распаковываем и восстанавливаем
    gunzip -c "$BACKUP_DIR/$LAST_BACKUP" | psql -h $PG_HOST -p $PG_PORT -U $PG_USER -d $PG_DB
    if [ $? -ne 0 ]; then
        echo "Ошибка: Не удалось восстановить базу данных из бэкапа."
        exit 1
    fi
    
    # Очищаем временные файлы
    rm -f "$BACKUP_DIR/$LAST_BACKUP"
    
    echo "Restore completed"
}

# Проверяем аргументы командной строки
case "$1" in
    "backup")
        backup
        ;;
    "restore")
        restore
        ;;
    "check")
        check_postgres
        check_minio
        echo "Все проверки успешно пройдены!"
        ;;
    *)
        echo "Usage: $0 {backup|restore|check}"
        exit 1
        ;;
esac 