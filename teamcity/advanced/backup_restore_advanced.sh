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
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
PARALLEL_JOBS="${PARALLEL_JOBS:-4}"
INCREMENTAL_BACKUP="${INCREMENTAL_BACKUP:-false}"
LAST_FULL_BACKUP="${LAST_FULL_BACKUP:-}"

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
    setup_aws_config
    
    if ! aws s3 ls --endpoint-url $MINIO_ENDPOINT --profile minio --no-verify-ssl > /dev/null 2>&1; then
        echo "Ошибка: Не удалось подключиться к MinIO по адресу $MINIO_ENDPOINT"
        exit 1
    fi
    
    if ! aws s3 ls s3://$MINIO_BUCKET --endpoint-url $MINIO_ENDPOINT --profile minio --no-verify-ssl > /dev/null 2>&1; then
        echo "Создаем бакет $MINIO_BUCKET..."
        aws s3 mb s3://$MINIO_BUCKET --endpoint-url $MINIO_ENDPOINT --profile minio --no-verify-ssl
    fi
}

# Настройка AWS CLI для MinIO
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

# Получение списка схем
get_schemas() {
    psql -h $PG_HOST -p $PG_PORT -U $PG_USER -d $PG_DB -t -c "SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT IN ('pg_catalog', 'information_schema');"
}

# Параллельный бэкап схем
parallel_backup() {
    local schemas=($(get_schemas))
    local total_schemas=${#schemas[@]}
    local jobs_per_schema=$((PARALLEL_JOBS / total_schemas))
    
    for schema in "${schemas[@]}"; do
        echo "Backing up schema: $schema"
        pg_dump -h $PG_HOST -p $PG_PORT -U $PG_USER -d $PG_DB -n $schema | gzip > "$BACKUP_DIR/${schema}_${DATE}.sql.gz" &
        
        # Ограничиваем количество параллельных процессов
        while [ $(jobs -r | wc -l) -ge $jobs_per_schema ]; do
            sleep 1
        done
    done
    
    # Ждем завершения всех процессов
    wait
}

# Инкрементальный бэкап
incremental_backup() {
    if [ -z "$LAST_FULL_BACKUP" ]; then
        echo "Ошибка: Не указана дата последнего полного бэкапа"
        exit 1
    fi
    
    # Получаем список измененных таблиц с момента последнего бэкапа
    local changed_tables=$(psql -h $PG_HOST -p $PG_PORT -U $PG_USER -d $PG_DB -t -c "
        SELECT schemaname || '.' || tablename 
        FROM pg_stat_user_tables 
        WHERE last_analyze > '$LAST_FULL_BACKUP' OR last_autoanalyze > '$LAST_FULL_BACKUP';
    ")
    
    for table in $changed_tables; do
        echo "Backing up changed table: $table"
        pg_dump -h $PG_HOST -p $PG_PORT -U $PG_USER -d $PG_DB -t $table | gzip > "$BACKUP_DIR/incremental_${table}_${DATE}.sql.gz"
    done
}

# Валидация бэкапа
validate_backup() {
    local backup_file=$1
    local temp_file="/tmp/validate_${DATE}.sql"
    
    # Распаковываем бэкап
    gunzip -c "$backup_file" > "$temp_file"
    
    # Проверяем структуру SQL
    if ! grep -q "CREATE TABLE" "$temp_file"; then
        echo "Ошибка: Бэкап не содержит определения таблиц"
        rm "$temp_file"
        return 1
    fi
    
    # Проверяем наличие данных
    if ! grep -q "COPY" "$temp_file"; then
        echo "Ошибка: Бэкап не содержит данных"
        rm "$temp_file"
        return 1
    fi
    
    rm "$temp_file"
    return 0
}

# Ротация бэкапов
rotate_backups() {
    local current_date=$(date +%s)
    local retention_seconds=$((BACKUP_RETENTION_DAYS * 86400))
    
    # Получаем список бэкапов
    local backups=$(aws s3 ls "s3://$MINIO_BUCKET/backups/" --endpoint-url $MINIO_ENDPOINT --profile minio --no-verify-ssl)
    
    while IFS= read -r backup; do
        local backup_date=$(echo "$backup" | awk '{print $1" "$2}')
        local backup_timestamp=$(date -d "$backup_date" +%s)
        local age=$((current_date - backup_timestamp))
        
        if [ $age -gt $retention_seconds ]; then
            local backup_name=$(echo "$backup" | awk '{print $4}')
            echo "Удаляем старый бэкап: $backup_name"
            aws s3 rm "s3://$MINIO_BUCKET/backups/$backup_name" --endpoint-url $MINIO_ENDPOINT --profile minio --no-verify-ssl
        fi
    done <<< "$backups"
}

# Функция для бэкапа
backup() {
    echo "Starting backup of database $PG_DB..."
    
    check_postgres
    check_minio
    
    if [ "$INCREMENTAL_BACKUP" = "true" ]; then
        incremental_backup
    else
        parallel_backup
    fi
    
    # Загружаем бэкапы в MinIO
    for file in "$BACKUP_DIR"/*.sql.gz; do
        if [ -f "$file" ]; then
            # Валидируем бэкап
            if ! validate_backup "$file"; then
                echo "Ошибка: Бэкап $file не прошел валидацию"
                continue
            fi
            
            # Загружаем в MinIO
            aws s3 cp "$file" "s3://$MINIO_BUCKET/backups/$(basename $file)" \
                --endpoint-url $MINIO_ENDPOINT \
                --profile minio \
                --no-verify-ssl
        fi
    done
    
    # Выполняем ротацию
    rotate_backups
    
    # Очищаем временные файлы
    rm -f "$BACKUP_DIR"/*.sql.gz
    
    echo "Backup completed and uploaded to MinIO S3"
}

# Функция для восстановления
restore() {
    echo "Starting restore of database $PG_DB..."
    
    check_postgres
    check_minio
    
    # Получаем последний бэкап
    local last_backup=$(aws s3 ls "s3://$MINIO_BUCKET/backups/" \
        --endpoint-url $MINIO_ENDPOINT \
        --profile minio \
        --no-verify-ssl | sort | tail -n 1 | awk '{print $4}')
    
    if [ -z "$last_backup" ]; then
        echo "No backup found in MinIO S3"
        exit 1
    fi
    
    # Скачиваем бэкап
    aws s3 cp "s3://$MINIO_BUCKET/backups/$last_backup" \
        "$BACKUP_DIR/$last_backup" \
        --endpoint-url $MINIO_ENDPOINT \
        --profile minio \
        --no-verify-ssl
    
    # Валидируем бэкап перед восстановлением
    if ! validate_backup "$BACKUP_DIR/$last_backup"; then
        echo "Ошибка: Бэкап не прошел валидацию"
        exit 1
    fi
    
    # Восстанавливаем
    gunzip -c "$BACKUP_DIR/$last_backup" | psql -h $PG_HOST -p $PG_PORT -U $PG_USER -d $PG_DB
    
    # Очищаем временные файлы
    rm -f "$BACKUP_DIR/$last_backup"
    
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