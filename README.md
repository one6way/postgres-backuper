# PostgreSQL Backup and Restore Solution

Это решение для автоматического бэкапа и восстановления баз данных PostgreSQL с использованием TeamCity и Apache Airflow.

## Структура проекта

```
postgres-backup/
├── teamcity/
│   ├── backup_restore.sh    # Скрипт для бэкапа и восстановления
│   └── teamcity-config.xml  # Конфигурация TeamCity
├── airflow/
│   └── postgres_backup_dag.py  # DAG для Airflow
├── install.sh              # Скрипт установки зависимостей
└── requirements.txt        # Зависимости Python
```

## Требования

- PostgreSQL клиент
- AWS CLI (для работы с MinIO S3)
- TeamCity или Apache Airflow (в зависимости от выбранного решения)
- MinIO сервер

## Быстрый старт

1. Скачайте и распакуйте проект
2. Запустите скрипт установки:
```bash
cd postgres-backup
chmod +x install.sh
./install.sh
```

## Настройка переменных окружения

Необходимо настроить следующие переменные окружения:

```bash
# Стандартные параметры подключения к PostgreSQL
PG_HOST=your_postgres_host
PG_PORT=5432
PG_DB=your_database_name
PG_USER=your_postgres_user

# Альтернативный способ подключения через JDBC URL
PG_JDBC_URL=jdbc:postgresql://host:port/database?user=username&password=password

# Параметры MinIO
MINIO_ENDPOINT=https://minio.vanek-test.com
MINIO_ACCESS_KEY=your_access_key
MINIO_SECRET_KEY=your_secret_key
MINIO_BUCKET=your_bucket_name
```

## Кастомные бэкапы в Airflow

### Настройка параметров подключения

В Airflow вы можете настроить параметры подключения двумя способами:

1. Через стандартные параметры:
```python
# В интерфейсе Airflow -> Admin -> Variables добавьте:
PG_HOST = 'your_host'
PG_PORT = '5432'
PG_DB = 'your_database'
PG_USER = 'your_user'
```

2. Через JDBC URL (для сложных конфигураций):
```python
# В интерфейсе Airflow -> Admin -> Variables добавьте:
PG_JDBC_URL = 'jdbc:postgresql://host:port/database?user=username&password=password&ssl=true'
```

### Создание бэкапа конкретной базы

1. Через стандартные параметры:
```python
# В интерфейсе Airflow -> Admin -> Variables измените:
PG_DB = 'your_specific_database'
```

2. Через JDBC URL:
```python
# В интерфейсе Airflow -> Admin -> Variables добавьте:
PG_JDBC_URL = 'jdbc:postgresql://host:port/your_specific_database?user=username&password=password'
```

### Восстановление конкретного бэкапа

Вы можете восстановить конкретный бэкап по дате:

1. В интерфейсе Airflow найдите DAG `postgres_backup_dag`
2. Выберите задачу `restore_postgres`
3. Нажмите "Clear" и в появившемся окне добавьте параметр:
```json
{
    "backup_date": "20240315"  # Формат: YYYYMMDD
}
```

### Примеры использования

1. Бэкап конкретной базы на другом сервере:
```python
# В Airflow Variables:
PG_HOST = 'another-server.com'
PG_DB = 'specific_database'
PG_USER = 'backup_user'
```

2. Бэкап с SSL и дополнительными параметрами:
```python
# В Airflow Variables:
PG_JDBC_URL = 'jdbc:postgresql://host:port/database?ssl=true&sslmode=verify-full&sslcert=/path/to/cert'
```

3. Восстановление на другую базу:
```python
# В Airflow Variables перед восстановлением:
PG_DB = 'target_database'  # или
PG_JDBC_URL = 'jdbc:postgresql://host:port/target_database?user=username&password=password'
```

## TeamCity Solution

### Настройка

1. Скопируйте файлы из директории `teamcity/` в ваш проект TeamCity
2. Настройте параметры в `teamcity-config.xml`
3. Создайте два build configuration:
   - `postgres_backup_daily` - для ежедневного бэкапа
   - `postgres_restore` - для ручного восстановления

### Использование

- Бэкап будет выполняться автоматически каждый день в полночь
- Восстановление доступно только через ручной запуск build configuration `postgres_restore`

## Airflow Solution

### Настройка

1. Скопируйте файл `postgres_backup_dag.py` в директорию DAGs вашего Airflow
2. Настройте переменные в интерфейсе Airflow (Admin -> Variables)
3. Перезапустите Airflow для загрузки нового DAG

### Использование

- DAG будет выполняться автоматически каждый день в полночь
- Задача восстановления (`restore_postgres`) доступна только для ручного запуска через веб-интерфейс Airflow
- Для восстановления конкретного бэкапа используйте параметр `backup_date`

## Проверка работы и устранение проблем

Если у вас возникают проблемы, проверьте следующее:

1. Убедитесь, что PostgreSQL сервер доступен:
```bash
pg_isready -h $PG_HOST -p $PG_PORT -d $PG_DB -U $PG_USER
# или для JDBC URL
pg_isready -d "$PG_JDBC_URL"
```

2. Проверьте подключение к MinIO:
```bash
aws s3 ls --endpoint-url $MINIO_ENDPOINT --profile minio --no-verify-ssl
```

3. Проверьте наличие и права доступа к бакету:
```bash
aws s3 ls s3://$MINIO_BUCKET --endpoint-url $MINIO_ENDPOINT --profile minio --no-verify-ssl
```

4. Проверьте логи для получения дополнительной информации о проблемах:
   - В TeamCity - в логах сборки
   - В Airflow - в логах задач DAG

## Особенности

- Бэкапы сохраняются в сжатом виде (gzip)
- Хранение бэкапов в MinIO S3 с поддержкой path-style access
- Автоматическая очистка временных файлов
- Восстановление из последнего доступного бэкапа или конкретной даты
- Поддержка ручного восстановления
- Безопасная аутентификация через access key и secret key
- Поддержка JDBC URL для сложных конфигураций подключения
- Поддержка SSL и дополнительных параметров подключения
- Возможность восстановления на другую базу данных 