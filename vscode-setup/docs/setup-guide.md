# Настройка VSCode с AI-ассистентами (Cline + RooCode + Continue)

## 1. Установка базовых компонентов

### Visual Studio Code
1. Скачать VSCode с [официального сайта](https://code.visualstudio.com/)
2. Установить рекомендуемую версию 1.87.0 или новее

### Cline
1. Установить Cline CLI:
```bash
# Для macOS
brew install cline

# Для Linux
curl -L https://raw.githubusercontent.com/cline-ai/cline/main/install.sh | bash

# Для Windows
winget install cline
```

2. Настройка Cline:
```bash
cline auth login
cline config set-default-model gpt-4
```

### Continue
1. Установить расширение Continue из VSCode Marketplace
2. Получить API ключ:
   - Зарегистрироваться на [continue.dev](https://continue.dev/)
   - Создать новый API ключ в настройках
3. Настройка в VSCode:
   ```json
   {
     "continue.apiKey": "ваш_ключ",
     "continue.model": "gpt-4",
     "continue.completionModel": "gpt-4",
     "continue.systemMessage": "Вы - опытный разработчик, помогающий с кодом"
   }
   ```

## 2. Интеграция компонентов

### Настройка Cline в VSCode
1. Установить расширение "Cline for VSCode"
2. Добавить в settings.json:
```json
{
  "cline.enabled": true,
  "cline.shortcuts.suggest": "ctrl+space",
  "cline.shortcuts.complete": "tab",
  "cline.ai.model": "gpt-4"
}
```

### Настройка Continue
1. Добавить горячие клавиши в keybindings.json:
```json
[
  {
    "key": "ctrl+shift+/",
    "command": "continue.edit"
  },
  {
    "key": "ctrl+shift+e",
    "command": "continue.explain"
  }
]
```

### RooCode (альтернативные варианты)
Так как RooCode сейчас недоступен, рекомендуется использовать:
1. Amazon CodeWhisperer:
   - Бесплатен для индивидуальных разработчиков
   - Интегрируется с VSCode
   - Поддерживает автодополнение кода

2. Или Tabnine:
   - Имеет бесплатный план
   - Работает офлайн
   - Хорошо интегрируется с VSCode

## 3. Оптимальные настройки VSCode

### Основные настройки (settings.json)
```json
{
  "editor.formatOnSave": true,
  "editor.inlineSuggest.enabled": true,
  "editor.suggestSelection": "first",
  "editor.acceptSuggestionOnEnter": "smart",
  "editor.snippetSuggestions": "top",
  
  "continue.enabled": true,
  "continue.telemetry": false,
  
  "cline.enabled": true,
  "cline.telemetry": false,
  
  "workbench.colorTheme": "Default Dark Modern",
  "workbench.iconTheme": "material-icon-theme"
}
```

### Рекомендуемые расширения
1. Error Lens
   - Улучшенное отображение ошибок
   - `code --install-extension usernamehw.errorlens`

2. GitLens
   - Расширенная работа с Git
   - `code --install-extension eamodio.gitlens`

3. Material Icon Theme
   - Улучшенные иконки файлов
   - `code --install-extension pkief.material-icon-theme`

## 4. Использование

### Cline
- `Ctrl+Space` - вызов подсказок
- `Tab` - принятие предложения
- Команды в терминале:
  ```bash
  cline explain "код"
  cline suggest "задача"
  ```

### Continue
- `/edit` - редактирование кода
- `/explain` - объяснение кода
- `/test` - генерация тестов
- `/doc` - создание документации

### CodeWhisperer (замена RooCode)
- Автоматические предложения при наборе
- `Alt+C` - принятие предложения
- `Alt+]` - следующее предложение

## 5. Устранение проблем

### Конфликты расширений
1. Отключить конфликтующие AI-ассистенты
2. В случае конфликтов с Cline и Continue:
   ```json
   {
     "continue.suggestOnTriggerCharacters": false,
     "cline.suggestOnTriggerCharacters": true
   }
   ```

### Производительность
1. Отключить тяжелые расширения:
   ```json
   {
     "extensions.autoUpdate": false,
     "extensions.ignoreRecommendations": true
   }
   ```

2. Оптимизировать исключения:
   ```json
   {
     "search.exclude": {
       "**/node_modules": true,
       "**/dist": true,
       "**/.git": true
     }
   }
   ```

### Очистка кэша
```bash
# macOS
rm -rf ~/Library/Application\ Support/Code/Cache/*
rm -rf ~/Library/Application\ Support/Code/CachedData/*

# Windows
rmdir /s /q %APPDATA%\Code\Cache\
rmdir /s /q %APPDATA%\Code\CachedData\
``` 