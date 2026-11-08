"""Start a repeatable presentation without deleting the working database."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kb.corpus import chunks
from kb.llm import ModelClient, ModelConfig, ModelError
from kb.store import Store


def main():
    parser = argparse.ArgumentParser(description='Подготовить отдельную учебную базу и запустить показ')
    parser.add_argument('--resume', type=Path, help='Продолжить показ с существующим SQLite-файлом')
    parser.add_argument('--port', type=int, default=8501)
    parser.add_argument('--backend', choices=('local', 'elastic'), default='local')
    parser.add_argument('--es-url', default='http://127.0.0.1:9200')
    parser.add_argument('--llm-url', default='http://127.0.0.1:11434/v1')
    parser.add_argument('--model', default='qwen2.5:1.5b')
    parser.add_argument('--prepare-only', action='store_true', help='Создать/проверить базу, не запускать сервер')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Порт должен быть от 1 до 65535')
    try:
        # Validate the address; this does not call the model or require it to be running.
        ModelClient(ModelConfig(model=args.model, base_url=args.llm_url))
    except ModelError as error:
        parser.error(str(error))
    if args.resume:
        db_path = args.resume.expanduser().resolve()
        if not db_path.is_file():
            parser.error('--resume должен указывать на существующий SQLite-файл')
        if not db_path.is_relative_to((ROOT / '.local' / 'demo').resolve()) or not (db_path.parent / 'run.json').is_file():
            parser.error('--resume принимает только базу репетиции, созданную этим скриптом в .local/demo')
    else:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        run_dir = ROOT / '.local' / 'demo' / (stamp + '-' + uuid4().hex[:8])
        run_dir.mkdir(parents=True, exist_ok=False)
        db_path = run_dir / 'handbook.sqlite'
    store = Store(db_path)
    published = store.published()
    env = dict(os.environ, KB_DB=str(db_path), KB_BACKEND=args.backend,
               KB_DEMO_MODE='true', LLM_PROVIDER='local', LLM_MODEL=args.model,
               LLM_BASE_URL=args.llm_url, LLM_TIMEOUT='120',
               ALLOW_EXTERNAL_LLM='false', ES_URL=args.es_url)
    print('Режим: учебные профили, локальная модель, внешний API отключён.', flush=True)
    print('База:', db_path, flush=True)
    print(f'Записей: {len(published)}; действующих разделов: {len(chunks(published))}.', flush=True)
    print('Поиск:', args.backend, flush=True)
    print('Модель:', args.model, 'по адресу', args.llm_url, flush=True)
    print('Файлы для загрузки:', ROOT / 'demo' / 'files', flush=True)
    print('Сценарий:', ROOT / 'demo' / '04-presentation.md', flush=True)
    print('Новая репетиция без --resume создаёт другую базу; старые файлы сохраняются.', flush=True)
    if not args.resume:
        (db_path.parent / 'run.json').write_text(json.dumps({
            'database': str(db_path), 'backend': args.backend, 'model': args.model,
            'llm_url': args.llm_url, 'port': args.port,
        }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if args.prepare_only:
        print('Подготовка завершена. Сервер не запущен.', flush=True)
        return 0
    return subprocess.call([
        sys.executable, '-m', 'streamlit', 'run', str(ROOT / 'app.py'),
        '--server.address=127.0.0.1', f'--server.port={args.port}',
        '--browser.gatherUsageStats=false',
    ], cwd=ROOT, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
