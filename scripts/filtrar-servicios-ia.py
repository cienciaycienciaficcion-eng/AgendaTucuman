#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Filtrado incremental de Servicios con Gemini.

- Máximo 50 llamadas HTTP a Gemini por ejecución.
- Cada llamada procesa un artículo.
- Los artículos procesados quedan registrados en un estado persistente.
- Si quedan artículos pendientes, la siguiente ejecución continúa desde donde quedó.
- Los resultados seleccionados se conservan entre ejecuciones.
"""
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
API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
MAX_GEMINI_CALLS = 50
REQUEST_TIMEOUT = 60
GEMINI_RETRIES = 3
GEMINI_RETRY_BASE_SECONDS = 5
GEMINI_MIN_INTERVAL_SECONDS = 7
GEMINI_JITTER_SECONDS = 2
GEMINI_429_BACKOFF = [30, 60, 120]
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
    if not STATE.exists():
        return {"processed": {}, "selected_ids": [], "updated_at": ""}
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("estado inválido")
        data.setdefault("processed", {})
        data.setdefault("selected_ids", [])
        return data
    except Exception as exc:
        print(f"[Estado] No se pudo leer {STATE}: {exc}. Se crea uno nuevo.")
        return {"processed": {}, "selected_ids": [], "updated_at": ""}


def save_state(state):
    state["updated_at"] = now_utc().isoformat()
    STATE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def deterministic_candidates(articles):
    """Reduce candidatos sin usar IA."""
    today = datetime.now().date()
    cutoff = today - timedelta(days=90)
    result = []
    for a in articles:
        published = str(a.get("published", ""))[:10]
        recent = False
        try:
            recent = datetime.fromisoformat(published).date() >= cutoff
        except Exception:
            pass
        text = (
            f"{a.get('title','')} {a.get('description','')} "
            f"{a.get('content','')[:700]}"
        ).lower()
        temporal = bool(re.search(
            r"\b(?:hoy|mañana|esta semana|este lunes|este martes|"
            r"este miércoles|este jueves|este viernes|este sábado|"
            r"este domingo|septiembre|octubre|noviembre|diciembre|"
            r"enero|febrero|marzo|abril|mayo|junio|julio|agosto)\b",
            text,
        ))
        if recent or temporal:
            result.append(a)
    return result or articles


def ask_gemini(article):
    """Consulta Gemini para un único artículo, con reintentos ante 429/5xx."""
    prompt = f"""Eres el filtro de Servicios de Agenda Tucumán.

Selecciona si ESTA publicación representa información útil de servicios para ciudadanos de Tucumán.

INCLUIR: trámites, operativos municipales, salud pública, transporte, mercados,
campañas, turnos, vacunación, castraciones, beneficios, cronogramas, cortes,
horarios de servicios, programas sociales y actividades de utilidad pública.

EXCLUIR: eventos culturales, recitales, fiestas, cine, espectáculos y noticias
generales que no sean un servicio.

Devuelve EXCLUSIVAMENTE JSON válido:
{{"selected":true,"reason":"breve motivo"}}

o

{{"selected":false,"reason":"breve motivo"}}

