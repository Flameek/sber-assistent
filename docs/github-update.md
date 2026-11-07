# Репозиторий и ветки

Репозиторий: https://github.com/Flameek/sber-assistent

- `main` — исходный проект из переданного ZIP.
- `feature/ai-assistant` — новая RAG-версия с языковой моделью и документацией команды БВТ2506.

Клонирование новой версии:

```bash
git clone --branch feature/ai-assistant https://github.com/Flameek/sber-assistent.git
cd sber-assistent
```

Далее — установка Python-зависимостей, локальной модели и запуск по README. Для своих изменений внутри этой ветки:

```bash
git status --short
git add PATH_TO_CHANGED_FILE
git commit -m "Describe the change"
git push
```

Перед коммитом проверьте `git diff --cached`. Ключи GigaChat, `.env`, базы с пользователями, пароли, модели и реальные банковские документы в репозиторий не добавляются. В текущем проекте опубликован только синтетический корпус.

Новая версия представляется отдельным pull request; объединение с `main` выполняется после командного просмотра и проверки демонстрации.
