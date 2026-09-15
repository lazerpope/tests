"""Periodic status messages, including when a server sends no data."""
from contextlib import contextmanager
import threading
import time

INTERVAL = 5

@contextmanager
def progress(label):
    start = time.monotonic()
    state = {"last": start, "detail": "waiting for response"}
    stop = threading.Event()
    def update(detail):
        state.update(last=time.monotonic(), detail=detail)
    def pulse():
        while not stop.wait(INTERVAL):
            now = time.monotonic()
            idle = now - state["last"]
            print(f"  [{label}] elapsed {now-start:.0f}s | {state['detail']} | last update {idle:.0f}s ago"
                  + (" | no recent data; server may be loading or stalled" if idle >= 30 else ""), flush=True)
    print(f"  [{label}] started", flush=True)
    thread = threading.Thread(target=pulse, daemon=True)
    thread.start()
    try:
        yield update
    finally:
        stop.set()
        thread.join()
        print(f"  [{label}] ended after {time.monotonic()-start:.1f}s", flush=True)
