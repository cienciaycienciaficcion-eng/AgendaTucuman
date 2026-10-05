#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Filtrado incremental de Servicios con Gemini/Groq.

- Los artículos descargados desde la web se filtran primero sin IA.
- Cada artículo guarda un hash de contenido en el estado persistente.
- Un artículo sin cambios NO vuelve a consumir Gemini/Groq.
- Si cambia título, fecha, descripción, contenido, URL o enlaces, se vuelve a analizar.
- Gemini se usa primero mientras tenga cuota; Groq es fallback automático.
- Los resultados seleccionados se conservan entre ejecuciones.
"""
import hashlib
import json
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

RAW = Path("datos/servicios_raw.json")
OUT = Path("datos/servicios_tucuman.json")
STATE = Path("datos/servicios_gemini_state.json")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
MAX_GEMINI_CALLS_PER_RUN = 5
MAX_GEMINI_CALLS_PER_DAY = 20
MAX_GROQ_CALLS_PER_RUN = 5
MAX_GROQ_CALLS_PER_DAY = 30

# Fallback automático: si Gemini falla, se intenta Groq.
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_REQUEST_TIMEOUT = 60
REQUEST_TIMEOUT = 60
GEMINI_RETRIES = 2
GEMINI_RETRY_BASE_SECONDS = 5
GEMINI_MIN_INTERVAL_SECONDS = 13
GEMINI_JITTER_SECONDS = 2
GEMINI_5XX_BACKOFF = [15, 30, 60]


def now_utc():
    return datetime.now(timezone.utc)


def extract_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else {}


def load_state():
    default_usage = {
        "date": now_utc().date().isoformat(),
        "calls": 0,
    }
    if not STATE.exists():
        return {
            "processed": {},
            "selected_ids": [],
            "updated_at": "",
            "gemini_usage": dict(default_usage),
            "groq_usage": dict(default_usage),
        }
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("estado inválido")
        data.setdefault("processed", {})
        data.setdefault("selected_ids", [])
        data.setdefault("gemini_usage", dict(default_usage))
        data.setdefault("groq_usage", dict(default_usage))
        return data
    except Exception as exc:
        print(f"[Estado] No se pudo leer {STATE}: {exc}. Se crea uno nuevo.")
        return {
            "processed": {},
            "selected_ids": [],
            "updated_at": "",
            "gemini_usage": dict(default_usage),
            "groq_usage": dict(default_usage),
        }


def save_state(state):
    state["updated_at"] = now_utc().isoformat()
    STATE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
