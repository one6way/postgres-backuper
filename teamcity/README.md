# PostgreSQL Backup and Restore Tool

This tool provides functionality for backing up and restoring PostgreSQL databases with MinIO integration.

## Features

- Backup PostgreSQL databases to MinIO
- Restore PostgreSQL databases from MinIO backups
- Support for schema and table filtering
- Compression of backups
- Detailed logging
- Error handling and validation
- Airflow integration with scheduled backups

## Prerequisites

- Python 3.8+
- PostgreSQL client tools (pg_dump, pg_restore)
- MinIO server
- Required Python packages (see requirements.txt)
- Apache Airflow (for scheduled backups)

## Installation

1. Clone the repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Airflow Setup

1. Copy the DAG file to your Airflow DAGs directory:
```bash
cp postgres_backup_dag.py $AIRFLOW_HOME/dags/
```

2. Copy the backup script to your Airflow scripts directory:
```bash
mkdir -p $AIRFLOW_HOME/dags/scripts
cp postgres_backup_restore.py $AIRFLOW_HOME/dags/scripts/
```

3. Set up Airflow variables for sensitive data:
```bash
airflow variables set postgres_password "your_password"
airflow variables set minio_access_key "your_access_key"
airflow variables set minio_secret_key "your_secret_key"
airflow variables set postgres_host "your_host"
airflow variables set postgres_port "5432"
airflow variables set postgres_user "your_user"
airflow variables set postgres_database "your_database"
airflow variables set minio_endpoint "http://your-minio:9000"
airflow variables set minio_bucket "backups"
```

4. Enable the DAG in the Airflow web interface

## Usage

### Manual Backup

```bash
python postgres_backup_restore.py \
    --mode backup \
    --host localhost \
    --port 5432 \
    --user postgres \
    --password your_password \
    --database your_database \
    --minio-endpoint http://localhost:9000 \
    --minio-access-key your_access_key \
    --minio-secret-key your_secret_key \
    --minio-bucket backups \
    --backup-name my_backup
```

### Manual Restore

```bash
python postgres_backup_restore.py \
    --mode restore \
    --host localhost \
    --port 5432 \
    --user postgres \
    --password your_password \
    --database your_database \
    --minio-endpoint http://localhost:9000 \
    --minio-access-key your_access_key \
    --minio-secret-key your_secret_key \
    --minio-bucket backups \
    --backup-name my_backup \
    --force
```

### Scheduled Backups with Airflow

The DAG is configured to run daily at midnight. You can:
- Monitor backup status in the Airflow web interface
- Trigger manual backups through the Airflow UI
- Configure email notifications for failures
- Set up retry policies for failed backups

### Options

- `--mode`: Operation mode (backup/restore)
- `--host`: PostgreSQL host
- `--port`: PostgreSQL port
- `--user`: PostgreSQL user
- `--password`: PostgreSQL password
- `--database`: PostgreSQL database name
- `--minio-endpoint`: MinIO server endpoint
- `--minio-access-key`: MinIO access key
- `--minio-secret-key`: MinIO secret key
- `--minio-bucket`: MinIO bucket name
- `--schemas`: Comma-separated list of schemas to include
- `--exclude-schemas`: Comma-separated list of schemas to exclude
- `--tables`: Comma-separated list of tables to include
- `--exclude-tables`: Comma-separated list of tables to exclude
- `--backup-name`: Name for the backup
- `--force`: Force restore (drop existing database)

## Logging

The tool logs all operations to stdout with timestamps and operation details. Logs include:
- Connection attempts
- Backup/restore progress
- Error messages
- Success confirmations

## Error Handling

The tool includes comprehensive error handling for:
- Connection failures
- Invalid configurations
- Backup/restore failures
- MinIO operations
- Database operations

## Security Considerations

- Passwords and sensitive information should be provided through environment variables or secure configuration management
- Ensure proper permissions on MinIO buckets
- Use secure connections (HTTPS) for MinIO endpoint
- Consider using SSL for PostgreSQL connections
- Use Airflow variables for storing sensitive data
- Implement proper access controls for Airflow web interface 