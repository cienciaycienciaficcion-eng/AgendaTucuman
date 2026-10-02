#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Genera el evento semanal "Estrenos de la semana".

- Detecta películas nuevas comparando carteleras.
- Genera un único evento semanal.
- Usa los datos obtenidos por Cinemacenter.
- Genera un resumen mediante Gemini.
- Gemini tiene 2 intentos.
- Si Gemini falla, el evento se genera igualmente.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import unicodedata
from pathlib import Path

import requests


TZ = "-03:00"

CARTELERA_URL = "https://www.cinemacenter.com.ar/cartelera#contenido"
MIBOLETERIA_URL = "https://www.miboleteria.com.ar"

DEFAULT_MODEL = "gemini-3.5-flash-lite"

GEMINI_TIMEOUT = 45
GEMINI_RETRIES = 2
GEMINI_RETRY_DELAY = 10

MAX_SUMMARY_CHARS = 900


# ============================================================
# UTILIDADES
# ============================================================

def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize(value: object) -> str:
    text = unicodedata.normalize(
        "NFD",
        clean(value)
    )

    text = "".join(
        c for c in text
        if unicodedata.category(c) != "Mn"
    )

    text = text.lower()

    text = re.sub(
        r"\b(?:2d|3d)\b",
        " ",
        text
    )

    text = re.sub(
        r"\b(?:cast|sub)\b",
        " ",
        text
    )

    return re.sub(
        r"[^a-z0-9]+",
        " ",
        text
    ).strip()


