# Content Poster Wiki

Главная точка входа в wiki по проекту Content Poster.

## С чего начать

1. [[START_HERE]]
2. [[01 Проекты/Content Poster/README]]
3. [[Home]]

## Что где лежит

- `01 Проекты/Content Poster/`
  Каноническая проектная карта. Сюда складываются краткие, актуальные заметки по архитектуре, входам и storage.
- `Home.md`, `AI Assistant.md`, `Configuration.md`, `Posts and Formatting.md`
  Legacy-страницы. Их не удаляем без явного перевода информации в новую карту.
- `bot.py`, `bot.log`, `posts.json`, `users.json`, `billing_config.json`
  Источник истины для поведения, состояния и runtime.

## Что помнить сразу

- проект — Telegram-бот для публикации постов;
- админ-панель реализована через Telegram-меню, а не через отдельный web UI;
- состояние файловое, без БД;
- любые выводы по поведению лучше сверять с live запуском, а не только с заметками.
