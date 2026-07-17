"""
FEATURE 4 (enterprise): lightweight, in-memory request/error counters.

Deliberately simple — no external dependency (Prometheus client, StatsD,
etc.), matching "simple in-memory or logging-based is fine". Counters
reset on process restart, which is an accepted tradeoff for a
lightweight, zero-config observability layer; anything durable belongs
in the audit_logs table (Feature 1) or a real metrics backend, not here.

Not thread-safe in the strictest sense (a `+= 1` on a dict value has a
tiny race window under multiple worker threads), but for coarse
request/error counts used for basic dashboards, that's an acceptable
tradeoff for the simplicity this feature calls for. Swap in a real
metrics backend (e.g. prometheus_client Counters, which *are*
thread-safe) if this ever needs production-grade accuracy.
"""
import threading
import time

_lock = threading.Lock()

_state = {
    "request_count": 0,
    "error_count": 0,
    "status_counts": {},   # {"200": 10, "404": 2, ...}
    "endpoint_counts": {}, # {"kb.kb_list": 5, ...}
    "started_at": time.time(),
}


def record_request(endpoint, status_code, duration_ms):
    with _lock:
        _state["request_count"] += 1
        if status_code >= 400:
            _state["error_count"] += 1
        status_key = str(status_code)
        _state["status_counts"][status_key] = _state["status_counts"].get(status_key, 0) + 1
        if endpoint:
            _state["endpoint_counts"][endpoint] = _state["endpoint_counts"].get(endpoint, 0) + 1


def get_metrics():
    with _lock:
        return {
            "request_count": _state["request_count"],
            "error_count": _state["error_count"],
            "status_counts": dict(_state["status_counts"]),
            "endpoint_counts": dict(_state["endpoint_counts"]),
            "uptime_seconds": round(time.time() - _state["started_at"], 1),
        }
