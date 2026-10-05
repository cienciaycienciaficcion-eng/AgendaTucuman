#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Filtrado incremental de Servicios con Gemini/Groq.

- Los artículos descargados desde la web se filtran primero sin IA.
- Cada artículo guarda un hash de contenido en el estado persistente.
- Un artículo sin cambios no vuelve a consumir Gemini/Groq.
- Si cambia contenido relevante, se vuelve a analizar.
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
    )


def provider_usage_today(state, provider):
    today = now_utc().date().isoformat()
    key = f"{provider}_usage"
    usage = state.setdefault(key, {})
    if usage.get("date") != today:
        usage.clear()
        usage.update({"date": today, "calls": 0})
    usage.setdefault("calls", 0)
    return usage


def usage_today(state):
    return provider_usage_today(state, "gemini")


def register_gemini_call(state):
    usage = provider_usage_today(state, "gemini")
    if usage["calls"] >= MAX_GEMINI_CALLS_PER_DAY:
        raise RuntimeError("Se alcanzó el límite diario de Gemini (20 llamadas).")
    usage["calls"] += 1
    save_state(state)
    print(
        f"[Gemini Servicios] Llamada contabilizada: "
        f"{usage['calls']}/{MAX_GEMINI_CALLS_PER_DAY} hoy."
    )


def register_groq_call(state):
    usage = provider_usage_today(state, "groq")
    if usage["calls"] >= MAX_GROQ_CALLS_PER_DAY:
        raise RuntimeError("Se alcanzó el límite diario de Groq (30 llamadas).")
    usage["calls"] += 1
    save_state(state)
    print(
        f"[Groq Servicios] Llamada contabilizada: "
        f"{usage['calls']}/{MAX_GROQ_CALLS_PER_DAY} hoy."
    )


def article_content_hash(article):
    """Hash estable para detectar publicaciones nuevas o modificadas."""
    payload = {
        "id": str(article.get("id", "")),
        "title": str(article.get("title", "")),
        "published": str(article.get("published", "")),
        "description": str(article.get("description", "")),
        "excerpt": str(article.get("excerpt", "")),
        "content": str(article.get("content", "")),
        "url": str(article.get("url", "")),
        "links": article.get("links") or [],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def prepare_incremental_state(state, articles):
    """Identifica IDs nuevos/modificados sin llamar a ninguna IA."""
    by_id = {
        str(a.get("id")): a
        for a in articles
        if a.get("id") is not None
    }

    state["processed"] = {
        str(k): v
        for k, v in state.get("processed", {}).items()
        if str(k) in by_id
    }
    state["selected_ids"] = [
        str(x)
        for x in state.get("selected_ids", [])
        if str(x) in by_id
    ]

    new_ids = []
    modified_ids = []

    for sid, article in by_id.items():
        current_hash = article_content_hash(article)
        previous = state["processed"].get(sid)

        if not previous:
            new_ids.append(sid)
            continue

        previous_hash = str(previous.get("content_hash", "")).strip()

        # Estados antiguos sin hash no se reprocesan masivamente.
        if not previous_hash:
            continue

        if previous_hash != current_hash:
            modified_ids.append(sid)

    return by_id, set(new_ids), set(modified_ids)


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



def ask_groq(article, state):
    """Usa Groq como fallback para clasificar un servicio."""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY no está configurada.")

    register_groq_call(state)

    title = str(article.get("title", "")).strip()
    description = str(
        article.get("content")
        or article.get("description")
        or article.get("excerpt")
        or ""
    ).strip()
    url = str(article.get("url", "")).strip()

    prompt = f"""
Analiza este artículo de Servicios de Agenda Tucumán.

Título:
{title}

Contenido:
{description[:12000]}

URL:
{url}

Devuelve SOLO JSON válido:
{{
  "include": true,
  "summary": "resumen breve en español",
  "category": "categoría",
  "reason": "motivo breve"
}}

Reglas:
- include=true solo si corresponde realmente a un servicio útil para ciudadanos.
- summary debe ser breve, claro y factual.
- No inventes datos.
- Si no corresponde, usa include=false.
""".strip()

    response = requests.post(
        GROQ_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": GROQ_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "Clasifica contenidos de Agenda Tucumán. Responde únicamente JSON válido."
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 300,
            "response_format": {"type": "json_object"},
        },
        timeout=GROQ_REQUEST_TIMEOUT,
    )

    if response.status_code >= 400:
        raise requests.HTTPError(
            f"Groq HTTP {response.status_code}: {response.text[:500]}",
            response=response,
        )

    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Groq no devolvió choices.")

    content = choices[0].get("message", {}).get("content", "")
    if not content:
        raise RuntimeError("Groq devolvió una respuesta vacía.")

    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.I)
        content = re.sub(r"\s*```$", "", content)

    result = extract_json(content)
    if not isinstance(result, dict) or not result:
        raise RuntimeError("La respuesta de Groq no contiene un objeto JSON válido.")
    return result