def load_json(path: Path, default):
    if not path.exists():
        return default

    try:
        with path.open(
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except Exception as exc:
        print(
            f"ADVERTENCIA: no se pudo leer "
            f"{path}: {exc}"
        )

        return default


def current_movies(data: dict) -> list[dict]:
    return list(
        (
            data or {}
        ).get("cartelera", {})
        .get("movies", [])
        or []
    )


def movie_key(movie: dict) -> str:
    return normalize(
        movie.get("title", "")
    )


def occurrences_dates(movie: dict) -> list[str]:
    return sorted(
        {
            str(o.get("date"))
            for o in (
                movie.get("occurrences")
                or []
            )
            if o.get("date")
        }
    )


def format_date(value: str) -> str:

    try:

        y, m, d = map(
            int,
            value.split("-")
        )

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

        return (
            f"{d} de "
            f"{months[m - 1]} de "
            f"{y}"
        )

    except Exception:
        return value


# ============================================================
# GEMINI
# ============================================================

def extract_gemini_text(data: dict) -> str:

    candidates = (
        data.get("candidates")
        or []
    )

    if not candidates:
        return ""

    content = (
        candidates[0]
        .get("content")
        or {}
    )

    parts = (
        content.get("parts")
        or []
    )

    texts = []

    for part in parts:

        if (
            isinstance(part, dict)
            and part.get("text")
        ):
            texts.append(
                str(part["text"])
            )

    return " ".join(texts).strip()


def normalize_summary(text: str) -> str:

    text = clean(text)

    text = re.sub(
        r"^(resumen\s*:\s*)",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = text.strip(
        '"“”'
    )

    if len(text) > MAX_SUMMARY_CHARS:

        cut = text[
            :MAX_SUMMARY_CHARS
        ]

        pos = max(
            cut.rfind(". "),
            cut.rfind(".")
        )

        if pos >= 300:
            text = cut[
                :pos + 1
            ]

        else:
            text = (
                cut.rstrip()
                + "…"
            )

    return text


def build_gemini_prompt(
    new_movies: list[dict],
    week_start: str,
    week_end: str,
) -> str:

    movies_text = []

    for movie in new_movies:

        metadata = (
            movie.get("metadata")
            or {}
        )

        title = clean(
            movie.get("title")
        )

        original_title = clean(
            metadata.get(
                "original_title"
            )
        )

        year = clean(
            metadata.get("year")
        )

        duration = metadata.get(
            "duration_minutes"
        )

        genres = clean(
            ", ".join(
                metadata.get(
                    "genres"
                )
                or []
            )
        )

        director = clean(
            ", ".join(
                metadata.get(
                    "director"
                )
                or []
            )
        )

        cast = clean(
            ", ".join(
                metadata.get(
                    "cast"
                )
                or []
            )
        )

        classification = clean(
            metadata.get(
                "classification"
            )
        )

        synopsis = clean(
            metadata.get(
                "synopsis"
            )
        )

        block = [
            f"Título: {title}"
        ]

        if original_title:
            block.append(
                "Título original: "
                f"{original_title}"
            )

        if year:
            block.append(
                f"Año: {year}"
            )

        if duration:
            block.append(
                f"Duración: "
                f"{duration} minutos"
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
                f"Clasificación: "
                f"{classification}"
            )

        if synopsis:
            block.append(
                f"Sinopsis: {synopsis}"
            )

        movies_text.append(
            "\n".join(block)
        )

    movies_context = (
        "\n\n---\n\n".join(
            movies_text
        )
    )

    return f"""
Eres el asistente editorial de Agenda Tucumán.

Necesito escribir el resumen del evento
"Estrenos de la semana".

La semana cinematográfica es:

{format_date(week_start)}
al
{format_date(week_end)}

Estas son las películas que se incorporan
como estrenos esta semana:

{movies_context}

Escribe un único resumen breve en español
argentino.

El resumen debe:

- presentar que son los estrenos
  cinematográficos de esta semana;
- mencionar las películas principales;
- describir brevemente qué tipo de películas
  son;
- utilizar únicamente la información
  proporcionada;
- no inventar datos;
- no mencionar que eres una IA;
- no utilizar listas;
- no utilizar Markdown;
- no utilizar encabezados;
- tener aproximadamente entre 3 y 6
  oraciones.

Devuelve solamente el texto del resumen.
""".strip()


def generate_gemini_summary(
    new_movies: list[dict],
    week_start: str,
    week_end: str,
) -> str:

    api_key = os.getenv(
        "GEMINI_API_KEY",
        ""
    ).strip()

    if not api_key:

        print(
            "ADVERTENCIA: "
            "GEMINI_API_KEY no está configurada."
        )

        return ""

    model = os.getenv(
        "GEMINI_MODEL",
        DEFAULT_MODEL
    ).strip()

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{model}:generateContent"
    )

    prompt = build_gemini_prompt(
        new_movies,
        week_start,
        week_end
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
            "maxOutputTokens": 500
        }
    }

    # ========================================================
    # DOS INTENTOS
    # ========================================================

    for attempt in range(
        1,
        GEMINI_RETRIES + 1
    ):

        print(
            f"→ Intento {attempt}/"
            f"{GEMINI_RETRIES} "
            "para generar resumen con Gemini..."
        )

        try:

            response = requests.post(
                url,
                params={
                    "key": api_key
                },
                json=payload,
                timeout=GEMINI_TIMEOUT
            )

            if response.status_code == 200:

                data = response.json()

                text = extract_gemini_text(
                    data
                )

                if text:

                    summary = normalize_summary(
                        text
                    )

                    if summary:

                        print(
                            "✓ Gemini generó "
                            "el resumen correctamente."
                        )

                        return summary

                print(
                    "ADVERTENCIA: Gemini "
                    "respondió correctamente "
                    "pero no devolvió texto."
                )

            else:

                print(
                    "ADVERTENCIA: Gemini "
                    f"respondió HTTP "
                    f"{response.status_code}."
                )

                print(
                    response.text[:500]
                )

        except Exception as exc:

            print(
                "ADVERTENCIA: error "
                f"consultando Gemini: {exc}"
            )

        # ----------------------------------------------------
        # Si todavía queda un intento, esperar.
        # ----------------------------------------------------

        if attempt < GEMINI_RETRIES:

            print(
                f"→ Esperando "
                f"{GEMINI_RETRY_DELAY} segundos "
                "antes del segundo intento..."
            )

            time.sleep(
                GEMINI_RETRY_DELAY
            )

    # ========================================================
    # FALLAR GEMINI NO DEBE FALLAR EL EVENTO
    # ========================================================

    print(
        "⚠ Gemini no pudo generar "
        "el resumen después de "
        f"{GEMINI_RETRIES} intentos."
    )

    print(
        "⚠ El evento se generará "
        "igualmente con los datos "
        "obtenidos por Cinemacenter."
    )

    return ""


# ============================================================
# CONSTRUIR EVENTO
# ============================================================

