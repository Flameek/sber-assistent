"""Real model clients. External requests require explicit operator opt-in."""
from dataclasses import dataclass
import ipaddress
import json
import os
import ssl
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler
from uuid import uuid4


class ModelError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class ModelConfig:
    provider: str = 'local'
    model: str = 'qwen2.5:1.5b'
    base_url: str = 'http://127.0.0.1:11434/v1'
    external_enabled: bool = False
    timeout: float = 120

    @classmethod
    def from_env(cls):
        provider = os.getenv('LLM_PROVIDER', 'local')
        return cls(provider=provider,
                   model=os.getenv('LLM_MODEL', 'GigaChat' if provider == 'gigachat' else 'qwen2.5:1.5b'),
                   base_url=os.getenv('LLM_BASE_URL', 'http://127.0.0.1:11434/v1'),
                   external_enabled=os.getenv('ALLOW_EXTERNAL_LLM', 'false').lower() == 'true',
                   timeout=float(os.getenv('LLM_TIMEOUT', '120')))


def local_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        return False
    if parsed.hostname in ('localhost', 'ollama', 'llama'):
        return True
    try:
        address = ipaddress.ip_address(parsed.hostname)
        return address.is_loopback or address.is_private and not address.is_unspecified
    except ValueError:
        return False


class ModelClient:
    def __init__(self, config=None):
        self.config = config or ModelConfig.from_env()
        self._token = None
        self._expires = 0
        self._lock = threading.Lock()
        if self.config.provider not in ('local', 'gigachat'):
            raise ModelError('Неизвестный LLM_PROVIDER. Используйте local или gigachat.')
        if self.config.provider == 'local' and not local_url(self.config.base_url):
            raise ModelError('Для локальной модели нужен loopback/private IP или имя сервиса ollama/llama.')
        if self.config.provider == 'gigachat' and not self.config.external_enabled:
            raise ModelError('Внешняя модель отключена. Нужен ALLOW_EXTERNAL_LLM=true.')

    def request(self, url, body, headers=None, form=False):
        headers = dict(headers or {})
        headers.setdefault('Content-Type', 'application/x-www-form-urlencoded' if form else 'application/json')
        payload = urlencode(body).encode() if form else json.dumps(body, ensure_ascii=False).encode()
        ca = os.getenv('GIGACHAT_CA_BUNDLE') if self.config.provider == 'gigachat' else None
        context = ssl.create_default_context(cafile=ca)
        opener = build_opener(NoRedirect(), HTTPSHandler(context=context))
        try:
            with opener.open(Request(url, payload, headers, method='POST'), timeout=self.config.timeout) as response:
                raw = response.read(1_000_001)
                if len(raw) > 1_000_000:
                    raise ModelError('Модель вернула слишком большой ответ.')
                return json.loads(raw)
        except HTTPError as error:
            # Do not echo remote bodies: they may contain credentials or context.
            raise ModelError(f'Сервис модели вернул HTTP {error.code}.') from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise ModelError('Не удалось получить ответ модели. Проверьте адрес, запуск модели и доверенные сертификаты.') from None

    def gigachat_token(self):
        supplied = os.getenv('GIGACHAT_ACCESS_TOKEN')
        if supplied:
            return supplied
        credentials = os.getenv('GIGACHAT_CREDENTIALS')
        if not credentials:
            raise ModelError('Задайте GIGACHAT_CREDENTIALS или GIGACHAT_ACCESS_TOKEN в окружении сервера.')
        with self._lock:
            if self._token and time.time() < self._expires - 60:
                return self._token
            result = self.request('https://ngw.devices.sberbank.ru:9443/api/v2/oauth',
                                  {'scope': os.getenv('GIGACHAT_SCOPE', 'GIGACHAT_API_PERS')},
                                  {'Authorization': 'Basic ' + credentials, 'RqUID': str(uuid4())}, form=True)
            try:
                self._token = result['access_token']
                self._expires = float(result['expires_at']) / 1000
            except (KeyError, TypeError, ValueError):
                raise ModelError('Некорректный ответ авторизации GigaChat.') from None
            return self._token

    def complete(self, messages, schema=None):
        body = {'model': self.config.model, 'messages': messages, 'temperature': 0,
                'max_tokens': 900, 'stream': False}
        if self.config.provider == 'gigachat':
            url = 'https://gigachat.devices.sberbank.ru/api/v1/chat/completions'
            headers = {'Authorization': 'Bearer ' + self.gigachat_token()}
        else:
            url = self.config.base_url.rstrip('/') + '/chat/completions'
            headers = {}
            body['response_format'] = ({'type': 'json_schema', 'json_schema': {'name': 'kb_answer', 'strict': True, 'schema': schema}}
                                       if schema else {'type': 'json_object'})
        result = self.request(url, body, headers)
        try:
            content = result['choices'][0]['message']['content']
            if not isinstance(content, str):
                raise ValueError
            return content
        except (KeyError, IndexError, TypeError, ValueError):
            raise ModelError('Модель вернула ответ неизвестного формата.') from None
