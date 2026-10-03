#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agenda Tucumán - extractor auxiliar con IA para SERVICIOS.

No reemplaza agenda_mec.py. Importa el extractor existente y sustituye
solamente la interpretación de fechas de /category/servicios/.

Uso:
    python agenda_mec_ia.py --start-year ... --start-month ... \
        --months 12 --lookback-months 2 --delay 0.15 --out .tmp/agenda

Requiere:
    GEMINI_API_KEY

La IA se consulta solamente cuando el parser determinista no encuentra
una fecha. La respuesta de Gemini se valida estrictamente antes de usarla.
Las consultas se limitan a 10 por bloque de 61 segundos. Los errores 429 y los timeouts no bloquean el workflow.
"""
import os
import json
import re
from datetime import datetime, date
from urllib.parse import quote
import time

import requests

import agenda_mec as base


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    + GEMINI_MODEL
    + ":generateContent"
)

# Límite de la API de Gemini:
# máximo 10 consultas por minuto. Dejamos 61 segundos entre bloques
# para evitar superar el límite de 10 RPM.
GEMINI_BATCH_SIZE = 10
GEMINI_BATCH_WAIT = 61
GEMINI_MAX_RETRIES = 2
GEMINI_RETRY_WAIT = 10
GEMINI_REQUEST_TIMEOUT = 20
GEMINI_TOTAL_TIMEOUT = 45

_gemini_queries_in_batch = 0
_gemini_batch_started_at = None


def _wait_for_gemini_rate_limit():
    """Aplica un límite conservador de 10 consultas por bloque de 61 s."""
    global _gemini_queries_in_batch, _gemini_batch_started_at

    now = time.monotonic()

    if _gemini_batch_started_at is None:
        _gemini_batch_started_at = now

    if _gemini_queries_in_batch >= GEMINI_BATCH_SIZE:
        elapsed = now - _gemini_batch_started_at
        wait = max(0, GEMINI_BATCH_WAIT - elapsed)

        if wait > 0:
            print(
                f"[Gemini Servicios] Límite de "
                f"{GEMINI_BATCH_SIZE} consultas alcanzado. "
                f"Esperando {wait:.0f} segundos..."
            )
            time.sleep(wait)

        _gemini_queries_in_batch = 0
        _gemini_batch_started_at = time.monotonic()

    _gemini_queries_in_batch += 1
    print(
        f"[Gemini Servicios] Consulta "
        f"{_gemini_queries_in_batch}/{GEMINI_BATCH_SIZE}"
    )


def _today():
    return datetime.now(base.ARGENTINA_TZ).date().isoformat()


def _valid_iso(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False
