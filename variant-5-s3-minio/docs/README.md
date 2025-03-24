# Вариант 5: Хранение сертификатов в S3/MinIO

## Описание

Данный вариант предполагает хранение сертификатов в объектном хранилище S3/MinIO и их динамическую загрузку в Spark-приложение во время запуска. При этом подходе сертификаты хранятся централизованно в защищенном хранилище, а приложение получает к ним доступ по мере необходимости.

## Преимущества

- **Централизованное хранилище**: Все сертификаты хранятся в едином месте
- **Безопасность доступа**: Доступ к хранилищу строго контролируется через IAM-политики (AWS) или политики доступа (MinIO)
- **Версионирование**: Возможность использования версионирования S3 для хранения нескольких версий сертификатов
- **Независимость от Kubernetes**: Работает в любой среде, не только в Kubernetes
- **Масштабируемость**: Поддерживает большие объемы сертификатов для множества приложений
- **Репликация**: Возможность использования репликации S3/MinIO для повышения доступности
- **Журналирование доступа**: Детальное логирование всех операций с сертификатами

## Недостатки

- **Зависимость от внешнего сервиса**: Требуется доступность S3/MinIO для работы приложения
- **Сложность начальной настройки**: Требуется настройка политик безопасности и IAM-ролей
- **Задержки при запуске**: Время, затрачиваемое на загрузку сертификатов из хранилища
- **Управление секретами**: Требуется управление секретными ключами для доступа к S3/MinIO

## Схема взаимодействия

```
┌─────────────────────┐     ┌───────────────────────┐
│                     │     │                       │
│  Администратор      │────▶│  Загрузка сертификатов│
│                     │     │  в S3/MinIO           │
└─────────────────────┘     └───────────────────────┘
                                      │
                                      ▼
┌─────────────────────┐     ┌───────────────────────┐
│                     │     │                       │
│  S3/MinIO Bucket    │     │  IAM Политики/        │
│  с сертификатами    │◀────│  Политики доступа     │
│                     │     │                       │
└─────────────────────┘     └───────────────────────┘
        │
        │
        ▼
┌─────────────────────┐     ┌───────────────────────┐
│                     │     │                       │
│  Init Container/    │     │  Загрузка сертификатов│
│  Скрипт инициализации│────▶│  при запуске          │
└─────────────────────┘     └───────────────────────┘
        │
        │
        ▼
┌─────────────────────┐     ┌───────────────────────┐
│                     │     │                       │
│  Spark Application  │────▶│  Kafka Cluster        │
│  с загруженными     │     │  (SSL/TLS)            │
│  сертификатами      │     │                       │
└─────────────────────┘     └───────────────────────┘
```

## Процесс реализации

1. Создание бакета в S3/MinIO для хранения сертификатов
2. Настройка политик безопасности и IAM-ролей для доступа к бакету
3. Загрузка сертификатов в бакет S3/MinIO
4. Создание init-контейнера или скрипта для загрузки сертификатов при запуске Spark-приложения
5. Настройка Spark-приложения для использования загруженных сертификатов

## Пример конфигурации MinIO

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: minio-credentials
  namespace: spark
type: Opaque
data:
  accesskey: bWluaW8= # minio в base64
  secretkey: bWluaW8xMjM= # minio123 в base64
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: minio
  namespace: spark
spec:
  selector:
    matchLabels:
      app: minio
  strategy:
    type: Recreate
  template:
    metadata:
      labels:
        app: minio
    spec:
      containers:
      - name: minio
        image: minio/minio:RELEASE.2023-03-20T20-16-18Z
        args:
        - server
        - /data
        - --console-address
        - ":9001"
        env:
        - name: MINIO_ACCESS_KEY
          valueFrom:
            secretKeyRef:
              name: minio-credentials
              key: accesskey
        - name: MINIO_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: minio-credentials
              key: secretkey
        ports:
        - containerPort: 9000
        - containerPort: 9001
        volumeMounts:
        - name: data
          mountPath: /data
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: minio-pvc
```

## Пример SparkApplication с init-контейнером для загрузки сертификатов

```yaml
apiVersion: "sparkoperator.k8s.io/v1beta2"
kind: SparkApplication
metadata:
  name: kafka-spark-adb
  namespace: spark
