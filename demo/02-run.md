# Подготовка и запуск на Arch Linux

Команды выполняются на вашем компьютере. Для основного показа нужны Ollama с моделью и приложение. Для демонстрации Elasticsearch есть отдельный вариант ниже. Каталог проекта в примерах — `sber-assistent-ai`.

## 1. Установить один раз

```bash
sudo pacman -Syu ollama git uv
sudo systemctl enable --now ollama
systemctl is-active ollama
ollama pull qwen2.5:1.5b
ollama list
```

Служба должна показать `active`, модель — присутствовать в списке. Пакет Ollama есть в [официальном репозитории Arch](https://archlinux.org/packages/extra/x86_64/ollama/). Модель [Qwen2.5 1.5B](https://ollama.com/library/qwen2.5:1.5b) скачивается отдельно, примерно 1 ГБ. Повторный `pull` не нужен для каждого вопроса или показа. Если служба уже работает, второй `ollama serve` запускать не нужно.

## 2. Получить нужную ветку

Если проект ещё не скачан:

```bash
git clone --branch feature/ai-assistant https://github.com/Flameek/sber-assistent.git sber-assistent-ai
cd sber-assistent-ai
```

Если папка уже есть, сначала откройте её и посмотрите своё состояние:

```bash
git status --short
git fetch origin
git switch feature/ai-assistant
git pull --ff-only origin feature/ai-assistant
```

Если Git сообщает о несохранённых изменениях или расхождении веток, сначала сохраните свою работу и разберите сообщение. Для получения этих материалов не требуется удалять папку, выполнять `reset --hard` или менять исходную `main`.

## 3. Подготовить Python

Из корня проекта:

```bash
uv python install 3.12
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

Если `.venv` уже готова на Python 3.12, повторять её создание не нужно — достаточно обновить зависимости. Проверка версии:

```bash
.venv/bin/python --version
```

Используем явный путь `.venv/bin/python`, поэтому активировать окружение в Bash/Zsh/Fish не обязательно. Установка отдельного Python описана в [документации uv](https://docs.astral.sh/uv/guides/install-python/).

## 4. Проверить реальную модель до выступления

Команда явно выбирает локальную модель, даже если в `.env` сохранился другой провайдер:

```bash
env LLM_PROVIDER=local \
  LLM_BASE_URL=http://127.0.0.1:11434/v1 \
  LLM_MODEL=qwen2.5:1.5b \
  LLM_TIMEOUT=120 \
  ALLOW_EXTERNAL_LLM=false \
  .venv/bin/python scripts/check_model.py
```

Должны появиться действия по учебной инструкции и строка с моделью/временем. Это одновременно прогревает модель. Скрипт использует временную базу и локальный retrieval: он **не проверяет Elasticsearch** и не изменяет рабочие документы.

## 5. Начать отдельную репетицию

```bash
.venv/bin/python demo/start_demo.py
```

Откройте http://127.0.0.1:8501. Терминал напечатает путь вида `.local/demo/<уникальный-показ>/handbook.sqlite`. Исходные документы уже загружены. Переключатель «Учебный профиль» включён явно; пароли для этого режима не нужны.

Скрипт явно задаёт локальный провайдер, модель `qwen2.5:1.5b`, внешний API `false`, локальный backend и отдельную SQLite-базу. Эти параметры не переопределяются пользовательским `.env`. Ollama он не устанавливает и не запускает — служба должна быть готова по шагу 1.

Каждый запуск без `--resume` — новая репетиция. Старая рабочая база и предыдущие репетиции сохраняются. Для продолжения **того же** показа остановите Streamlit через Ctrl+C и укажите напечатанный путь:

```bash
.venv/bin/python demo/start_demo.py --resume .local/demo/ИМЯ_ВАШЕГО_ПОКАЗА/handbook.sqlite
```

Подставьте реально существующую папку. `--resume` принимает только базы репетиций этого скрипта, не создаёт базу по ошибочно указанному пути и не переключает обычную рабочую базу в деморежим.

При продолжении повторите нестандартные флаги: `--backend elastic`, `--es-url`, `--model`, `--llm-url`, `--port`, если использовали их раньше. `--resume` возобновляет базу, а не автоматически восстанавливает параметры из `run.json`.

Если 8501 занят:

```bash
.venv/bin/python demo/start_demo.py --port 8502
```

Для подготовки без запуска сервера: `--prepare-only`. Чтобы потом использовать эту подготовленную базу, передайте её путь через `--resume`.

## Показ с Elasticsearch и уже установленной Ollama

Этот маршрут использует **Ollama на хосте**, Elasticsearch в одном контейнере и Streamlit на хосте. Загрузка модели повторно в Docker не требуется.

Установите Docker, если его ещё нет:

```bash
sudo pacman -Syu docker docker-compose
sudo systemctl enable --now docker
```

Из корня проекта запустите только Elasticsearch:

```bash
sudo docker compose -f compose.yaml -f demo/compose.elasticsearch.yaml up -d --wait elastic
```

Дополнительный файл публикует порт **только на 127.0.0.1:9200**. Основной `compose.yaml` без этого файла по-прежнему не публикует Elasticsearch. Не запускайте этим маршрутом весь стек: для него сейчас нужны только `elastic`, хостовая Ollama и хостовое приложение.

В другом терминале из корня проекта:

```bash
.venv/bin/python demo/start_demo.py --backend elastic --es-url http://127.0.0.1:9200
```

Далее все шаги показа одинаковы. При запросе будет использован/создан индекс `kb-demo-<hash>`. Можно отдельно проверить сервис и метрики:

```bash
curl http://127.0.0.1:9200/
curl 'http://127.0.0.1:9200/_cat/indices/kb-demo-*?v'
env KB_TEST_ES=1 ES_URL=http://127.0.0.1:9200 .venv/bin/python -m unittest -v tests.test_elastic_live
env ES_URL=http://127.0.0.1:9200 .venv/bin/python -m kb.benchmark --backend elastic
```

Если Elasticsearch уже установлен отдельно, контейнер не нужен: передайте его адрес через `--es-url`.

После показа Ctrl+C останавливает Streamlit. Остановить только контейнер Elasticsearch, сохранив его том:

```bash
sudo docker compose -f compose.yaml -f demo/compose.elasticsearch.yaml stop elastic
```

Не используйте `down --volumes` для обычной репетиции: создание свежей базы через наш скрипт не требует удаления томов.

## Альтернатива: весь проект в Docker

Полный `docker compose up --build --wait` запускает другую топологию: контейнеры приложения, Elasticsearch и Ollama. Его SQLite и модели лежат в Docker-томах; это не те же файлы, что у хостовой Ollama и `.local` на компьютере. Модель загружается командой `docker compose exec ollama ollama pull qwen2.5:1.5b`.

Используйте этот вариант по основному README, если решили показывать именно контейнерный стенд. Не смешивайте одновременно два приложения на порту 8501. Ранее здесь был проверен нативный Elasticsearch и локальная LLM; полный Compose и новый вспомогательный маршрут нужно предварительно проверить на вашем Docker, а не запускать впервые перед преподавателем.

## Если показываем настоящий вход

В демонстрационном режиме роли переключаются. Это не вход в корпоративную систему. Для обычной рабочей базы создайте пользователей и запустите приложение без `--demo`:

```bash
.venv/bin/python -m kb.users create oleg --profile lead
.venv/bin/python -m kb.users create trainee-ib --profile ib
.venv/bin/python -m kb.users create trainee-support --profile support
env KB_DEMO_MODE=false .venv/bin/python run_local.py
```

CLI использует `KB_DB` из окружения/`.env`; убедитесь, что создаёте пользователей в той же базе, которую откроет приложение. Пароль вводится скрыто, минимум 10 символов, готовых паролей в проекте нет. Быстрый `run_local.py` всегда выбирает локальный backend, даже если `.env` содержит `KB_BACKEND=elastic`. Для проверки Elasticsearch используйте `demo/start_demo.py --backend elastic` либо прямой запуск Streamlit с явно заданным окружением.
