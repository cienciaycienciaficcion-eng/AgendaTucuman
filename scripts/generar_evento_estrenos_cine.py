#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Genera el evento semanal "Estrenos de la semana" para Agenda Tucumán.

Funciones:
- Compara la cartelera actual con la anterior.
- Detecta únicamente películas nuevas.
- Genera un único evento semanal.
- El evento dura desde week_start hasta week_end.
- Incluye las películas nuevas.
- Genera un resumen con Gemini utilizando los datos reales de Cinemacenter.
- Si Gemini falla, el evento igualmente se genera sin resumen.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from pathlib import Path

import requests


TZ = "-03:00"

CARTELERA_URL = "https://www.cinemacenter.com.ar/cartelera#contenido"
MIBOLETERIA_URL = "https://www.miboleteria.com.ar"

DEFAULT_MODEL = "gemini-3.5-flash-lite"
GEMINI_TIMEOUT = 45
MAX_SUMMARY_CHARS = 900


# ============================================================
# UTILIDADES
# ============================================================

def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFD", clean(value))
    text = "".join(
        c for c in text
        if unicodedata.category(c) != "Mn"
    )

    text = text.lower()

    text = re.sub(r"\b(?:2d|3d)\b", " ", text)
    text = re.sub(r"\b(?:cast|sub)\b", " ", text)

    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def load_json(path: Path, default):
    if not path.exists():
        return default

    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"ADVERTENCIA: no se pudo leer {path}: {exc}")
        return default


def current_movies(data: dict) -> list[dict]:
    return list(
        ((data or {}).get("cartelera") or {}).get("movies") or []
    )


def movie_key(movie: dict) -> str:
    return normalize(movie.get("title", ""))


def occurrences_dates(movie: dict) -> list[str]:
    return sorted(
        {
            str(o.get("date"))
            for o in movie.get("occurrences", [])
            if o.get("date")
        }
    )


def format_date(value: str) -> str:
    try:
        y, m, d = map(int, value.split("-"))

        months = [
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        ]

        return f"{d} de {months[m - 1]} de {y}"

    except Exception:
        return value


# ============================================================
# GEMINI
# ============================================================

def extract_gemini_text(data: dict) -> str:
    """
    Extrae el texto de la respuesta de Gemini.
    """

    candidates = data.get("candidates") or []

    if not candidates:
        return ""

    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []

    texts = []

    for part in parts:
        if isinstance(part, dict) and part.get("text"):
            texts.append(str(part["text"]))

    return " ".join(texts).strip()


