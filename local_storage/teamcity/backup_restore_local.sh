#!/bin/bash

# Конфигурация
BACKUP_DIR="/var/lib/postgresql/backups"  # Директория для хранения бэкапов
RETENTION_DAYS=30                          # Количество дней хранения бэкапов
DATE=$(date +%Y%m%d_%H%M%S)               # Текущая дата и время
BACKUP_FILE="${BACKUP_DIR}/backup_${DATE}.sql.gz"  # Имя файла бэкапа

# Функция для проверки и создания директории
ensure_backup_dir() {
    if [ ! -d "$BACKUP_DIR" ]; then
        echo "Создание директории для бэкапов: $BACKUP_DIR"
        sudo mkdir -p "$BACKUP_DIR"
        sudo chown postgres:postgres "$BACKUP_DIR"
        sudo chmod 700 "$BACKUP_DIR"
    fi
}

# Функция для создания бэкапа
create_backup() {
    echo "Создание бэкапа PostgreSQL..."
    pg_dump -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" | gzip > "$BACKUP_FILE"
    
    if [ $? -eq 0 ]; then
        echo "Бэкап успешно создан: $BACKUP_FILE"
        # Устанавливаем права на файл
        sudo chown postgres:postgres "$BACKUP_FILE"
        sudo chmod 600 "$BACKUP_FILE"
    else
        echo "Ошибка при создании бэкапа"
        exit 1
    fi
}

# Функция для ротации старых бэкапов
rotate_backups() {
    echo "Ротация старых бэкапов..."
    find "$BACKUP_DIR" -name "backup_*.sql.gz" -mtime +$RETENTION_DAYS -delete
}

# Функция для восстановления из бэкапа
restore_backup() {
    local backup_file="$1"
    if [ -z "$backup_file" ]; then
        # Если файл не указан, используем последний бэкап
        backup_file=$(ls -t "$BACKUP_DIR"/backup_*.sql.gz | head -n 1)
    fi

    if [ ! -f "$backup_file" ]; then
        echo "Файл бэкапа не найден: $backup_file"
        exit 1
    fi

    echo "Восстановление из бэкапа: $backup_file"
    gunzip -c "$backup_file" | psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB"
    
    if [ $? -eq 0 ]; then
        echo "Восстановление успешно завершено"
    else
        echo "Ошибка при восстановлении"
        exit 1
    fi
}

# Функция для проверки свободного места
check_disk_space() {
    local required_space=1024  # Минимальный требуемый объем в МБ
    local available_space=$(df -m "$BACKUP_DIR" | awk 'NR==2 {print $4}')
    
    if [ "$available_space" -lt "$required_space" ]; then
        echo "Ошибка: Недостаточно свободного места в $BACKUP_DIR"
        echo "Доступно: ${available_space}MB, Требуется: ${required_space}MB"
        exit 1
    fi
}

# Основная логика
case "$1" in
    "backup")
        ensure_backup_dir
        check_disk_space
        create_backup
        rotate_backups
        ;;
    "restore")
        ensure_backup_dir
        restore_backup "$2"
        ;;
    "list")
        ls -lh "$BACKUP_DIR"/backup_*.sql.gz
        ;;
    "check")
        ensure_backup_dir
        check_disk_space
        echo "Проверка завершена успешно"
        ;;
    *)
        echo "Использование: $0 {backup|restore [file]|list|check}"
        exit 1
        ;;
esac 