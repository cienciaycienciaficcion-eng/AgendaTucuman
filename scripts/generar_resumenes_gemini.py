#!/usr/bin/env python3
"""Genera resúmenes breves de eventos con Gemini.

Diseñado para ejecutarse en GitHub Actions después del extractor de agenda y
antes de publicar datos/agenda_eventos.json.

Características:
- Conserva siempre la descripción original.
- Reutiliza un resumen previo si la descripción no cambió.
- Solo consulta Gemini para descripciones largas.
- Si Gemini no está disponible, deja el evento publicable sin resumen nuevo.
- No envía a Gemini datos distintos de los necesarios para resumir el evento.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from collections import deque
from html import unescape
from pathlib import Path
from typing import Any

import requests

DEFAULT_MODEL = "gemini-3.5-flash-lite"
SUMMARY_VERSION = 1
MIN_DESCRIPTION_CHARS = 450
MAX_INPUT_CHARS = 12000
MAX_SUMMARY_CHARS = 420
API_TIMEOUT = 45
REQUESTS_PER_MINUTE = 10
RATE_WINDOW_SECONDS = 60.0
RATE_SAFETY_SECONDS = 0.5
REQUEST_JITTER_MIN = 0.5
REQUEST_JITTER_MAX = 1.5
MAX_RETRIES = 3
RETRY_429_SECONDS = 65.0
RETRY_5XX_BASE_SECONDS = 10.0
RETRY_MAX_SECONDS = 180.0


def clean_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def description_hash(description: str) -> str:
    normalized = re.sub(r"\s+", " ", description).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"ADVERTENCIA: no se pudo leer {path}: {exc}")
        return default


def extract_response_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    return " ".join(
        str(part.get("text", ""))
        for part in parts
        if isinstance(part, dict) and part.get("text")
    ).strip()


def normalize_summary(text: str) -> str:
    text = clean_text(text)
    text = re.sub(r"^(resumen\s*:\s*)", "", text, flags=re.I)
    text = text.strip('"“”')
    # Gemini puede devolver listas o markdown aunque se le pida texto plano.
    text = re.sub(r"^[-*•]\s*", "", text)
    if len(text) > MAX_SUMMARY_CHARS:
        cut = text[:MAX_SUMMARY_CHARS]
        # Cortar en una oración completa cuando sea posible.
        sentence = max(cut.rfind(". "), cut.rfind(".\n"))
        if sentence >= 180:
            text = cut[: sentence + 1]
        else:
            text = cut.rstrip() + "…"
    return text


def build_prompt(event: dict[str, Any], description: str) -> str:
    title = clean_text(event.get("title"))
    date_start = event.get("date_start") or ""
    date_end = event.get("date_end") or ""
    location = clean_text(event.get("location"))
    address = clean_text(event.get("address"))

    context = []
    if date_start:
        context.append(f"Fecha: {date_start}" + (f" al {date_end}" if date_end and date_end != date_start else ""))
    if location:
        context.append(f"Lugar: {location}")
    if address:
        context.append(f"Dirección: {address}")

    context_text = "\n".join(context)

    return f"""Resume en español el siguiente contenido para una aplicación móvil de eventos de Tucumán.

REGLAS:
- Escribe 2 o 3 oraciones breves, claras y naturales.
- Máximo 420 caracteres.
- Explica qué es la actividad y los datos prácticos más importantes que aparezcan en el texto.
- Conserva nombres propios, fechas, horarios, lugares, precios y requisitos relevantes cuando sean importantes.
- No inventes información ni completes datos que no estén en el texto.
- No hagas publicidad ni emitas opiniones.
- Si es una nota informativa o de servicios y no un evento, resume su contenido como información, sin presentarlo como un evento distinto.
- Devuelve únicamente el resumen, sin título, sin viñetas y sin Markdown.

TÍTULO:
{title}

DATOS ESTRUCTURADOS:
{context_text}