def normalize_summary(text: str) -> str:
    text = clean(text)

    text = re.sub(
        r"^(resumen\s*:\s*)",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = text.strip('"“”')

    if len(text) > MAX_SUMMARY_CHARS:
        cut = text[:MAX_SUMMARY_CHARS]

        # Intentar terminar en una oración completa.
        pos = max(
            cut.rfind(". "),
            cut.rfind("."),
        )

        if pos >= 300:
            text = cut[:pos + 1]
        else:
            text = cut.rstrip() + "…"

    return text


def build_gemini_prompt(new_movies: list[dict], week_start: str, week_end: str) -> str:

    movies_text = []

    for movie in new_movies:

        metadata = movie.get("metadata") or {}

        title = clean(movie.get("title"))
        original_title = clean(metadata.get("original_title"))
        year = clean(metadata.get("year"))
        duration = metadata.get("duration_minutes")
        genres = clean(
            ", ".join(metadata.get("genres") or [])
        )
        director = clean(
            ", ".join(metadata.get("director") or [])
        )
        cast = clean(
            ", ".join(metadata.get("cast") or [])
        )
        classification = clean(
            metadata.get("classification")
        )
        synopsis = clean(
            metadata.get("synopsis")
        )

        block = [
            f"Título: {title}",
        ]

        if original_title:
            block.append(
                f"Título original: {original_title}"
            )

        if year:
            block.append(
                f"Año: {year}"
            )

        if duration:
            block.append(
                f"Duración: {duration} minutos"
            )

        if genres:
            block.append(
                f"Géneros: {genres}"
            )

        if director:
            block.append(
                f"Director: {director}"
            )

        if cast:
            block.append(
                f"Actores: {cast}"
            )

        if classification:
            block.append(
                f"Clasificación: {classification}"
            )

        if synopsis:
            block.append(
                f"Sinopsis: {synopsis}"
            )

        movies_text.append("\n".join(block))

    movies_context = "\n\n---\n\n".join(movies_text)

    return f"""
Eres el asistente editorial de Agenda Tucumán.

Necesito escribir el resumen del evento "Estrenos de la semana".

La semana cinematográfica es:

{format_date(week_start)} al {format_date(week_end)}

Estas son las películas que se incorporan como estrenos esta semana:

{movies_context}

Escribe un único resumen breve en español argentino.

El resumen debe:
- presentar que son los estrenos cinematográficos de esta semana;
- mencionar las películas principales;
- describir brevemente qué tipo de películas son;
- utilizar únicamente la información proporcionada;
- no inventar datos;
- no mencionar que eres una IA;
- no utilizar listas;
- no utilizar Markdown;
- no utilizar encabezados;
- tener aproximadamente entre 3 y 6 oraciones.

Devuelve solamente el texto del resumen.
""".strip()


def generate_gemini_summary(
    new_movies: list[dict],
    week_start: str,
    week_end: str,
) -> str:

    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        print(
            "ADVERTENCIA: GEMINI_API_KEY no está configurada. "
            "El evento se generará sin resumen."
        )
        return ""

    model = os.getenv(
        "GEMINI_MODEL",
        DEFAULT_MODEL,
    ).strip()

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{model}:generateContent"
    )

    prompt = build_gemini_prompt(
        new_movies,
        week_start,
        week_end,
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 500,
        },
    }

    try:

        response = requests.post(
            url,
            params={"key": api_key},
            json=payload,
            timeout=GEMINI_TIMEOUT,
        )

        if response.status_code != 200:

            print(
                "ADVERTENCIA: Gemini respondió "
                f"{response.status_code}: "
                f"{response.text[:500]}"
            )

            return ""

        data = response.json()

        text = extract_gemini_text(data)

        if not text:
            print(
                "ADVERTENCIA: Gemini no devolvió texto."
            )
            return ""

        summary = normalize_summary(text)

        print(
            "✓ Resumen Gemini generado "
            f"({len(summary)} caracteres)."
        )

        return summary

    except Exception as exc:

        print(
            "ADVERTENCIA: error consultando Gemini: "
            f"{exc}"
        )

        return ""


# ============================================================
# CONSTRUCCIÓN DEL EVENTO
# ============================================================

