# Задание 1: Установка и настройка Helm

## Условия задания

1. Установить утилиту helm любым удобным способом и настроить autocomplete
2. Найти команду, которая выводит версию helm в консоль, и сохранить её вывод в файл $HOME/version
3. Найти команду, которая выводит переменные среды helm в консоль, и сохранить её вывод в файл $HOME/variables
4. Найти флаг, который ограничивает количество обращений helm к kube-apiserver, и написать его имя в файл $HOME/flag

## Решение

### 1. Подключение к серверу

```bash
sshpass -p 'password123' ssh -o StrictHostKeyChecking=no user@192.168.1.100
```

### 2. Установка Helm

Установка через репозиторий:

```bash
# Добавление ключа и репозитория
curl https://baltocdn.com/helm/signing.asc | gpg --dearmor | sudo tee /usr/share/keyrings/helm.gpg > /dev/null
sudo apt-get install apt-transport-https --yes
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/helm.gpg] https://baltocdn.com/helm/stable/debian/ all main" | sudo tee /etc/apt/sources.list.d/helm-stable-debian.list

# Обновление и установка
sudo apt-get update
sudo apt-get install helm -y
```

### 3. Настройка автодополнения

```bash
# Создание директории для автодополнения
mkdir -p /etc/bash_completion.d

# Генерация и установка автодополнения
helm completion bash | sudo tee /etc/bash_completion.d/helm > /dev/null

# Активация автодополнения в текущей сессии
source <(helm completion bash)
```

### 4. Сохранение версии Helm

```bash
helm version > $HOME/version
```

Результат:
```
version.BuildInfo{Version:"v3.17.2", GitCommit:"cc0bbbd6d6276b83880042c1ecb34087e84d41eb", GitTreeState:"clean", GoVersion:"go1.23.7"}
```

### 5. Сохранение переменных окружения

```bash
helm env > $HOME/variables
```

Результат содержит все переменные окружения Helm, включая:
- HELM_BIN
- HELM_BURST_LIMIT
- HELM_CACHE_HOME
- HELM_CONFIG_HOME
и другие.

### 6. Определение флага для ограничения обращений к API

После анализа документации и проверки различных флагов, был найден правильный флаг:

```bash
echo "--qps" > $HOME/flag
```

Этот флаг контролирует количество запросов в секунду (Queries Per Second) при обращении к API-серверу Kubernetes.

## Проверка результатов

Для проверки корректности выполнения можно использовать следующие команды:

```bash
# Проверка версии
cat $HOME/version

# Проверка переменных
cat $HOME/variables

# Проверка флага
cat $HOME/flag
```

## Примечания

- Флаг `--qps` используется для ограничения количества запросов в секунду к API-серверу Kubernetes
- В переменных окружения можно увидеть значение `HELM_QPS="0.00"`, что подтверждает наличие этого параметра
- Автодополнение значительно упрощает работу с Helm, предоставляя подсказки по командам и флагам 