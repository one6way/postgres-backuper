# Проверка установленных компонентов
Write-Host "Проверка установленных компонентов..." -ForegroundColor Green

# Проверка VSCode
if (Test-Command code) {
    $version = code --version
    Write-Host "✓ VSCode установлен (версия: $version)" -ForegroundColor Green
} else {
    Write-Host "✗ VSCode не установлен" -ForegroundColor Red
}

# Проверка Cline
if (Test-Command cline) {
    $version = cline --version
    Write-Host "✓ Cline установлен (версия: $version)" -ForegroundColor Green
} else {
    Write-Host "✗ Cline не установлен" -ForegroundColor Red
}

# Проверка расширений
Write-Host "`nПроверка расширений VSCode:" -ForegroundColor Green
$extensions = @(
    "continue.continue",
    "usernamehw.errorlens",
    "eamodio.gitlens",
    "pkief.material-icon-theme",
    "esbenp.prettier-vscode",
    "amazonwebservices.aws-toolkit-vscode"
)

foreach ($extension in $extensions) {
    $installed = code --list-extensions | Where-Object { $_ -eq $extension }
    if ($installed) {
        Write-Host "✓ $extension установлен" -ForegroundColor Green
    } else {
        Write-Host "✗ $extension не установлен" -ForegroundColor Red
    }
}

# Проверка конфигурационных файлов
Write-Host "`nПроверка конфигурационных файлов:" -ForegroundColor Green
$CONFIG_DIR = "$env:APPDATA\Code\User"

if (Test-Path "$CONFIG_DIR\settings.json") {
    Write-Host "✓ settings.json найден" -ForegroundColor Green
} else {
    Write-Host "✗ settings.json не найден" -ForegroundColor Red
}

if (Test-Path "$CONFIG_DIR\keybindings.json") {
    Write-Host "✓ keybindings.json найден" -ForegroundColor Green
} else {
    Write-Host "✗ keybindings.json не найден" -ForegroundColor Red
}

# Проверка Git
if (Test-Command git) {
    $version = git --version
    Write-Host "`n✓ Git установлен ($version)" -ForegroundColor Green
} else {
    Write-Host "`n✗ Git не установлен" -ForegroundColor Red
}

Write-Host "`nПроверка завершена!" -ForegroundColor Green
Write-Host "Если есть красные отметки (✗), запустите install-windows.ps1 от имени администратора" 