def build_event(
    current: dict,
    previous: dict,
) -> dict | None:

    current_list = current_movies(current)

    previous_keys = {
        movie_key(m)
        for m in current_movies(previous)
    }

    new_movies = []
    seen = set()

    for movie in current_list:

        key = movie_key(movie)

        if not key:
            continue

        if key in seen:
            continue

        if key in previous_keys:
            continue

        seen.add(key)

        dates = occurrences_dates(movie)

        cartelera = current.get("cartelera") or {}

        first_date = (
            dates[0]
            if dates
            else cartelera.get("week_start")
        )

        metadata = movie.get("metadata") or {}

        item = {
            "title": clean(
                movie.get("title")
            ),

            "release_date": first_date,

            "format": clean(
                movie.get("format")
            ),

            "language": clean(
                movie.get("language")
            ),

            "poster": metadata.get(
                "poster"
            ),

            # Mantener metadata para Gemini.
            "metadata": metadata,
        }

        new_movies.append(item)

    if not new_movies:
        return None

    cartelera = current.get("cartelera") or {}

    week_start = cartelera.get(
        "week_start"
    )

    week_end = cartelera.get(
        "week_end"
    )

    if not week_start or not week_end:
        return None

    new_movies.sort(
        key=lambda x: (
            x.get("release_date")
            or week_start,
            normalize(x["title"]),
        )
    )

    # ========================================================
    # GENERAR RESUMEN IA
    # ========================================================

    summary = generate_gemini_summary(
        new_movies,
        week_start,
        week_end,
    )

    # ========================================================
    # DESCRIPCIÓN
    # ========================================================

    lines = [
        "<p><strong>Nuevas películas que llegan "
        "a la cartelera de Cinemacenter Tucumán "
        "esta semana:</strong></p>",
        "<ul>",
    ]

    for movie in new_movies:

        label = movie["title"]

        if movie.get("release_date"):

            label += (
                f" — estreno "
                f"{format_date(movie['release_date'])}"
            )

        lines.append(
            f"<li>{label}</li>"
        )

    lines.extend(
        [
            "</ul>",
            (
                f'<p><a href="{CARTELERA_URL}">'
                "Ver cartelera y horarios"
                "</a></p>"
            ),
        ]
    )

    description = "\n".join(lines)

    # Imagen principal: primera película que tenga poster.
    poster = next(
        (
            m.get("poster")
            for m in new_movies
            if m.get("poster")
        ),
        "",
    )

    # ========================================================
    # EVENTO
    # ========================================================

    event = {
        "id": (
            f"cine-estrenos-semana-"
            f"{week_start}"
        ),

        "source": "CINEMACENTER",

        "title": "Estrenos de la semana",

        "url": CARTELERA_URL,

        "date_start": week_start,

        "date_end": week_end,

        "time_start": "",

        "time_end": "",

        "start_datetime": (
            f"{week_start}T00:00:00{TZ}"
        ),

        "end_datetime": "",

        "description": description,

        "summary": summary,

        "image": poster,

        "price": None,

        "currency": "",

        "is_free": False,

        "location": "Cinemacenter Tucumán",

        "address": (
            "Av. Néstor Kirchner "
            "(Ex Roca) 3450"
        ),

        "city": "San Miguel de Tucumán",

        "organizer": "Cinemacenter",

        "categories": [
            "Cine"
        ],

        "tags": [
            "Cine",
            "Estrenos"
        ],

        "map_search_url": (
            "https://www.google.com/maps/search/"
            "?api=1&query="
            "Cinemacenter+Tucumán"
        ),

        "registration_urls": [
            MIBOLETERIA_URL
        ],

        "external_urls": [
            CARTELERA_URL,
            MIBOLETERIA_URL,
        ],

        "occurrences": [
            {
                "date": week_start,
                "time_start": "",
                "time_end": "",
                "start_datetime": (
                    f"{week_start}"
                    f"T00:00:00{TZ}"
                ),
                "end_datetime": "",
            }
        ],

        "cinemacenter_release_titles": [
            m["title"]
            for m in new_movies
        ],

        "cinemacenter_release_count": len(
            new_movies
        ),
    }

    return event


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--agenda",
        required=True,
    )

    parser.add_argument(
        "--cinema-current",
        required=True,
    )

    parser.add_argument(
        "--cinema-previous",
        required=True,
    )

    args = parser.parse_args()

    agenda_path = Path(
        args.agenda
    )

    current_path = Path(
        args.cinema_current
    )

    previous_path = Path(
        args.cinema_previous
    )

    agenda = load_json(
        agenda_path,
        [],
    )

    current = load_json(
        current_path,
        {},
    )

    previous = load_json(
        previous_path,
        {},
    )

    if not isinstance(agenda, list):

        raise RuntimeError(
            "agenda_eventos.json "
            "no contiene una lista de eventos"
        )

    # --------------------------------------------------------
    # Eliminar evento anterior de Estrenos de la semana.
    # --------------------------------------------------------

    agenda = [
        e
        for e in agenda
        if not (
            e.get("source") == "CINEMACENTER"
            and e.get("title")
            == "Estrenos de la semana"
        )
    ]

    # --------------------------------------------------------
    # Construir evento.
    # --------------------------------------------------------

    event = build_event(
        current,
        previous,
    )

    if event:

        agenda.append(event)

        print(
            "✓ Evento generado: "
            "Estrenos de la semana "
            f"({event['cinemacenter_release_count']} "
            "películas)"
        )

        for title in event[
            "cinemacenter_release_titles"
        ]:

            print(
                f"  - {title}"
            )

        print(
            "  Vigencia: "
            f"{event['date_start']} -> "
            f"{event['date_end']}"
        )

        if event.get("summary"):

            print(
                "  ✓ Resumen IA: generado"
            )

        else:

            print(
                "  ⚠ Resumen IA: no disponible"
            )

    else:

        print(
            "✓ No hay estrenos nuevos "
            "esta semana; no se genera "
            "el evento."
        )

    # --------------------------------------------------------
    # Guardar agenda.
    # --------------------------------------------------------

    agenda_path.write_text(
        json.dumps(
            agenda,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
