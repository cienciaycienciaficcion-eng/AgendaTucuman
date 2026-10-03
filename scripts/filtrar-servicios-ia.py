#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Filtra una vez al día los servicios extraídos usando Gemini.

El extractor ya descargó TODO. Gemini no navega ni extrae páginas: recibe un
listado compacto de artículos y decide cuáles son servicios útiles, actuales
o próximos para la app. La salida conserva la data completa de cada artículo.
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

RAW = Path("datos/servicios_raw.json")
OUT = Path("datos/servicios_tucuman.json")
API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"


def extract_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else {}


def deterministic_candidates(articles):
    # Reducimos el tamaño del prompt sin usar IA: títulos publicados recientemente
    # o artículos con indicios temporales en el título/contenido.
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
        text = f"{a.get('title','')} {a.get('description','')} {a.get('content','')[:500]}".lower()
        temporal = bool(re.search(r"\b(?:hoy|mañana|esta semana|este lunes|este martes|este miércoles|este jueves|este viernes|este sábado|este domingo|septiembre|octubre|noviembre|diciembre|enero|febrero|marzo|abril|mayo|junio|julio|agosto)\b", text))
        if recent or temporal:
            result.append(a)
    return result or articles


def main():
    if not RAW.exists():
        raise SystemExit(f"No existe {RAW}")
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    articles = raw.get("articles", []) if isinstance(raw, dict) else raw
    if not articles:
        OUT.write_text(json.dumps({"schema_version":"1.0","generated_at":datetime.now(timezone.utc).isoformat(),"source":"Gemini","count":0,"events":[]}, ensure_ascii=False, indent=2), encoding="utf-8")
        return
    if not API_KEY:
        raise SystemExit("GEMINI_API_KEY no está configurada")

    candidates = deterministic_candidates(articles)
    compact = []
    for a in candidates:
        compact.append({
            "id": a.get("id"),
            "title": a.get("title"),
            "published": a.get("published"),
            "description": a.get("description", "")[:900],
            "content": a.get("content", "")[:1400],
        })

    prompt = f"""Eres el filtro diario de Servicios de Agenda Tucumán.
Fecha actual: {datetime.now().date().isoformat()}

Selecciona SOLO publicaciones que representen información útil de servicios para ciudadanos de Tucumán: trámites, operativos municipales, salud pública, transporte, mercados, campañas, turnos, vacunación, castraciones, beneficios, cronogramas, cortes/horarios de servicios, programas sociales y actividades de utilidad pública.

EXCLUYE eventos culturales, recitales, fiestas, cine, espectáculos y noticias generales que no sean un servicio.

Devuelve exclusivamente JSON con esta forma:
{{"selected_ids":["id1","id2"]}}

No cambies IDs. No inventes IDs. Puedes seleccionar cero o más.

PUBLICACIONES:
{json.dumps(compact, ensure_ascii=False)}"""

    response = requests.post(
        URL,
        params={"key": API_KEY},
        headers={"Content-Type": "application/json"},
        json={"contents":[{"parts":[{"text":prompt}]}], "generationConfig":{"temperature":0,"responseMimeType":"application/json"}},
        timeout=90,
    )
    response.raise_for_status()
    body = response.json()
    text = body["candidates"][0]["content"]["parts"][0]["text"]
    result = extract_json(text)
    selected = set(str(x) for x in result.get("selected_ids", []) if isinstance(x, (str,int)))

    by_id = {str(a.get("id")): a for a in articles}
    events = []
    for sid in selected:
        a = by_id.get(sid)
        if not a:
            continue
        # La app usa el mismo modelo de evento; conservamos TODO el contenido.
        event = dict(a)
        event["source"] = "Agenda Tucumán - Servicios"
        event["categories"] = list(dict.fromkeys([*(a.get("categories") or []), "Servicios"]))
        event["date_start"] = a.get("published") or ""
        event["date_end"] = a.get("published") or ""
        event["time_start"] = ""
        event["time_end"] = ""
        event["start_datetime"] = (a.get("published") or "") + "T00:00:00-03:00" if a.get("published") else ""
        event["end_datetime"] = ""
        event["location"] = ""
        event["address"] = ""
        event["city"] = "Tucumán"
        event["is_free"] = False
        event["price"] = None
        event["currency"] = ""
        event["tags"] = a.get("tags") or []
        event["map_search_url"] = ""
        event["registration_urls"] = []
        event["external_urls"] = a.get("links") or []
        event["occurrences"] = []
        events.append(event)

    events.sort(key=lambda x: (x.get("date_start") or "9999-99-99", x.get("title") or ""))
    output = {
        "schema_version":"1.0",
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "source":"Gemini daily filter",
        "raw_count":len(articles),
        "candidate_count":len(candidates),
        "count":len(events),
        "events":events,
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Servicios filtrados: {len(events)} de {len(articles)} artículos")


if __name__ == "__main__":
    main()
