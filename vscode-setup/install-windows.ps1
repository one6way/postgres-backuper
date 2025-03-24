# Требуется запуск от администратора
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Warning "Запустите скрипт от имени администратора!"
    Break
}

# Функция для проверки наличия команды
function Test-Command($cmdname) {
    return [bool](Get-Command -Name $cmdname -ErrorAction SilentlyContinue)
}

# Установка Chocolatey если не установлен
if (-not (Test-Command choco)) {
    Write-Host "Установка Chocolatey..."
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))
}

# Установка VSCode если не установлен
if (-not (Test-Command code)) {
    Write-Host "Установка Visual Studio Code..."
    choco install vscode -y
    refreshenv
}

# Установка Git если не установлен
if (-not (Test-Command git)) {
    Write-Host "Установка Git..."
    choco install git -y
    refreshenv
}

# Установка Node.js если не установлен
if (-not (Test-Command node)) {
    Write-Host "Установка Node.js..."
    choco install nodejs-lts -y
    refreshenv
}

# Создание директорий для конфигурации
$CONFIG_DIR = "$env:APPDATA\Code\User"
New-Item -ItemType Directory -Force -Path $CONFIG_DIR

# Установка расширений VSCode
Write-Host "Установка расширений VSCode..."
$extensions = @(
    "continue.continue",
    "usernamehw.errorlens",
    "eamodio.gitlens",
    "pkief.material-icon-theme",
    "esbenp.prettier-vscode",
    "amazonwebservices.aws-toolkit-vscode" # CodeWhisperer
)

foreach ($extension in $extensions) {
    Write-Host "Установка расширения $extension..."
    code --install-extension $extension
}

# Загрузка и установка Cline
Write-Host "Установка Cline..."
winget install cline

# Копирование конфигурационных файлов
Write-Host "Копирование конфигурационных файлов..."
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Copy-Item "$scriptPath\configs\settings.json" -Destination "$CONFIG_DIR\settings.json" -Force
Copy-Item "$scriptPath\configs\keybindings.json" -Destination "$CONFIG_DIR\keybindings.json" -Force

# Настройка Git
git config --global core.autocrlf true
git config --global init.defaultBranch main

# Очистка кэша VSCode
Write-Host "Очистка кэша VSCode..."
Remove-Item "$env:APPDATA\Code\Cache\*" -Recurse -Force
Remove-Item "$env:APPDATA\Code\CachedData\*" -Recurse -Force

Write-Host "Установка завершена! Перезапустите VSCode для применения изменений."
Write-Host "Не забудьте:"
Write-Host "1. Настроить API ключ для Continue в настройках"
Write-Host "2. Войти в Amazon CodeWhisperer"
Write-Host "3. Настроить Cline через команду 'cline auth login'" 