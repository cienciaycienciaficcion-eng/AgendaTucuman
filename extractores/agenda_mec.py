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
"""
import os
import json
import re
from datetime import datetime, date
from urllib.parse import quote

import requests

import agenda_mec as base


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    + GEMINI_MODEL
    + ":generateContent"
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


def _extract_json(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}


def _ask_gemini(title, content, reference_date):
    if not GEMINI_API_KEY:
        return {}

    # Limitar tamaño para evitar mandar basura HTML o textos enormes.
    text = (content or "").strip()
    if len(text) > 12000:
        text = text[:12000]

    prompt = f"""
Eres el analizador temporal de Agenda Tucumán.

Tu tarea es determinar la VIGENCIA temporal de una publicación de la
categoría "Servicios". Debes usar únicamente las pistas temporales que
aparecen en el título y texto proporcionados.

Fecha de referencia actual: {reference_date}

Título:
{title}

Texto:
{text}

Reglas:
- No inventes fechas.
- Si aparece una fecha sin año, usa el año que corresponda a la fecha
  de referencia, salvo que el propio texto indique otro año.
- "hasta el 15 de octubre" => date_end 15 de octubre.
- "del 5 al 20 de octubre" => inicio 5, fin 20.
- "desde el 5 de octubre" => inicio 5, fin vacío.
- "durante octubre" => inicio 1 de octubre y fin 31 de octubre.
- "todo octubre" tiene el mismo significado.
- Si dice "todos los sábados de octubre", representa el período de octubre:
  inicio 1 de octubre y fin 31 de octubre. No inventes ocurrencias individuales.
- "permanente", "todo el año", "de lunes a viernes" sin un período concreto
  puede ser un servicio permanente: type="permanent".
- Si el texto sólo habla de una fecha de publicación y no de vigencia,
  no la uses como fecha del servicio.
- Si hay una fecha pasada pero el texto deja claro que el servicio continúa,
  usa la vigencia actual.
- Si no existe ninguna pista temporal suficiente, type="unknown".
- La evidencia debe ser una frase breve copiada del texto, no una explicación.

