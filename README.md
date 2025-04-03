# Решение для бэкапа PostgreSQL с поддержкой MinIO

Это решение позволяет автоматизировать процесс создания и восстановления бэкапов PostgreSQL с использованием MinIO в качестве хранилища.

## Особенности

- Автоматическое создание бэкапов по расписанию
- Поддержка ручного запуска бэкапа или восстановления
- Гибкая настройка через коннекторы Airflow
- Поддержка JDBC URL для сложных конфигураций подключения
- Возможность восстановления конкретного бэкапа по дате
- Сжатие бэкапов для экономии места
- Безопасное хранение учетных данных через коннекторы Airflow

## Настройка коннекторов в Airflow

### PostgreSQL коннектор

1. В интерфейсе Airflow перейдите в Admin -> Connections
2. Добавьте новый коннектор с ID `postgres_backup_db`:
   - Connection Type: `Postgres`
   - Host: адрес вашего PostgreSQL сервера
   - Schema: имя базы данных
   - Login: пользователь PostgreSQL
   - Password: пароль пользователя
   - Port: порт PostgreSQL (по умолчанию 5432)
   - Extra: для использования JDBC URL добавьте:
     ```json
     {
         "jdbc_url": "jdbc:postgresql://host:port/database?параметры"
     }
     ```

### MinIO коннектор

1. В интерфейсе Airflow перейдите в Admin -> Connections
2. Добавьте новый коннектор с ID `minio_backup`:
   - Connection Type: `Generic`
   - Host: URL вашего MinIO сервера (например, https://minio.vanek-test.com)
   - Login: Access Key
   - Password: Secret Key
   - Port: порт MinIO (если отличается от стандартного)
   - Extra: дополнительные параметры:
     ```json
     {
         "bucket": "postgres-backup"
     }
     ```

### Пример настройки через CLI

```bash
# PostgreSQL коннектор
airflow connections add 'postgres_backup_db' \
    --conn-type 'postgres' \
    --conn-host 'localhost' \
    --conn-schema 'postgres' \
    --conn-login 'postgres' \
    --conn-password 'your_password' \
    --conn-port 5432

# MinIO коннектор
airflow connections add 'minio_backup' \
    --conn-type 'generic' \
    --conn-host 'https://minio.vanek-test.com' \
    --conn-login 'minioadmin' \
    --conn-password 'minioadmin' \
    --conn-extra '{"bucket": "postgres-backup"}'
```

## Управление операциями в Airflow

### Режимы работы

DAG поддерживает три режима работы:

1. **Только бэкап** (по умолчанию):
```json
{
    "operation": "backup"
}
```

2. **Только восстановление**:
```json
{
    "operation": "restore",
    "backup_date": "20240315"  # Опционально, формат: YYYYMMDD
}
```

3. **Бэкап с последующим восстановлением**:
```json
{
    "operation": "backup_and_restore"
}
```

### Запуск операций

1. **Автоматический бэкап**:
   - Выполняется каждый день в полночь
   - Не требует дополнительных параметров

2. **Ручной запуск**:
   - В интерфейсе Airflow найдите DAG `postgres_backup_dag`
   - Нажмите "Trigger DAG w/ config"
   - Введите JSON с нужными параметрами

### Примеры использования

1. **Создание бэкапа вручную**:
```json
{
    "operation": "backup"
}
```

2. **Восстановление из конкретного бэкапа**:
```json
{
    "operation": "restore",
    "backup_date": "20240315"
}
```

3. **Бэкап с немедленным восстановлением**:
```json
{
    "operation": "backup_and_restore"
}
```

4. **Восстановление последнего бэкапа**:
```json
{
    "operation": "restore"
}
```

## Требования

- Airflow 2.x
- PostgreSQL клиент (pg_dump, pg_restore)
- AWS CLI
- Доступ к MinIO
- Доступ к PostgreSQL

## Безопасность

- Учетные данные хранятся в коннекторах Airflow
- Поддержка SSL для PostgreSQL через JDBC URL
- Поддержка SSL для MinIO
- Временные файлы автоматически удаляются
- Логирование всех операций
