# Автоматическая настройка VSCode с AI-ассистентами

Этот проект содержит скрипты и конфигурационные файлы для автоматической настройки VSCode с AI-ассистентами (Continue, Cline и CodeWhisperer как замена RooCode).

## Структура проекта

```
vscode-setup/
├── configs/
│   ├── settings.json       # Настройки VSCode
│   └── keybindings.json    # Горячие клавиши
├── docs/
│   └── setup-guide.md      # Подробное руководство
├── install-windows.ps1     # Скрипт установки для Windows
├── verify-setup.ps1        # Скрипт проверки установки
└── README.md              # Этот файл
```

## Быстрая установка (Windows)

1. Откройте PowerShell от имени администратора
2. Перейдите в директорию проекта:
   ```powershell
   cd путь/к/vscode-setup
   ```
3. Разрешите выполнение скриптов:
   ```powershell
   Set-ExecutionPolicy Bypass -Scope Process -Force
   ```
4. Запустите скрипт установки:
   ```powershell
   .\install-windows.ps1
   ```
5. После установки проверьте корректность настройки:
   ```powershell
   .\verify-setup.ps1
   ```

## Что устанавливается

1. Visual Studio Code (если не установлен)
2. Git (если не установлен)
3. Node.js (если не установлен)
4. Chocolatey (если не установлен)
5. Расширения VSCode:
   - Continue
   - Error Lens
   - GitLens
   - Material Icon Theme
   - Prettier
   - AWS Toolkit (для CodeWhisperer)
6. Cline CLI
7. Конфигурационные файлы

## После установки

1. Получите и настройте API ключ для Continue:
   - Зарегистрируйтесь на [continue.dev](https://continue.dev/)
   - Добавьте ключ в настройки VSCode

2. Настройте Cline:
   ```bash
   cline auth login
   ```

3. Настройте CodeWhisperer:
   - Откройте Command Palette (Ctrl+Shift+P)
   - Найдите "AWS: Connect to AWS"
   - Следуйте инструкциям для настройки

## Устранение проблем

Если что-то не работает:

1. Проверьте установку с помощью:
   ```powershell
   .\verify-setup.ps1
   ```

2. Убедитесь, что все компоненты установлены:
   ```powershell
   code --version
   cline --version
   git --version
   ```

3. Проверьте наличие конфигурационных файлов в:
   ```
   %APPDATA%\Code\User\settings.json
   %APPDATA%\Code\User\keybindings.json
   ```

4. Очистите кэш VSCode:
   ```powershell
   Remove-Item "$env:APPDATA\Code\Cache\*" -Recurse -Force
   Remove-Item "$env:APPDATA\Code\CachedData\*" -Recurse -Force
   ```

## Дополнительная информация

Подробное руководство по настройке и использованию находится в файле [docs/setup-guide.md](docs/setup-guide.md). 