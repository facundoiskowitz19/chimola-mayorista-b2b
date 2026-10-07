"""Doc Firestore `config/home` (homes, banners y menú del sitio): lectura cacheada 60 s e invalidación."""
from __future__ import annotations

import threading
import time

import db

_cache: dict = {"data": None, "ts": 0.0}
_lock = threading.Lock()
_TTL = 60


def _ref():
    return db.client().collection(db.COL_CONFIG).document("home")


def invalidar() -> None:
    with _lock:
        _cache.update(data=None, ts=0.0)


def get_home_raw() -> dict:
    """Doc `config/home` tal cual está (sin defaults). Cache 60 s."""
    with _lock:
        if _cache["data"] is not None and time.time() - _cache["ts"] < _TTL:
            return _cache["data"]
    snap = _ref().get()
    data = (snap.to_dict() or {}) if snap.exists else {}
    with _lock:
        _cache.update(data=data, ts=time.time())
    return data