def ask_gemini(article, state):
    """Consulta Gemini para un único artículo; 429 pasa inmediatamente a Groq y 5xx puede reintentarse."""
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

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY no está configurada.")

    last_error = None

    for attempt in range(1, GEMINI_RETRIES + 1):
        try:
            register_gemini_call(state)
            response = requests.post(
                URL,
                params={"key": api_key},
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

            # 429 significa cuota/rate limit: abandonar Gemini inmediatamente
            # y dejar que el caller pruebe Groq. No desperdiciamos reintentos.
            if response.status_code == 429:
                print(
                    f"[Gemini Servicios] HTTP 429 para {article.get('id')}; "
                    "se activa Groq sin reintentar Gemini."
                )
                response.raise_for_status()

            # 5xx sí puede ser transitorio: permitir un reintento.
            if 500 <= response.status_code < 600:
                if attempt < GEMINI_RETRIES:
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

            # 429 = cuota/rate limit. No se reintenta Gemini: el caller
            # desactiva Gemini para esta ejecución y pasa inmediatamente a Groq.
            if status == 429:
                raise

            # Otros 4xx no son transitorios.
            if status is not None and not (500 <= status < 600):
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

    # 1. Detectar nuevos/modificados antes de usar IA.
    by_id, new_ids, modified_ids = prepare_incremental_state(
        state, articles
    )

    unchanged_count = max(
        0,
        len(articles) - len(new_ids) - len(modified_ids),
    )

    print(
        f"[Estado Servicios] Descargados: {len(articles)} | "
        f"Nuevos: {len(new_ids)} | "
        f"Modificados: {len(modified_ids)} | "
        f"Sin cambios: {unchanged_count}"
    )

    # 2. Filtro determinístico, sin IA.
    candidates = deterministic_candidates(articles)
    candidate_ids = {
        str(a.get("id"))
        for a in candidates
        if a.get("id") is not None
    }

    # 3. Marcar nuevos artículos descartados por el filtro previo.
    for sid in new_ids - candidate_ids:
        article = by_id.get(sid)
        if article:
            state["processed"][sid] = {
                "selected": False,
                "processed_at": now_utc().isoformat(),
                "content_hash": article_content_hash(article),
                "provider": "deterministic-filter",
                "reason": "Descartado por filtro previo sin IA.",
            }

    # 4. Los modificados que ya no son candidatos se actualizan sin IA.
    for sid in modified_ids - candidate_ids:
        article = by_id.get(sid)
        if article:
            previous = state["processed"].get(sid, {})
            state["processed"][sid] = {
                **previous,
                "selected": False,
                "processed_at": now_utc().isoformat(),
                "content_hash": article_content_hash(article),
                "provider": "deterministic-filter",
                "reason": "Modificado pero descartado por filtro previo sin IA.",
            }
            if sid in state["selected_ids"]:
                state["selected_ids"].remove(sid)

    # 5. Solo IA para nuevos/modificados que sobrevivieron al filtro.
    pending = [
        a
        for a in candidates
        if str(a.get("id")) in (new_ids | modified_ids)
    ]

    if not pending:
        print("[IA Servicios] No hay artículos nuevos o modificados para IA.")
        state["selected_ids"] = write_output(
            articles,
            state["selected_ids"],
            len(candidate_ids),
            0,
        )
        save_state(state)
        return

    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
    groq_api_key = os.getenv("GROQ_API_KEY", "").strip()

    if not gemini_api_key and not groq_api_key:
        raise SystemExit(
            "No está configurada ninguna API: "
            "se necesita GEMINI_API_KEY o GROQ_API_KEY."
        )

    print(
        f"[IA Servicios] Gemini: "
        f"{'configurada' if gemini_api_key else 'NO configurada'} "
        f"(modelo {MODEL}); "
        f"Groq: "
        f"{'configurada' if groq_api_key else 'NO configurada'} "
        f"(modelo {GROQ_MODEL})."
    )

    gemini_usage = usage_today(state)
    gemini_remaining = max(
        0,
        MAX_GEMINI_CALLS_PER_DAY - gemini_usage["calls"],
    )

    groq_usage = provider_usage_today(state, "groq")
    groq_remaining = max(
        0,
        MAX_GROQ_CALLS_PER_DAY - groq_usage["calls"],
    )

    # Máximo por ejecución: 5 artículos. Gemini se usa primero.
    run_budget = min(
        len(pending),
        MAX_GEMINI_CALLS_PER_RUN,
    )

    # Si Gemini no tiene cuota, Groq toma directamente el presupuesto.
    if not gemini_api_key or gemini_remaining <= 0:
        run_budget = min(
            len(pending),
            MAX_GROQ_CALLS_PER_RUN,
        )

    if run_budget <= 0:
        print("[IA Servicios] No hay cuota disponible para esta corrida.")
        state["selected_ids"] = write_output(
            articles,
            state["selected_ids"],
            len(candidate_ids),
            0,
        )
        save_state(state)
        return

    print(
        f"[IA Servicios] Pendientes IA: {len(pending)} | "
        f"Gemini restante: {gemini_remaining} | "
        f"Groq restante: {groq_remaining} | "
        f"Máximo esta corrida: {run_budget}"
    )

    processed_this_run = 0
    selected_this_run = 0
    gemini_available = bool(
        gemini_api_key and gemini_remaining > 0
    )

    for index, article in enumerate(pending[:run_budget], start=1):
        if index > 1:
            wait = GEMINI_MIN_INTERVAL_SECONDS + random.uniform(
                0,
                GEMINI_JITTER_SECONDS,
            )
            print(
                f"[IA Servicios] Esperando {wait:.1f}s antes del artículo "
                f"{index}/{run_budget}..."
            )
            time.sleep(wait)

        sid = str(article.get("id"))
        result = None
        provider = None

        try:
            if gemini_available:
                try:
                    result = ask_gemini(article, state)
                    provider = "gemini"
                except Exception as gemini_error:
                    print(
                        f"[Gemini Servicios] Falló Gemini: {gemini_error}"
                    )
                    # Cualquier fallo de Gemini hace que Groq tome el relevo
                    # para esta corrida. Un 429 desactiva Gemini especialmente.
                    gemini_available = False

                    if isinstance(gemini_error, requests.HTTPError):
                        status = (
                            gemini_error.response.status_code
                            if gemini_error.response is not None
                            else None
                        )
                        if status == 429:
                            print(
                                "[Gemini Servicios] 429: cuota/rate limit. "
                                "Se pasa inmediatamente a Groq."
                            )
                    else:
                        print(
                            "[Gemini Servicios] Error de Gemini. "
                            "Se pasa inmediatamente a Groq."
                        )

            if result is None:
                if not groq_api_key:
                    raise RuntimeError(
                        "Gemini no disponible y GROQ_API_KEY no está configurada."
                    )

                groq_usage = provider_usage_today(state, "groq")
                if groq_usage["calls"] >= MAX_GROQ_CALLS_PER_DAY:
                    raise RuntimeError(
                        "Gemini no disponible y Groq también alcanzó "
                        "su límite diario."
                    )

                print("[IA Servicios] Usando Groq como fallback.")
                result = ask_groq(article, state)
                provider = "groq"
                print(
                    f"[Groq Servicios] OK: {article.get('title', '')}"
                )

            if not isinstance(result, dict):
                raise RuntimeError("La IA no devolvió un objeto JSON válido.")

            selected = bool(
                result.get(
                    "selected",
                    result.get("include", False),
                )
            )

            state["processed"][sid] = {
                "selected": selected,
                "processed_at": now_utc().isoformat(),
                "content_hash": article_content_hash(article),
                "provider": provider,
                "reason": str(result.get("reason", ""))[:300],
            }

            if selected:
                if sid not in state["selected_ids"]:
                    state["selected_ids"].append(sid)
                    selected_this_run += 1
            elif sid in state["selected_ids"]:
                state["selected_ids"].remove(sid)

            processed_this_run += 1

            print(
                f"[IA Servicios] {index}/{run_budget} "
                f"ID={sid} provider={provider} selected={selected}"
            )

        except requests.HTTPError as exc:
            print(f"[IA Servicios] HTTP error para {sid}: {exc}")
        except Exception as exc:
            print(f"[IA Servicios] Error para {sid}: {exc}")

    state["selected_ids"] = write_output(
        articles,
        state["selected_ids"],
        len(candidate_ids),
        processed_this_run,
    )
    save_state(state)

    remaining = sum(
        1
        for a in candidates
        if str(a.get("id")) not in state["processed"]
    )

    print(
        f"[IA Servicios] Fin de corrida: "
        f"procesados={processed_this_run}, "
        f"nuevos seleccionados={selected_this_run}, "
        f"pendientes={remaining}, "
        f"publicados={len(state['selected_ids'])}."
    )


if __name__ == "__main__":
    main()