CONTENIDO ORIGINAL:
{description[:MAX_INPUT_CHARS]}
"""


class RateLimiter:
    """Mantiene las solicitudes por debajo del límite de RPM de Gemini."""

    def __init__(self, max_requests: int = REQUESTS_PER_MINUTE, window_seconds: float = RATE_WINDOW_SECONDS):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.timestamps: deque[float] = deque()

    def wait_for_slot(self) -> None:
        now = time.monotonic()
        while self.timestamps and now - self.timestamps[0] >= self.window_seconds:
            self.timestamps.popleft()

        if len(self.timestamps) >= self.max_requests:
            wait_seconds = self.window_seconds - (now - self.timestamps[0]) + RATE_SAFETY_SECONDS
            print(f"⏳ Límite preventivo: {self.max_requests} solicitudes/min. Esperando {wait_seconds:.1f}s...")
            time.sleep(max(wait_seconds, 0))
            self.wait_for_slot()
            return

        self.timestamps.append(time.monotonic())


def generate_summary(api_key: str, model: str, event: dict[str, Any], description: str, rate_limiter: RateLimiter) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": build_prompt(event, description)}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 180,
        },
    }

    for attempt in range(1, MAX_RETRIES + 1):
        # El rate limiter se aplica a CADA intento, incluidos los reintentos.
        rate_limiter.wait_for_slot()

        # Pequeño jitter para evitar que varias ejecuciones de Actions
        # hagan solicitudes exactamente en el mismo instante.
        jitter = random.uniform(REQUEST_JITTER_MIN, REQUEST_JITTER_MAX)
        time.sleep(jitter)

        response = requests.post(
            url,
            params={"key": api_key},
            json=payload,
            timeout=API_TIMEOUT,
        )

        if response.status_code == 429:
            if attempt < MAX_RETRIES:
                retry_after = response.headers.get("Retry-After", "").strip()
                try:
                    retry_after_seconds = float(retry_after)
                except (TypeError, ValueError):
                    retry_after_seconds = 0.0

                wait_seconds = max(RETRY_429_SECONDS, retry_after_seconds)
                wait_seconds += random.uniform(0, 5)
                wait_seconds = min(wait_seconds, RETRY_MAX_SECONDS)

                print(
                    f"⚠ Gemini respondió 429. Esperando {wait_seconds:.1f}s "
                    f"antes de reintentar ({attempt}/{MAX_RETRIES - 1})..."
                )
                time.sleep(wait_seconds)
                continue

            detail = response.text[:500].replace("\n", " ")
            raise RuntimeError(
                f"HTTP 429 después de {MAX_RETRIES} intentos: {detail}"
            )

        if response.status_code >= 500:
            if attempt < MAX_RETRIES:
                wait_seconds = RETRY_5XX_BASE_SECONDS * (2 ** (attempt - 1))
                wait_seconds += random.uniform(0, 3)
                wait_seconds = min(wait_seconds, RETRY_MAX_SECONDS)

                print(
                    f"⚠ Gemini respondió HTTP {response.status_code}. "
                    f"Esperando {wait_seconds:.1f}s antes de reintentar..."
                )
                time.sleep(wait_seconds)
                continue

            detail = response.text[:500].replace("\n", " ")
            raise RuntimeError(
                f"HTTP {response.status_code} después de {MAX_RETRIES} intentos: {detail}"
            )

        if response.status_code >= 400:
            detail = response.text[:500].replace("\n", " ")
            raise RuntimeError(f"HTTP {response.status_code}: {detail}")

        summary = normalize_summary(extract_response_text(response.json()))
        if not summary:
            raise RuntimeError("Gemini devolvió una respuesta vacía")
        return summary

    raise RuntimeError("No se pudo generar el resumen con Gemini")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--previous", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default=os.getenv("GEMINI_MODEL", DEFAULT_MODEL))
    parser.add_argument("--min-chars", type=int, default=MIN_DESCRIPTION_CHARS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    previous_path = Path(args.previous)
    output_path = Path(args.output)

    events = load_json(input_path, None)
    if not isinstance(events, list):
        print(f"ERROR: {input_path} no contiene una lista de eventos.")
        return 1

    previous = load_json(previous_path, [])
    previous_by_id = {
        str(event.get("id")): event
        for event in previous
        if isinstance(event, dict) and event.get("id")
    }

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("ADVERTENCIA: GEMINI_API_KEY no está configurada.")
        print("Se publicarán los datos sin generar resúmenes nuevos.")
        output_path.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    total = len(events)
    reused = 0
    generated = 0
    skipped = 0
    failed = 0
    rate_limiter = RateLimiter()

    print(
    f"Límite Gemini: máximo {REQUESTS_PER_MINUTE} solicitudes en "
    f"cualquier ventana de {int(RATE_WINDOW_SECONDS)} segundos "
    f"(los reintentos también cuentan)."
)
    print(f"Umbral de resumen: {args.min_chars} caracteres. Descripciones más cortas no generan summary.")

    for index, event in enumerate(events, 1):
        if not isinstance(event, dict):
            continue

        description = clean_text(event.get("description"))
        event_id = str(event.get("id", ""))
        previous_event = previous_by_id.get(event_id, {})

        # Las descripciones cortas no necesitan resumen, aunque el evento
        # tuviera uno generado en una ejecución anterior.
        if not description or len(description) < args.min_chars:
            event["summary"] = ""
            event["summary_generated"] = False
            event["summary_version"] = SUMMARY_VERSION
            event["summary_source_hash"] = description_hash(description) if description else ""
            skipped += 1
            continue

        # Reutilizar el resumen si la descripción sigue siendo idéntica.
        previous_summary = clean_text(previous_event.get("summary"))
        previous_description = clean_text(previous_event.get("description"))
        if previous_summary and previous_description and previous_description == description:
            event["summary"] = previous_summary
            event["summary_generated"] = bool(previous_event.get("summary_generated", True))
            event["summary_version"] = int(previous_event.get("summary_version", SUMMARY_VERSION))
            event["summary_source_hash"] = description_hash(description)
            reused += 1
            continue

        try:
            summary = generate_summary(api_key, args.model, event, description, rate_limiter)
            event["summary"] = summary
            event["summary_generated"] = True
            event["summary_version"] = SUMMARY_VERSION
            event["summary_source_hash"] = description_hash(description)
            generated += 1
            print(f"[{index}/{total}] ✓ {event_id}: {summary}")
        except Exception as exc:
            failed += 1
            # Si el evento tenía un resumen anterior, conservarlo como fallback.
            if previous_summary:
                event["summary"] = previous_summary
                event["summary_generated"] = bool(previous_event.get("summary_generated", True))
                event["summary_version"] = int(previous_event.get("summary_version", SUMMARY_VERSION))
                event["summary_source_hash"] = description_hash(description)
                reused += 1
                print(f"[{index}/{total}] ⚠ {event_id}: Gemini falló; se conserva el resumen anterior: {exc}")
            else:
                event["summary"] = ""
                event["summary_generated"] = False
                event["summary_version"] = SUMMARY_VERSION
                event["summary_source_hash"] = description_hash(description)
                print(f"[{index}/{total}] ⚠ {event_id}: no se generó resumen: {exc}")

    output_path.write_text(
        json.dumps(events, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("")
    print("RESÚMENES GEMINI")
    print(f"  Eventos: {total}")
    print(f"  Generados: {generated}")
    print(f"  Reutilizados: {reused}")
    print(f"  Sin resumen por descripción corta/vacía: {skipped}")
    print(f"  Fallos de generación: {failed}")
    print(f"  Modelo: {args.model}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
