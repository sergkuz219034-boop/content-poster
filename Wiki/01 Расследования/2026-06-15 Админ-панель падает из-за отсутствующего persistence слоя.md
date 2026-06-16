# Симптом

При открытии пункта `👑 Админ-панель` бот падает в runtime.

# Зона системы

- [[02 Архитектура/Бот и состояние]]
- [[04 Сущности/Файлы состояния]]
- [bot.py](C:\Users\sergk\OneDrive\Desktop\traffichubserver\content-poster\bot.py)
- [bot.log](C:\Users\sergk\OneDrive\Desktop\traffichubserver\content-poster\bot.log)

# Гипотеза

В коде есть UI и обработчики админ-панели, но отсутствует слой хранения для пользователей, биллинга и системного промта.

# Проверка

- Поиск по проекту показал вызовы `is_super_admin`, `load_billing_config`, `load_users_db`, `load_system_prompt`, `save_*`, `get_or_create_user`, но их определений не было.
- Лог подтверждает фактическое падение: `NameError: name 'is_super_admin' is not defined`.
- После добавления helper-функций импорт модуля и smoke-проверка helper-слоя проходят.

# Наблюдение

- Админ-панель в этом проекте не web UI, а Telegram-меню внутри бота.
- Источники состояния: `posts.json`, `users.json`, `billing_config.json`, `system_prompt.txt`, `vacancy_config.json`.
- `users.json` в текущем workspace был в legacy-формате `[]`; код теперь нормализует это в пустой словарь на чтении.

# Вывод

Первопричина была в неполной сборке `bot.py`: UI-логика админки была добавлена без persistence-слоя. После добавления `users.json`, `billing_config.json` и `system_prompt.txt` этот класс падения закрыт, но проект всё ещё требует live runtime smoke-check перед релизом.

# Следующий шаг

- Проверить end-to-end runtime с реальным Telegram polling.
- После локального smoke/runtime-check проверить сервер и только затем выкладывать.