PUBLICACIÓN:
Título: {article.get('title','')}
Fecha de publicación: {article.get('published','')}
Descripción: {article.get('description','')[:1200]}
Contenido: {article.get('content','')[:2500]}
"""

    last_error = None

    for attempt in range(1, GEMINI_RETRIES + 1):
        try:
            response = requests.post(
                URL,
                params={"key": API_KEY},
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0,
                        "responseMimeType": "application/json",
                    },
                },
                timeout=REQUEST_TIMEOUT,
            )

            # Retry only temporary/rate-limit/server errors.
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt < GEMINI_RETRIES:
                    if response.status_code == 429:
                        wait = GEMINI_429_BACKOFF[attempt - 1]
                    else:
                        wait = GEMINI_5XX_BACKOFF[attempt - 1]
                    wait += random.uniform(0, 5)
                    print(
                        f"[Gemini Servicios] HTTP {response.status_code} "
                        f"para {article.get('id')}; reintento {attempt + 1}/"
                        f"{GEMINI_RETRIES} en {wait:.1f}s."
                    )
                    time.sleep(wait)
                    continue

            response.raise_for_status()

            body = response.json()
            candidates = body.get("candidates") or []
            if not candidates:
                raise RuntimeError("Gemini no devolvió candidates")

            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts or "text" not in parts[0]:
                raise RuntimeError("Gemini no devolvió texto JSON")

            return extract_json(parts[0]["text"])

        except requests.HTTPError as exc:
            last_error = exc

            # 4xx other than 429 are configuration/request errors and should
            # not be retried repeatedly.
            status = exc.response.status_code if exc.response is not None else None
            if status is not None and status != 429 and not (500 <= status < 600):
                raise

            if attempt >= GEMINI_RETRIES:
                raise

        except (requests.RequestException, RuntimeError, ValueError, KeyError) as exc:
            last_error = exc
            if attempt >= GEMINI_RETRIES:
                raise

            wait = GEMINI_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
            print(
                f"[Gemini Servicios] Error temporal para {article.get('id')}: "
                f"{exc}; reintento {attempt + 1}/{GEMINI_RETRIES} en {wait}s."
            )
            time.sleep(wait)

    raise last_error or RuntimeError("Fallo desconocido consultando Gemini")


def make_event(article):
    event = dict(article)
    event["source"] = "Agenda Tucumán - Servicios"
    event["categories"] = list(dict.fromkeys([
        *(article.get("categories") or []), "Servicios"
    ]))
    event["date_start"] = article.get("published") or ""
    event["date_end"] = article.get("published") or ""
    event["time_start"] = ""
    event["time_end"] = ""
    event["start_datetime"] = (
        (article.get("published") or "") + "T00:00:00-03:00"
        if article.get("published") else ""
    )
    event["end_datetime"] = ""
    event["location"] = ""
    event["address"] = ""
    event["city"] = "Tucumán"
    event["is_free"] = False
    event["price"] = None
    event["currency"] = ""
    event["tags"] = article.get("tags") or []
    event["map_search_url"] = ""
    event["registration_urls"] = []
    event["external_urls"] = article.get("links") or []
    event["occurrences"] = []
    return event


def write_output(articles, selected_ids, candidates_count, processed_this_run):
    by_id = {str(a.get("id")): a for a in articles}
    events = []
    valid_selected = []
    for sid in selected_ids:
        article = by_id.get(str(sid))
        if article:
            events.append(make_event(article))
            valid_selected.append(str(sid))

    events.sort(key=lambda x: (
        x.get("date_start") or "9999-99-99", x.get("title") or ""
    ))

    output = {
        "schema_version": "1.0",
        "generated_at": now_utc().isoformat(),
        "source": "Gemini incremental filter",
        "raw_count": len(articles),
        "candidate_count": candidates_count,
        "processed_this_run": processed_this_run,
        "count": len(events),
        "events": events,
    }
    OUT.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return valid_selected


def main():
    if not RAW.exists():
        raise SystemExit(f"No existe {RAW}")

    raw = json.loads(RAW.read_text(encoding="utf-8"))
    articles = raw.get("articles", []) if isinstance(raw, dict) else raw
    if not isinstance(articles, list):
        raise SystemExit("servicios_raw.json no contiene una lista de artículos")

    state = load_state()
    by_id = {str(a.get("id")): a for a in articles if a.get("id") is not None}

    # Si el extractor reemplazó completamente el universo de artículos,
    # eliminamos del estado los IDs que ya no existen para no arrastrarlos.
    state["processed"] = {
        str(k): v for k, v in state.get("processed", {}).items() if str(k) in by_id
    }
    state["selected_ids"] = [
        str(x) for x in state.get("selected_ids", []) if str(x) in by_id
    ]

    candidates = deterministic_candidates(articles)
    candidate_ids = [str(a.get("id")) for a in candidates if a.get("id") is not None]

    pending = [
        a for a in candidates
        if str(a.get("id")) not in state["processed"]
    ]

    if not pending:
        print(
            f"[Gemini Servicios] No hay pendientes. "
            f"Procesados: {len(state['processed'])}; "
            f"publicados: {len(state['selected_ids'])}."
        )
        state["selected_ids"] = write_output(
            articles, state["selected_ids"], len(candidate_ids), 0
        )
        save_state(state)
        return

    if not API_KEY:
        raise SystemExit("GEMINI_API_KEY no está configurada")

    print(
        f"[Gemini Servicios] Modelo: {MODEL} | "
        f"API key: configurada | límite de artículos: {MAX_GEMINI_CALLS}"
    )

    batch = pending[:MAX_GEMINI_CALLS]
    print(
        f"[Gemini Servicios] Pendientes: {len(pending)}. "
        f"Esta corrida procesará como máximo {len(batch)} (límite {MAX_GEMINI_CALLS})."
    )

    calls = 0
    selected_this_run = 0

    for index, article in enumerate(batch, start=1):
        # Espaciado individual para evitar ráfagas de solicitudes.
        # No esperamos antes del primer artículo.
        if index > 1:
            wait = GEMINI_MIN_INTERVAL_SECONDS + random.uniform(
                0, GEMINI_JITTER_SECONDS
            )
            print(
                f"[Gemini Servicios] Esperando {wait:.1f}s antes del artículo "
                f"{index}/{len(batch)}..."
            )
            time.sleep(wait)

        sid = str(article.get("id"))
        calls += 1
        try:
            result = ask_gemini(article)
            selected = bool(result.get("selected", False))
            state["processed"][sid] = {
                "selected": selected,
                "processed_at": now_utc().isoformat(),
                "reason": str(result.get("reason", ""))[:300],
            }
            if selected and sid not in state["selected_ids"]:
                state["selected_ids"].append(sid)
                selected_this_run += 1
            print(
                f"[Gemini Servicios] {calls}/{len(batch)} "
                f"ID={sid} selected={selected}"
            )
        except requests.HTTPError as exc:
            # No marcar como procesado: se reintentará en la siguiente corrida.
            print(f"[Gemini Servicios] HTTP error para {sid}: {exc}")
            continue
        except Exception as exc:
            # Tampoco se marca como procesado si la llamada no pudo completarse.
            print(f"[Gemini Servicios] Error para {sid}: {exc}")
            continue

    state["selected_ids"] = write_output(
        articles,
        state["selected_ids"],
        len(candidate_ids),
        calls,
    )
    save_state(state)

    remaining = sum(
        1 for a in candidates if str(a.get("id")) not in state["processed"]
    )
    print(
        f"[Gemini Servicios] Fin de corrida: llamadas={calls}, "
        f"nuevos seleccionados={selected_this_run}, pendientes={remaining}, "
        f"publicados={len(state['selected_ids'])}."
    )


if __name__ == "__main__":
    main()
