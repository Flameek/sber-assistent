"""Synthetic handbook. Every public retrieval path starts from the active snapshot."""
from hashlib import sha256
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
ROLES = {"ib": "Стажёр ИБ", "support": "Стажёр поддержки"}

def seed():
    return json.loads((ROOT / "data/documents.json").read_text())

def chunks(documents):
    latest = {}
    for d in documents:
        if d["id"] not in latest or d["version"] > latest[d["id"]]["version"]:
            latest[d["id"]] = d
    result = []
    for d in latest.values():
        for s in d["sections"]:
            ref = f"{d['id']}@{d['version']}#{s['key']}"
            result.append({**{k:v for k,v in d.items() if k!="sections"},
                           **{k:v for k,v in s.items() if k in ("key","text","topic","facts")}, "ref": ref})
    return sorted(result, key=lambda x:x["ref"])

def digest(rows):
    raw = json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()
    return sha256(raw).hexdigest()[:24]

def token_hash(token):
    """Stable across Python processes for reproducible FastText initialization."""
    return int.from_bytes(sha256(token.encode('utf-8')).digest()[:8], 'little')
