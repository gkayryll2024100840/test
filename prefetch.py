# prefetch.py - runs several slow (cached) database reads AT THE SAME TIME instead of one after another.
# The free Aiven server answers each query in ~1-2 s, so 3 queries in a row = ~5 s, but 3 at once = ~2 s.
# Only cached functions are passed in: this just fills the cache early, the page logic itself is unchanged.
# Uses at most one pooled connection per function (the pool cap of 3 still applies).
import threading
from concurrent.futures import ThreadPoolExecutor

try:
    from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
except Exception:                      # very old / very new Streamlit: just run without the context
    add_script_run_ctx = get_script_run_ctx = None


def _run(fn, ctx):
    if ctx is not None and add_script_run_ctx is not None:
        add_script_run_ctx(threading.current_thread(), ctx)
    try:
        fn()
    except Exception as e:             # never break the page: the normal call later shows the real error
        print(f"[prefetch] {getattr(fn, '__name__', fn)} failed: {e}", flush=True)


def start_prefetch(*fns):
    """Start the given functions in background threads. Returns a handle for finish_prefetch()."""
    ctx = get_script_run_ctx() if get_script_run_ctx else None
    pool = ThreadPoolExecutor(max_workers=max(1, len(fns)))
    futures = [pool.submit(_run, fn, ctx) for fn in fns]
    pool.shutdown(wait=False)
    return futures


def finish_prefetch(futures):
    """Wait until the background reads are done (they're then in the cache)."""
    for f in futures:
        f.result()


def prefetch(*fns):
    """Run the functions at the same time and wait for all of them."""
    finish_prefetch(start_prefetch(*fns))