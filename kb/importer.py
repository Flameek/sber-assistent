"""Parse bounded training documents without contacting external services."""
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile, BadZipFile

from .store import validate

MAX_FILE = 5 * 1024 * 1024
MAX_TEXT = 60000


def extract(filename, content):
    if not content or len(content) > MAX_FILE:
        raise ValueError('Документ должен быть непустым и не больше 5 МиБ')
    suffix = Path(filename).suffix.lower()
    if suffix in ('.txt', '.md'):
        try:
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise ValueError('Сохраните текст в UTF-8') from None
    elif suffix == '.pdf':
        from pypdf import PdfReader
        try:
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted or len(reader.pages) > 100:
                raise ValueError('Нужен PDF без пароля, до 100 страниц')
            pages = []
            size = 0
            for page in reader.pages:
                value = page.extract_text() or ''
                size += len(value)
                if size > MAX_TEXT:
                    raise ValueError('В документе больше 60 000 символов текста')
                pages.append(value)
            text = '\n\n'.join(pages)
        except ValueError:
            raise
        except Exception:
            raise ValueError('Не удалось прочитать PDF') from None
    elif suffix == '.docx':
        from docx import Document
        try:
            with ZipFile(BytesIO(content)) as archive:
                if len(archive.infolist()) > 2000 or sum(f.file_size for f in archive.infolist()) > 20 * 1024 * 1024:
                    raise ValueError('Слишком большой распакованный DOCX')
            document = Document(BytesIO(content))
            blocks = []
            for block in document.iter_inner_content():
                if hasattr(block, 'rows'):
                    blocks.extend(' | '.join(cell.text for cell in row.cells) for row in block.rows)
                else:
                    blocks.append(block.text)
            text = '\n\n'.join(blocks)
        except ValueError:
            raise
        except Exception:
            raise ValueError('Не удалось прочитать DOCX') from None
    else:
        raise ValueError('Поддерживаются PDF, DOCX, TXT, MD и структурированный JSON')
    text = text.replace('\x00', '').strip()
    if not text:
        raise ValueError('Текст не найден. Для сканированного PDF сначала нужен OCR.')
    if len(text) > MAX_TEXT:
        raise ValueError('В документе больше 60 000 символов текста')
    return text


def split_text(text, limit=2500, overlap=150):
    """Overlapping chunks preserve complete coverage and prefer paragraph boundaries."""
    if not 0 <= overlap < limit:
        raise ValueError('Некорректные параметры фрагментации')
    sections = []
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            cut = max(text.rfind('\n', start + limit // 2, end), text.rfind('. ', start + limit // 2, end))
            if cut > start:
                end = cut + 1
        sections.append({'key': f'section-{len(sections)+1:03}', 'text': text[start:end].strip()})
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    if len(sections) > 30:
        raise ValueError('Слишком много разделов: разделите документ на несколько инструкций')
    return sections


def import_document(filename, content, metadata=None):
    if Path(filename).suffix.lower() == '.json':
        if len(content) > MAX_FILE:
            raise ValueError('Файл больше 5 МиБ')
        try:
            return validate(json.loads(content))
        except (UnicodeError, json.JSONDecodeError):
            raise ValueError('Некорректный JSON') from None
    if metadata is None:
        raise ValueError('Заполните метаданные документа')
    sections = split_text(extract(filename, content))
    topic = metadata.get('topic') or metadata['rule']
    for section in sections:
        section['topic'] = topic
    doc = {k: v for k, v in metadata.items() if k != 'topic'}
    doc['sections'] = sections
    return validate(doc)
