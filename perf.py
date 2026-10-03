# perf.py - prints how long each part of a page takes (in the terminal running streamlit)
import time
from contextlib import contextmanager

@contextmanager
def timed(label):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        print(f"[TIMING] {label}: {(time.perf_counter() - t0) * 1000:.0f} ms")