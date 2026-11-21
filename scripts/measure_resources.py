"""Замер ресурсов для отчёта: время ответа, пиковая память, место на диске.

Каждый режим меряется в отдельном запуске, чтобы память одного режима не смешивалась с другим:
  python -m scripts.measure_resources tfidf
  python -m scripts.measure_resources hybrid          (модель из KB_EMBED_MODEL, по умолчанию USER-base)
"""
import os
import platform
import statistics
import sys
import time
from pathlib import Path

from kb.backend import Local
from kb.corpus import chunks, seed
from kb.evaluate import load_questions
from kb.service import Service


def peak_memory_mb():
    """Пиковая память процесса (сколько оперативной памяти он занимал в самый «тяжёлый» момент)."""
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


def folder_mb(path):
    path = Path(path)
    if path.is_file():
        return path.stat().st_size / 2**20
    if not path.exists():
        return 0.0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 2**20


def model_disk_mb(model_name):
    if model_name == "navec":
        from kb.embeddings import NAVEC_PATH
        return folder_mb(NAVEC_PATH)
    cache = Path(os.getenv("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    return folder_mb(cache / ("models--" + model_name.replace("/", "--")))


def libraries_mb(names):
    import importlib.util
    total = 0.0
    for name in names:
        spec = importlib.util.find_spec(name)
        if spec and spec.origin:
            total += folder_mb(Path(spec.origin).parent)
    return total


def main():
    ranker = sys.argv[1] if len(sys.argv) > 1 else "tfidf"
    service = Service(chunks(seed()), Local(), ranker)
    questions = load_questions("dev2") + load_questions("stress")

    # Первый вопрос — «холодный старт»: загрузка модели и кодирование всех разделов.
    start = time.perf_counter()
    service.ask(questions[0]["role"], questions[0]["question"])
    cold_ms = 1000 * (time.perf_counter() - start)

    times = []
    for q in questions:
        start = time.perf_counter()
        service.ask(q["role"], q["question"])
        times.append(1000 * (time.perf_counter() - start))
    times.sort()

    from kb.embeddings import MODEL_NAME
    label = ranker if ranker == "tfidf" else f"{ranker} ({MODEL_NAME})"
    print(f"Режим: {label}")
    print(f"Процессор: {platform.processor() or platform.machine()}, ядер: {os.cpu_count()}, ОС: {platform.system()} {platform.release()}")
    print(f"Первый запрос (с загрузкой модели): {cold_ms:.0f} мс")
    print(f"Обычный запрос: медиана {statistics.median(times):.1f} мс, 95% запросов быстрее {times[int(0.95 * (len(times) - 1))]:.1f} мс ({len(times)} запросов)")
    print(f"Пиковая память процесса: {peak_memory_mb():.0f} МБ")
    if ranker == "hybrid":
        print(f"Модель на диске: {model_disk_mb(MODEL_NAME):.0f} МБ")
        if MODEL_NAME != "navec":
            print(f"Библиотеки torch + transformers + sentence_transformers: {libraries_mb(['torch', 'transformers', 'sentence_transformers']):.0f} МБ")
        else:
            print(f"Библиотека navec: {libraries_mb(['navec']):.1f} МБ")


if __name__ == "__main__":
    main()