"""Password login for the prototype; identity/roles are loaded server-side from SQLite."""
import argparse
from contextlib import contextmanager
import getpass
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time


PROFILES = ('ib', 'support', 'lead')


class Users:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv('KB_DB', '.local/handbook.sqlite'))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, salt TEXT, password TEXT, profile TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, username TEXT, expires REAL)')

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def password_hash(password, salt):
        return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()

    def create(self, username, password, profile):
        if not re.fullmatch(r'[a-zA-Z0-9_.-]{3,48}', username or '') or profile not in PROFILES:
            raise ValueError('Логин: 3–48 латинских букв/цифр, роль: ib/support/lead')
        if not isinstance(password, str) or not 10 <= len(password) <= 256:
            raise ValueError('Пароль: от 10 до 256 символов')
        salt = secrets.token_hex(16)
        with self.db() as db:
            db.execute('INSERT INTO users VALUES (?,?,?,?)', (username, salt, self.password_hash(password, salt), profile))

    def login(self, username, password):
        if not isinstance(username, str) or not isinstance(password, str) or len(password) > 256:
            return None
        with self.db() as db:
            user = db.execute('SELECT salt,password FROM users WHERE username=?', (username,)).fetchone()
        salt, expected = user if user else ('0' * 32, '0' * 64)
        actual = self.password_hash(password, salt)
        if not user or not hmac.compare_digest(actual, expected):
            return None
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.db() as db:
            db.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
            db.execute('INSERT INTO sessions VALUES (?,?,?)', (digest, username, time.time() + 4 * 3600))
        return token

    def session(self, token):
        if not isinstance(token, str):
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.db() as db:
            user = db.execute('SELECT u.username,u.profile FROM sessions s JOIN users u ON u.username=s.username WHERE s.token=? AND s.expires>?',
                              (digest, time.time())).fetchone()
        return {'username': user[0], 'profile': user[1]} if user else None

    def logout(self, token):
        if not isinstance(token, str):
            return
        with self.db() as db:
            db.execute('DELETE FROM sessions WHERE token=?', (hashlib.sha256(token.encode()).hexdigest(),))


if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('create',))
    parser.add_argument('username')
    parser.add_argument('--profile', choices=PROFILES, required=True)
    args = parser.parse_args()
    password = getpass.getpass('Пароль (минимум 10 символов): ')
    if password != getpass.getpass('Повторите пароль: '):
        raise SystemExit('Пароли не совпадают')
    try:
        Users().create(args.username, password, args.profile)
    except (ValueError, sqlite3.IntegrityError) as error:
        raise SystemExit(str(error))
    print('Пользователь создан:', args.username)