Devuelve ÚNICAMENTE JSON válido con este esquema:
{{
  "type": "range|start|permanent|unknown",
  "date_start": "YYYY-MM-DD o vacío",
  "date_end": "YYYY-MM-DD o vacío",
  "confidence": 0.0,
  "evidence": "frase breve"
}}
"""

    try:
        r = requests.post(
            GEMINI_URL,
            params={"key": GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0,
                    "responseMimeType": "application/json",
                },
            },
            timeout=35,
        )
        if r.status_code != 200:
            print(f"[Gemini Servicios] HTTP {r.status_code}: {r.text[:300]}")
            return {}

        obj = r.json()
        parts = (
            obj.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [])
        )
        raw = "\n".join(
            p.get("text", "") for p in parts if isinstance(p, dict)
        )
        return _extract_json(raw)
    except Exception as exc:
        print(f"[Gemini Servicios] error: {exc}")
        return {}


def parse_wp_service_date_ia(title, content, default_year, ai_result=None):
    # Primero se conserva TODO el comportamiento existente.
    a, b, source, score = base.parse_wp_service_date(
        title, content, default_year
    )
    if a:
        return a, b or a, source, score

    if not GEMINI_API_KEY:
        return "", "", "", 0

    result = ai_result if ai_result is not None else _ask_gemini(title, content, _today())
    if not result:
        return "", "", "", 0

    kind = str(result.get("type", "")).lower().strip()
    start = str(result.get("date_start", "") or "").strip()
    end = str(result.get("date_end", "") or "").strip()

    if start and not _valid_iso(start):
        start = ""
    if end and not _valid_iso(end):
        end = ""

    if kind == "range" and start and end:
        if end < start:
            return "", "", "", 0
        score = float(result.get("confidence", 0) or 0)
        score = max(0.60, min(0.92, score))
        return start, end, "services_gemini_range", score

    if kind == "start" and start:
        score = float(result.get("confidence", 0) or 0)
        score = max(0.60, min(0.88, score))
        # Sin fecha final: se considera vigente desde el inicio.
        return start, start, "services_gemini_start", score

    # Los servicios permanentes NO se convierten en eventos con una fecha
    # artificial. Se dejan fuera en esta primera prueba para no alterar
    # el contrato de la APK. Los medimos en el informe.
    return "", "", "", 0


def extract_services_ia(session, delay, year, max_pages=12):
    """
    Copia de la rutina de servicios existente, pero con el parser IA.
    Mantiene exactamente el mismo esquema de salida.
    """
    events = []
    errors = []
    category_url = base.BASE + "/wp-json/wp/v2/categories"
    posts_url = base.BASE + "/wp-json/wp/v2/posts"

    try:
        r = session.get(
            category_url,
            params={"slug": "servicios", "per_page": 10},
            timeout=25,
        )
        r.raise_for_status()
        cats = r.json()
        category_id = next(
            (c.get("id") for c in cats if c.get("slug") == "servicios"),
            None,
        )
        if not category_id:
            return events, [{
                "stage": "services_category",
                "error": "No se encontró la categoría servicios",
            }]
    except Exception as exc:
        return events, [{
            "stage": "services_category",
            "error": repr(exc),
        }]

    ia_attempts = 0
    ia_success = 0
    ia_permanent = 0

    for page in range(1, max_pages + 1):
        try:
            r = session.get(
                posts_url,
                params={
                    "categories": category_id,
                    "per_page": 100,
                    "page": page,
                    "_embed": 1,
                },
                timeout=25,
            )
            if r.status_code == 400:
                break
            r.raise_for_status()
            posts = r.json()
            if not posts:
                break
        except Exception as exc:
            errors.append({
                "stage": "services_posts",
                "page": page,
                "error": repr(exc),
            })
            break

        for post in posts:
            try:
                post_id = post.get("id")
                title = base.clean_text(
                    (post.get("title") or {}).get("rendered", "")
                )
                content_html = (
                    (post.get("content") or {}).get("rendered", "") or ""
                )
                content_text = base.strip_html(content_html)
                url = post.get("link") or ""

                published_year = year
                published_at = post.get("date") or post.get("modified") or ""
                published_match = re.match(r"^(\d{4})-", str(published_at))
                if published_match:
                    published_year = int(published_match.group(1))

                # Parser normal primero.
                date_start, date_end, date_source, date_score = (
                    base.parse_wp_service_date(
                        title, content_text, published_year
                    )
                )

                if not date_start:
                    ia_attempts += 1
                    result = _ask_gemini(title, content_text, _today())
                    kind = str(result.get("type", "")).lower().strip()

                    if kind == "permanent":
                        ia_permanent += 1

                    date_start, date_end, date_source, date_score = (
                        parse_wp_service_date_ia(
                            title, content_text, published_year, result
                        )
                    )

                    if date_start:
                        ia_success += 1
                        print(
                            f"[Gemini Servicios] {post_id} | "
                            f"{date_start} -> {date_end} | {title}"
                        )

                if not date_start:
                    continue

                soup = base.BeautifulSoup(
                    content_html, "html.parser"
                )
                image = ""
                embedded = post.get("_embedded") or {}
                media = (embedded.get("wp:featuredmedia") or [{}])[0]
                image = media.get("source_url") or ""
                if not image:
                    og = soup.find("img", src=True)
                    image = og.get("src", "") if og else ""

                location, location_source, location_score = (
                    base.extract_labeled_location(content_text)
                )
                if not location:
                    location, location_source, location_score = (
                        base.extract_narrative_location(content_text)
                    )

                address, address_source, address_score = (
                    base.extract_address(content_text)
                )
                city = base.infer_city(content_text, location, address)
                price, currency = base.extract_price(content_text)
                is_free = base.explicit_free(content_text)
                map_search_url = base.build_map_search_url(
                    location, address, city
                )

                occurrences = base.build_occurrences(
                    date_start, date_end, "", ""
                )

                tags = []
                for tag in (embedded.get("wp:term") or []):
                    if isinstance(tag, list):
                        tags.extend(
                            t.get("name", "")
                            for t in tag
                            if t.get("taxonomy") == "post_tag"
                        )
                tags = base.uniq(tags)

                events.append({
                    "id": f"servicios-{post_id}",
                    "source": "SERVICIOS",
                    "title": title,
                    "url": url,
                    "date_start": date_start,
                    "date_end": date_end,
                    "time_start": "",
                    "time_end": "",
                    "start_datetime": (
                        occurrences[0]["start_datetime"]
                        if occurrences
                        else base.make_local_datetime(date_start, "")
                    ),
                    "end_datetime": (
                        occurrences[-1]["end_datetime"]
                        if occurrences and occurrences[-1].get("end_datetime")
                        else ""
                    ),
                    "description": content_html,
                    "image": image,
                    "price": price,
                    "currency": currency,
                    "is_free": is_free,
                    "location": location,
                    "address": address,
                    "city": city,
                    "organizer": "",
                    "contact_email": [],
                    "contact_phone": [],
                    "categories": ["Servicios"],
                    "tags": tags,
                    "map_urls": [],
                    "map_search_url": map_search_url,
                    "registration_urls": [],
                    "external_urls": [url] if url else [],
                    "occurrences": occurrences,
                    "confidence": {
                        "date": {
                            "source": date_source,
                            "score": date_score,
                        },
                        "time": {
                            "source": "none",
                            "score": 0,
                            "has_start": False,
                            "has_end": False,
                        },
                        "location": {
                            "source": location_source,
                            "score": location_score,
                        },
                        "overall": round(
                            min(
                                1.0,
                                date_score * 0.55
                                + location_score * 0.25
                                + (0.10 if image else 0)
                                + 0.10,
                            ),
                            2,
                        ),
                    },
                    "_sources": {
                        "source_url": base.BASE + "/category/servicios/",
                        "post_id": post_id,
                        "date": date_source,
                    },
                })
            except Exception as exc:
                errors.append({
                    "stage": "services_event",
                    "post_id": post.get("id"),
                    "error": repr(exc),
                })

        if len(posts) < 100:
            break
        base.time.sleep(delay)

    # Guardamos estadísticas para que el informe permita medir la prueba.
    errors.append({
        "stage": "services_ia_stats",
        "attempts": ia_attempts,
        "success": ia_success,
        "permanent": ia_permanent,
    })

    dedup = base.OrderedDict()
    for e in events:
        dedup[e["id"]] = e
    return list(dedup.values()), errors


def main():
    if not GEMINI_API_KEY:
        print(
            "ADVERTENCIA: GEMINI_API_KEY no está definida. "
            "Se ejecutará con el parser normal."
        )

    # Monkey patch: todo MEC sigue funcionando exactamente igual.
    base.extract_services = extract_services_ia

    # Ejecuta el main original.
    base.main()


if __name__ == "__main__":
    main()