def build_event(
    current: dict,
    previous: dict,
) -> dict | None:

    current_list = current_movies(
        current
    )

    previous_keys = {
        movie_key(movie)
        for movie in current_movies(
            previous
        )
    }

    new_movies = []
    seen = set()

    for movie in current_list:

        key = movie_key(
            movie
        )

        if not key:
            continue

        if key in seen:
            continue

        if key in previous_keys:
            continue

        seen.add(key)

        dates = occurrences_dates(
            movie
        )

        cartelera = (
            current.get(
                "cartelera"
            )
            or {}
        )

        first_date = (
            dates[0]
            if dates
            else cartelera.get(
                "week_start"
            )
        )

        metadata = (
            movie.get(
                "metadata"
            )
            or {}
        )

        new_movies.append(
            {
                "title": clean(
                    movie.get(
                        "title"
                    )
                ),
                "release_date": first_date,
                "format": clean(
                    movie.get(
                        "format"
                    )
                ),
                "language": clean(
                    movie.get(
                        "language"
                    )
                ),
                "poster": metadata.get(
                    "poster"
                ),
                "metadata": metadata
            }
        )

    if not new_movies:
        return None

    cartelera = (
        current.get(
            "cartelera"
        )
        or {}
    )

    week_start = cartelera.get(
        "week_start"
    )

    week_end = cartelera.get(
        "week_end"
    )

    if not week_start or not week_end:
        return None

    new_movies.sort(
        key=lambda movie: (
            movie.get(
                "release_date"
            )
            or week_start,
            normalize(
                movie["title"]
            )
        )
    )

    # ========================================================
    # GEMINI
    # ========================================================

    summary = generate_gemini_summary(
        new_movies,
        week_start,
        week_end
    )

    # ========================================================
    # DESCRIPCIÓN
    # ========================================================

    lines = [
        "<p><strong>"
        "Nuevas películas que llegan "
        "a la cartelera de Cinemacenter "
        "Tucumán esta semana:"
        "</strong></p>",

        "<ul>"
    ]

    for movie in new_movies:

        label = movie[
            "title"
        ]

        if movie.get(
            "release_date"
        ):

            label += (
                " — estreno "
                + format_date(
                    movie[
                        "release_date"
                    ]
                )
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
            )
        ]
    )

    description = "\n".join(
        lines
    )

    # ========================================================
    # POSTER
    # ========================================================

    poster = next(
        (
            movie.get(
                "poster"
            )
            for movie in new_movies
            if movie.get(
                "poster"
            )
        ),
        ""
    )

    # ========================================================
    # EVENTO
    # ========================================================

    event = {

        "id": (
            "cine-estrenos-semana-"
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
            f"{week_start}"
            f"T00:00:00{TZ}"
        ),

        "end_datetime": "",

        "description": description,

        "summary": summary,

        "image": poster,

        "price": None,

        "currency": "",

        "is_free": False,

        "location": (
            "Cinemacenter Tucumán"
        ),

        "address": (
            "Av. Néstor Kirchner "
            "(Ex Roca) 3450"
        ),

        "city": (
            "San Miguel de Tucumán"
        ),

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
            MIBOLETERIA_URL
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

                "end_datetime": ""
            }
        ],

        "cinemacenter_release_titles": [
            movie[
                "title"
            ]
            for movie in new_movies
        ],

        "cinemacenter_release_count": (
            len(new_movies)
        )
    }

    return event


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--agenda",
        required=True
    )

    parser.add_argument(
        "--cinema-current",
        required=True
    )

    parser.add_argument(
        "--cinema-previous",
        required=True
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
        []
    )

    current = load_json(
        current_path,
        {}
    )

    previous = load_json(
        previous_path,
        {}
    )

    if not isinstance(
        agenda,
        list
    ):

        raise RuntimeError(
            "agenda_eventos.json "
            "no contiene una lista "
            "de eventos."
        )

    # ========================================================
    # ELIMINAR EVENTO ANTERIOR
    # ========================================================

    agenda = [
        event
        for event in agenda
        if not (
            event.get(
                "source"
            ) == "CINEMACENTER"

            and event.get(
                "title"
            ) == "Estrenos de la semana"
        )
    ]

    # ========================================================
    # GENERAR NUEVO EVENTO
    # ========================================================

    event = build_event(
        current,
        previous
    )

    if event:

        agenda.append(
            event
        )

        print(
            "✓ Evento generado: "
            "Estrenos de la semana"
        )

        print(
            "  Películas nuevas: "
            f"{event['cinemacenter_release_count']}"
        )

        for title in event[
            "cinemacenter_release_titles"
        ]:

            print(
                f"  - {title}"
            )

        print(
            "  Vigencia: "
            f"{event['date_start']} → "
            f"{event['date_end']}"
        )

        if event.get(
            "summary"
        ):

            print(
                "  ✓ Resumen IA: generado"
            )

        else:

            print(
                "  ⚠ Resumen IA: "
                "no disponible; "
                "evento publicado "
                "sin resumen."
            )

    else:

        print(
            "✓ No hay estrenos nuevos "
            "esta semana."
        )

    # ========================================================
    # GUARDAR
    # ========================================================

    agenda_path.write_text(
        json.dumps(
            agenda,
            ensure_ascii=False,
            indent=2
        )
        + "\n",
        encoding="utf-8"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