spec:
  type: Scala
  mode: cluster
  image: "apache/spark:3.3.0"
  mainClass: org.example.KafkaSparkADB
  driver:
    cores: 1
    memory: "1g"
    serviceAccount: spark
    volumeMounts:
      - name: kafka-certs
        mountPath: /etc/kafka/ssl
    env:
      - name: KEYSTORE_PASSWORD
        valueFrom:
          secretKeyRef:
            name: kafka-ssl-passwords
            key: keystore-password
      - name: TRUSTSTORE_PASSWORD
        valueFrom:
          secretKeyRef:
            name: kafka-ssl-passwords
            key: truststore-password
    initContainers:
      - name: fetch-certs
        image: amazon/aws-cli:2.11.22
        command:
        - /bin/sh
        - -c
        - |
          aws s3 cp s3://kafka-certs-bucket/keystore.jks /mnt/certs/keystore.jks
          aws s3 cp s3://kafka-certs-bucket/truststore.jks /mnt/certs/truststore.jks
          chmod 400 /mnt/certs/*
        env:
        - name: AWS_ACCESS_KEY_ID
          valueFrom:
            secretKeyRef:
              name: s3-credentials
              key: accesskey
        - name: AWS_SECRET_ACCESS_KEY
          valueFrom:
            secretKeyRef:
              name: s3-credentials
              key: secretkey
        - name: AWS_ENDPOINT_URL
          value: http://minio:9000
        volumeMounts:
        - name: kafka-certs
          mountPath: /mnt/certs
  executor:
    cores: 1
    instances: 2
    memory: "1g"
    volumeMounts:
      - name: kafka-certs
        mountPath: /etc/kafka/ssl
    env:
      - name: KEYSTORE_PASSWORD
        valueFrom:
          secretKeyRef:
            name: kafka-ssl-passwords
            key: keystore-password
      - name: TRUSTSTORE_PASSWORD
        valueFrom:
          secretKeyRef:
            name: kafka-ssl-passwords
            key: truststore-password
    initContainers:
      - name: fetch-certs
        image: amazon/aws-cli:2.11.22
        command:
        - /bin/sh
        - -c
        - |
          aws s3 cp s3://kafka-certs-bucket/keystore.jks /mnt/certs/keystore.jks
          aws s3 cp s3://kafka-certs-bucket/truststore.jks /mnt/certs/truststore.jks
          chmod 400 /mnt/certs/*
        env:
        - name: AWS_ACCESS_KEY_ID
          valueFrom:
            secretKeyRef:
              name: s3-credentials
              key: accesskey
        - name: AWS_SECRET_ACCESS_KEY
          valueFrom:
            secretKeyRef:
              name: s3-credentials
              key: secretkey
        - name: AWS_ENDPOINT_URL
          value: http://minio:9000
        volumeMounts:
        - name: kafka-certs
          mountPath: /mnt/certs
  volumes:
    - name: kafka-certs
      emptyDir: {}
```

## Скрипт для создания S3 бакета и загрузки сертификатов

```bash
#!/bin/bash

# Переменные окружения
MINIO_ENDPOINT="http://minio:9000"
MINIO_ACCESS_KEY="minio"
MINIO_SECRET_KEY="minio123"
BUCKET_NAME="kafka-certs-bucket"
KEYSTORE_PATH="./kafka.client.keystore.jks"
TRUSTSTORE_PATH="./kafka.client.truststore.jks"

# Установка и настройка MinIO client
wget https://dl.min.io/client/mc/release/linux-amd64/mc
chmod +x mc
./mc alias set minio $MINIO_ENDPOINT $MINIO_ACCESS_KEY $MINIO_SECRET_KEY

# Создание бакета
./mc mb minio/$BUCKET_NAME

# Настройка политик доступа
./mc policy set download minio/$BUCKET_NAME

# Загрузка сертификатов
./mc cp $KEYSTORE_PATH minio/$BUCKET_NAME/keystore.jks
./mc cp $TRUSTSTORE_PATH minio/$BUCKET_NAME/truststore.jks

# Проверка
./mc ls minio/$BUCKET_NAME
```

## Конфигурация SparkSession

```python
spark = SparkSession.builder \
    .appName("Kafka-Spark-ADB") \
    .config("spark.kafka.ssl.keystore.location", "/etc/kafka/ssl/keystore.jks") \
    .config("spark.kafka.ssl.truststore.location", "/etc/kafka/ssl/truststore.jks") \
    .config("spark.kafka.ssl.keystore.password", os.environ.get("KEYSTORE_PASSWORD")) \
    .config("spark.kafka.ssl.truststore.password", os.environ.get("TRUSTSTORE_PASSWORD")) \
    .getOrCreate()
```

## Безопасные практики

1. Использование шифрования на стороне сервера (SSE) для сертификатов в S3/MinIO
2. Настройка детальных политик IAM с принципом наименьших привилегий
3. Включение версионирования бакета для возможности отката
4. Настройка журналирования доступа к бакету
5. Регулярная ротация ключей доступа к S3/MinIO
6. Использование временных учетных данных через AWS STS или аналогичные механизмы в MinIO 