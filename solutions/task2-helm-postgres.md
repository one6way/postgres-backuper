# Задание 2: Установка PostgreSQL с помощью Helm

## Условия задания
- Установить PostgreSQL с помощью Helm chart
- Настроить базовые параметры через values.yaml:
  - База данных: mypostgres
  - Имя пользователя: mypostgres
  - Пароль: mypassword
  - Отключить persistence
  - Добавить метку mypostgres=true
  - Включить backup
- Проверить корректность установки

## Решение

### 1. Подключение к серверу
```bash
ssh user@192.168.1.10
```

### 2. Поиск чарта PostgreSQL
```bash
helm search hub postgresql
```

### 3. Создание файла values.yaml
```yaml
global:
  postgresql:
    auth:
      username: mypostgres
      password: mypassword
      database: mypostgres

primary:
  persistence:
    enabled: false

commonLabels:
  mypostgres: "true"

auth:
  enablePostgresUser: true
  postgresPassword: mypassword
  username: mypostgres
  password: mypassword
  database: mypostgres

backup:
  enabled: true
```

### 4. Установка PostgreSQL
```bash
helm install postgres-db oci://registry-1.docker.io/bitnamicharts/postgresql \
  --namespace postgres \
  --create-namespace \
  -f values.yaml
```

### 5. Проверка установки

#### Проверка namespace и пода
```bash
kubectl get pods -n postgres
```
Ожидаемый результат:
```
NAME                       READY   STATUS    RESTARTS   AGE
postgres-db-postgresql-0   1/1     Running   0          1m
```

#### Проверка меток
```bash
kubectl get pods -n postgres --show-labels
```
Ожидаемый результат должен содержать метку `mypostgres=true`

#### Проверка пароля
```bash
kubectl get secret -n postgres postgres-db-postgresql -o jsonpath="{.data.password}" | base64 -d
```
Ожидаемый результат: `mypassword`

#### Проверка подключения к базе
```bash
kubectl run postgres-test --rm --tty -i --restart="Never" \
  --namespace postgres \
  --image docker.io/bitnami/postgresql:17.4.0-debian-12-r10 \
  --env="PGPASSWORD=mypassword" \
  --command -- psql --host postgres-db-postgresql \
  -U mypostgres -d mypostgres -p 5432 -c "\conninfo"
```

## Проверка требований
1. ✅ Namespace postgres создан
2. ✅ Pod postgres-db-postgresql-0 запущен
3. ✅ Метки установлены корректно
4. ✅ Пароль установлен правильно
5. ✅ Backup включен

## Примечания
- В данной конфигурации отключена персистентность данных (persistence: false)
- Для продакшен окружения рекомендуется настроить ресурсы (CPU/Memory limits)
- Для доступа извне кластера можно использовать port-forward:
```bash
kubectl port-forward --namespace postgres svc/postgres-db-postgresql 5432:5432
``` 