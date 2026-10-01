#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera el evento semanal "Estrenos de la semana" para Agenda Tucumán.

La comparación se hace entre la cartelera Cinemacenter recién extraída y la
cartelera Cinemacenter publicada en la ejecución anterior. Un título cuenta
como estreno de la semana únicamente si no estaba presente en la cartelera
anterior.

Si no hay películas nuevas, no se agrega ningún evento.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import date
from pathlib import Path


TZ = "-03:00"
CARTELERA_URL = "https://www.cinemacenter.com.ar/cartelera#contenido"
MIBOLETERIA_URL = "https://www.miboleteria.com.ar"


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFD", clean(value))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    text = re.sub(r"\b(?:2d|3d)\b", " ", text)
    text = re.sub(r"\b(?:cast|sub)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def load_json(path: Path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def movie_key(movie: dict) -> str:
    return normalize(movie.get("title", ""))


def current_movies(data: dict) -> list[dict]:
    return list(((data or {}).get("cartelera") or {}).get("movies") or [])


def occurrences_dates(movie: dict) -> list[str]:
    return sorted({
        str(o.get("date"))
        for o in movie.get("occurrences", [])
        if o.get("date")
    })


def format_date(value: str) -> str:
    try:
        y, m, d = map(int, value.split("-"))
        months = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        return f"{d} de {months[m - 1]}"
    except Exception:
        return value


def build_event(current: dict, previous: dict) -> dict | None:
    current_list = current_movies(current)
    previous_keys = {movie_key(m) for m in current_movies(previous)}

    new_movies = []
    seen = set()
    for movie in current_list:
        key = movie_key(movie)
        if not key or key in seen or key in previous_keys:
            continue
        seen.add(key)
        dates = occurrences_dates(movie)
        first_date = dates[0] if dates else ((current.get("cartelera") or {}).get("week_start"))
        item = {
            "title": clean(movie.get("title")),
            "release_date": first_date,
            "format": clean(movie.get("format")),
            "language": clean(movie.get("language")),
            "poster": ((movie.get("metadata") or {}).get("poster")),
        }
        new_movies.append(item)

    if not new_movies:
        return None

    cartelera = current.get("cartelera") or {}
    week_start = cartelera.get("week_start")
    week_end = cartelera.get("week_end")
    if not week_start or not week_end:
        return None

    new_movies.sort(key=lambda x: (x.get("release_date") or week_start, normalize(x["title"])))

    lines = [
        "<p><strong>Nuevas películas que llegan a la cartelera de Cinemacenter Tucumán esta semana:</strong></p>",
        "<ul>",
    ]
    for movie in new_movies:
        label = movie["title"]
        if movie.get("release_date"):
            label += f" — estreno {format_date(movie['release_date'])}"
        lines.append(f"<li>{label}</li>")
    lines.extend([
        "</ul>",
        f'<p><a href="{CARTELERA_URL}">Ver cartelera y horarios</a></p>',
    ])
    description = "\n".join(lines)

    poster = next((m.get("poster") for m in new_movies if m.get("poster")), "")
    titles = ", ".join(m["title"] for m in new_movies)

    return {
        "id": f"cine-estrenos-semana-{week_start}",
        "source": "CINEMACENTER",
        "title": "Estrenos de la semana",
        "url": CARTELERA_URL,
        "date_start": week_start,
        "date_end": week_end,
        "time_start": "",
        "time_end": "",
        "start_datetime": f"{week_start}T00:00:00{TZ}",
        "end_datetime": "",
        "description": description,
        "image": poster,
        "price": None,
        "currency": "",
        "is_free": False,
        "location": "Cinemacenter Tucumán",
        "address": "Av. Néstor Kirchner (Ex Roca) 3450",
        "city": "San Miguel de Tucumán",
        "organizer": "Cinemacenter",
        "categories": ["Cine"],
        "tags": ["Cine", "Estrenos"],
        "map_search_url": "https://www.google.com/maps/search/?api=1&query=Cinemacenter+Tucumán",
        "registration_urls": [MIBOLETERIA_URL],
        "external_urls": [CARTELERA_URL, MIBOLETERIA_URL],
        "occurrences": [
            {
                "date": week_start,
                "time_start": "",
                "time_end": "",
                "start_datetime": f"{week_start}T00:00:00{TZ}",
                "end_datetime": "",
            }
        ],
        "cinemacenter_release_titles": [m["title"] for m in new_movies],
        "cinemacenter_release_count": len(new_movies),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agenda", required=True)
    parser.add_argument("--cinema-current", required=True)
    parser.add_argument("--cinema-previous", required=True)
    args = parser.parse_args()

    agenda_path = Path(args.agenda)
    current_path = Path(args.cinema_current)
    previous_path = Path(args.cinema_previous)

    agenda = load_json(agenda_path, [])
    current = load_json(current_path, {})
    previous = load_json(previous_path, {})

    if not isinstance(agenda, list):
        raise RuntimeError("agenda_eventos.json no contiene una lista de eventos")

    # Evita duplicados si se ejecuta más de una vez sobre el mismo archivo.
    agenda = [e for e in agenda if e.get("source") != "CINEMACENTER" or e.get("title") != "Estrenos de la semana"]

    event = build_event(current, previous)
    if event:
        agenda.append(event)
        print(f"✓ Evento generado: Estrenos de la semana ({event['cinemacenter_release_count']} películas)")
        for title in event["cinemacenter_release_titles"]:
            print(f"  - {title}")
        print(f"  Vigencia: {event['date_start']} -> {event['date_end']}")
    else:
        print("✓ No hay estrenos nuevos esta semana; no se genera el evento.")

    agenda_path.write_text(json.dumps(agenda, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
