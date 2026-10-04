# perf.py - prints how long each part of a page takes (in the terminal running streamlit)
# US-49: page load times are measured with these [TIMING] lines (see login.py).
import time
from contextlib import contextmanager

@contextmanager
def timed(label, warn_over_ms=None):
    """Prints '[TIMING] <label>: <n> ms'. With warn_over_ms, adds a warning when the time is over that limit."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        ms = (time.perf_counter() - t0) * 1000
        warning = f"  <-- OVER {warn_over_ms / 1000:g} s" if warn_over_ms is not None and ms > warn_over_ms else ""
        print(f"[TIMING] {label}: {ms:.0f} ms{warning}", flush=True)
