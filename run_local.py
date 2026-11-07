"""Cross-platform local launch; demo profiles must be explicitly requested."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--demo', action='store_true', help='Показать переключатель учебных профилей')
    parser.add_argument('--port', type=int, default=8501)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    env = dict(os.environ, KB_BACKEND='local')
    if args.demo:
        env['KB_DEMO_MODE'] = 'true'
    raise SystemExit(subprocess.call([
        sys.executable, '-m', 'streamlit', 'run', str(root / 'app.py'),
        '--server.address=127.0.0.1', f'--server.port={args.port}', '--browser.gatherUsageStats=false',
    ], cwd=root, env=env))
