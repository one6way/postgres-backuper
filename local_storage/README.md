# Локальное решение для бэкапа PostgreSQL

Это решение для автоматического бэкапа и восстановления баз данных PostgreSQL с хранением бэкапов на локальном сервере.

## Особенности

- Хранение бэкапов в локальной директории
- Автоматическая ротация старых бэкапов
- Проверка свободного места на диске
- Безопасное хранение (правильные права доступа)
- Поддержка TeamCity и Airflow

## Требования

- PostgreSQL клиент (pg_dump, pg_restore)
- Доступ к директории `/var/lib/postgresql/backups`
- Права на выполнение команд от имени postgres
- TeamCity или Apache Airflow (в зависимости от выбранного решения)

## Настройка

### 1. Создание директории для бэкапов

```bash
sudo mkdir -p /var/lib/postgresql/backups
sudo chown postgres:postgres /var/lib/postgresql/backups
sudo chmod 700 /var/lib/postgresql/backups
```

### 2. Настройка TeamCity

1. Скопируйте `backup_restore_local.sh` в ваш проект TeamCity
2. Настройте переменные окружения:
```bash
PG_HOST=your_postgres_host
PG_PORT=5432
PG_DB=your_database_name
PG_USER=your_postgres_user
```
3. Создайте build configuration с использованием скрипта

### 3. Настройка Airflow

1. Скопируйте `postgres_backup_dag_local.py` в директорию DAGs вашего Airflow
2. Настройте переменные в интерфейсе Airflow:
```python
pg_host = 'your_postgres_host'
pg_port = '5432'
pg_db = 'your_database_name'
pg_user = 'your_postgres_user'
```

## Использование

### TeamCity

```bash
# Создание бэкапа
./backup_restore_local.sh backup

# Восстановление из последнего бэкапа
./backup_restore_local.sh restore

# Восстановление из конкретного бэкапа
./backup_restore_local.sh restore /var/lib/postgresql/backups/backup_20240315_120000.sql.gz

# Просмотр списка бэкапов
./backup_restore_local.sh list

# Проверка настроек
./backup_restore_local.sh check
```

### Airflow

- DAG будет выполняться автоматически каждый день
- Проверяет наличие свободного места перед созданием бэкапа
- Автоматически удаляет старые бэкапы
- Отправляет уведомления при ошибках

## Безопасность

- Бэкапы хранятся с правами 600 (только владелец)
- Директория с бэкапами имеет права 700
- Владелец файлов и директории - пользователь postgres
- Регулярная ротация старых бэкапов

## Мониторинг

### Проверка места на диске
```bash
df -h /var/lib/postgresql/backups
```

### Просмотр размера бэкапов
```bash
du -sh /var/lib/postgresql/backups/*
```

### Проверка прав доступа
```bash
ls -la /var/lib/postgresql/backups
``` 