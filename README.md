# PostgreSQL Backup and Restore Solution

Этот проект содержит решения для автоматического бэкапа и восстановления баз данных PostgreSQL с использованием TeamCity и Apache Airflow.

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
PG_HOST=your_postgres_host
PG_PORT=5432
PG_DB=your_database_name
PG_USER=your_postgres_user
MINIO_ENDPOINT=https://minio.vanek-test.com
MINIO_ACCESS_KEY=your_access_key
MINIO_SECRET_KEY=your_secret_key
MINIO_BUCKET=your_bucket_name
```

## Настройка MinIO

1. Создайте бакет в MinIO:
```bash
mc alias set local-minio https://minio.vanek-test.com your_access_key your_secret_key --insecure
mc mb local-minio/postgres-backup --insecure
```

2. Создайте пользователя с необходимыми правами:
```bash
mc admin user add local-minio backup-user your_secret_key --insecure
mc admin policy add local-minio backup-policy policy.json --insecure
mc admin policy set local-minio backup-policy user=backup-user --insecure
```

Пример policy.json:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:ListBucket",
                "s3:DeleteObject"
            ],
            "Resource": [
                "arn:aws:s3:::postgres-backup/*",
                "arn:aws:s3:::postgres-backup"
            ]
        }
    ]
}
```

## Тестирование решения

Вы можете протестировать работу скрипта без установки в TeamCity или Airflow:

1. Проверьте подключение к PostgreSQL и MinIO:
```bash
cd postgres-backup
./teamcity/backup_restore.sh check
```

2. Создайте тестовый бэкап:
```bash
./teamcity/backup_restore.sh backup
```

3. Восстановите из последнего бэкапа:
```bash
./teamcity/backup_restore.sh restore
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
2. Настройте переменные окружения в Airflow
3. Перезапустите Airflow для загрузки нового DAG

### Использование

- DAG будет выполняться автоматически каждый день в полночь
- Задача восстановления (`restore_postgres`) доступна только для ручного запуска через веб-интерфейс Airflow

## Проверка работы и устранение проблем

Если у вас возникают проблемы, проверьте следующее:

1. Убедитесь, что PostgreSQL сервер доступен и работает:
```bash
pg_isready -h $PG_HOST -p $PG_PORT -d $PG_DB -U $PG_USER
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
- Восстановление из последнего доступного бэкапа
- Поддержка ручного восстановления
- Безопасная аутентификация через access key и secret key
- Автоматическое создание бакета, если он отсутствует
- Встроенные проверки подключения и обработка ошибок 