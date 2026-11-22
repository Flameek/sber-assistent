"""Замер ресурсов для отчёта: время ответа, память и место на диске.

Два режима, каждый — отдельным запуском, чтобы память одного не смешивалась с другим:
  python scripts/measure_resources.py --mode search          поиск по инструкциям (TF-IDF, без LLM)
  python scripts/measure_resources.py --mode ai              ИИ-ответ через локальную LLM (Ollama)
  python scripts/measure_resources.py --mode ai --cold       то же, но сначала выгрузить модель из памяти,
                                                             чтобы честно измерить холодный старт
Вопросы берутся из scripts/evaluate_ai.py — те же 10 сценариев, что в отчёте о качестве.
"""
import argparse
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kb.backend import Local
from kb.llm import ModelConfig
from kb.rag import Assistant
from kb.store import Store
from scripts.evaluate_ai import CASES


def peak_memory_mb():
    """Пиковая память этого процесса (приложение без Ollama)."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        kernel32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
        return counters.PeakWorkingSetSize / 2**20
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # в Linux ru_maxrss в КиБ


def ollama(path, body=None):
    """Запрос к служебному API Ollama (не к модели): загруженные модели, список скачанных, выгрузка."""
    base = ModelConfig.from_env().base_url.rstrip("/").removesuffix("/v1")
    data = json.dumps(body).encode() if body is not None else None
    request = Request(base + path, data=data, headers={"Content-Type": "application/json"},
                      method="POST" if data else "GET")
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def duration(ms):
    """Короткие замеры — в миллисекундах, длинные — в секундах."""
    return f"{ms:.1f} мс" if ms < 1000 else f"{ms / 1000:.1f} с"


def percentile_95(values):
    ordered = sorted(values)
    return ordered[int(0.95 * (len(ordered) - 1))]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("search", "ai"), default="search")
    parser.add_argument("--cold", action="store_true", help="перед замером выгрузить модель из памяти Ollama")
    args = parser.parse_args()
    model_name = ModelConfig.from_env().model

    if args.mode == "ai" and args.cold:
        ollama("/api/generate", {"model": model_name, "keep_alive": 0})  # keep_alive=0 — выгрузить модель
        time.sleep(2)

    times, with_model = [], []
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / "measure.sqlite")
        assistant = Assistant(store, Local(), search_only=args.mode == "search")
        for _, role, area, question, _, _ in CASES:
            started = time.perf_counter()
            result = assistant.ask(role, question, area)
            times.append(1000 * (time.perf_counter() - started))
            if result.get("generated"):
                with_model.append(times[-1])

    if args.mode == "search":
        label = "поиск по инструкциям (TF-IDF, без LLM)"
    else:
        label = f"ИИ-ответ ({model_name}{', холодный старт' if args.cold else ''})"
    first, rest = times[0], times[1:]
    print(f"Режим: {label}")
    print(f"Процессор: {platform.processor() or platform.machine()}, потоков: {os.cpu_count()}, ОС: {platform.system()} {platform.release()}")
    print(f"Вопросов: {len(times)}, из них с вызовом модели: {len(with_model)}")
    if with_model:
        print(f"Только вопросы с вызовом модели: медиана {duration(statistics.median(with_model))}, "
              f"максимум {duration(max(with_model))}")
    print(f"Первый запрос: {duration(first)}")
    print(f"Остальные: медиана {duration(statistics.median(rest))}, 95% быстрее {duration(percentile_95(rest))}")
    print(f"Пиковая память приложения: {peak_memory_mb():.0f} МБ")

    if args.mode == "ai":
        loaded = [m for m in ollama("/api/ps").get("models", []) if m.get("name") == model_name]
        on_disk = [m for m in ollama("/api/tags").get("models", []) if m.get("name") == model_name]
        if loaded:
            print(f"Память Ollama под модель: {loaded[0]['size'] / 2**20:.0f} МБ "
                  f"(из них видеопамять: {loaded[0].get('size_vram', 0) / 2**20:.0f} МБ)")
        if on_disk:
            print(f"Модель на диске: {on_disk[0]['size'] / 2**20:.0f} МБ")


if __name__ == "__main__":
    main()