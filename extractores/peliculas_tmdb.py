#!/usr/bin/env python3
"""
Enriquecimiento de películas de Agenda Tucumán usando TMDB.

Entrada:
  datos/cine_cinemacenter_tucuman.json

Salida:
  datos/agenda_peliculas.json

La API de TMDB se consulta únicamente desde GitHub Actions (no desde la APK).
El token debe estar en la variable de entorno TMDB_API_TOKEN.

Se conserva información previa para películas que no puedan resolverse en una
ejecución posterior, evitando que una caída temporal de TMDB vacíe el catálogo.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p"
CINEMA_FILE = Path("datos/cine_cinemacenter_tucuman.json")
OUTPUT_FILE = Path("datos/agenda_peliculas.json")

TIMEOUT = 25
SLEEP_BETWEEN_REQUESTS = 0.15
MAX_CAST = 12
MAX_TRAILERS = 3


def normalize(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def year_from_date(value: str | None) -> int | None:
    if not value or len(value) < 4:
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None


def tmdb_request(session: requests.Session, path: str, params: dict[str, Any]) -> dict[str, Any] | None:
    url = f"{BASE_URL}{path}"
    try:
        response = session.get(url, params=params, timeout=TIMEOUT)
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "2"))
            print(f"  TMDB rate limit; esperando {retry_after}s...")
            time.sleep(min(retry_after, 10))
            response = session.get(url, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        print(f"  ERROR TMDB {path}: {exc}")
        return None


def choose_result(query: str, results: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not results:
        return None

    nq = normalize(query)

    def score(item: dict[str, Any]) -> float:
        title = normalize(item.get("title"))
        original = normalize(item.get("original_title"))
        release_year = year_from_date(item.get("release_date"))

        value = 0.0
        if title == nq:
            value += 100
        elif original == nq:
            value += 98
        elif nq and (nq in title or title in nq):
            value += 70
        elif nq and (nq in original or original in nq):
            value += 68

        # Penaliza coincidencias que solo parecen cercanas.
        q_words = set(nq.split())
        t_words = set(title.split())
        if q_words and t_words:
            overlap = len(q_words & t_words) / max(len(q_words), len(t_words))
            value += overlap * 25

        # Preferimos películas con fecha y cierta popularidad.
        if release_year:
            value += 2
        value += min(float(item.get("popularity") or 0), 20) / 20

        return value

    ranked = sorted(results, key=score, reverse=True)
    best = ranked[0]

    # Evitamos rellenar con una película claramente diferente.
    if score(best) < 55:
        return None

    return best


def search_movie(session: requests.Session, title: str) -> dict[str, Any] | None:
    # Primero buscamos en español argentino y luego en inglés.
    queries = [
        {"language": "es-AR", "region": "AR"},
        {"language": "en-US", "region": "AR"},
    ]

    all_results: list[dict[str, Any]] = []
    seen_ids: set[int] = set()

    for params in queries:
        params = {
            **params,
            "query": title,
            "include_adult": "false",
            "page": 1,
        }
        data = tmdb_request(session, "/search/movie", params)
        if not data:
            continue

        for item in data.get("results", []):
            mid = item.get("id")
            if mid and mid not in seen_ids:
                seen_ids.add(mid)
                all_results.append(item)

        time.sleep(SLEEP_BETWEEN_REQUESTS)

    return choose_result(title, all_results)


def get_details(session: requests.Session, tmdb_id: int) -> dict[str, Any] | None:
    data = tmdb_request(
        session,
        f"/movie/{tmdb_id}",
        {
            "language": "es-AR",
            "append_to_response": "credits,videos",
            "include_image_language": "es,null,en",
        },
    )
    time.sleep(SLEEP_BETWEEN_REQUESTS)
    return data


def build_movie(
    cinema_title: str,
    details: dict[str, Any],
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    release_date = details.get("release_date") or None
    genres = [
        g.get("name")
        for g in details.get("genres", [])
        if g.get("name")
    ]

    crew = details.get("credits", {}).get("crew", [])
    directors = []
    seen_directors = set()
    for person in crew:
        if person.get("job") == "Director" and person.get("name"):
            if person["name"] not in seen_directors:
                seen_directors.add(person["name"])
                directors.append(person["name"])

    cast = []
    seen_cast = set()
    for person in details.get("credits", {}).get("cast", [])[:30]:
        name = person.get("name")
        if name and name not in seen_cast:
            seen_cast.add(name)
            cast.append({
                "nombre": name,
                "personaje": person.get("character") or "",
            })
        if len(cast) >= MAX_CAST:
            break

    videos = details.get("videos", {}).get("results", [])
    trailers = []

    # Prefer official YouTube trailers, then teasers.
    def video_score(v: dict[str, Any]) -> tuple:
        site = (v.get("site") or "").lower()
        typ = (v.get("type") or "").lower()
        official = bool(v.get("official"))
        country = (v.get("iso_3166_1") or "").upper()
        return (
            site == "youtube",
            typ == "trailer",
            official,
            country == "AR",
            country == "US",
        )

    for video in sorted(videos, key=video_score, reverse=True):
        if (video.get("site") or "").lower() != "youtube":
            continue
        if (video.get("type") or "").lower() not in {"trailer", "teaser"}:
            continue
        key = video.get("key")
        if not key:
            continue

        trailers.append({
            "id": video.get("id"),
            "titulo": video.get("name") or "Tráiler",
            "tipo": video.get("type"),
            "youtube_id": key,
            "url": f"https://www.youtube.com/watch?v={key}",
            "oficial": bool(video.get("official")),
        })
        if len(trailers) >= MAX_TRAILERS:
            break

    poster_path = details.get("poster_path")
    poster = f"{IMAGE_BASE}/w500{poster_path}" if poster_path else None

    movie = {
        "id": f"tmdb_{details.get('id')}",
        "titulo": details.get("title") or cinema_title,
        "titulo_original": details.get("original_title") or "",
        "anio": year_from_date(release_date),
        "fecha_estreno": release_date,
        "duracion_minutos": details.get("runtime"),
        "generos": genres,
        "director": directors,
        "actores": cast,
        "sinopsis": details.get("overview") or "",
        "poster": poster,
        "trailers": trailers,
        "tmdb_id": details.get("id"),
        "tmdb_url": f"https://www.themoviedb.org/movie/{details.get('id')}",
        "fuente": "TMDB",
        "titulo_cinemacenter": cinema_title,
        "actualizado_at": datetime.now(timezone.utc).isoformat(),
    }

    # Si TMDB temporalmente devuelve algún campo vacío, conserva el valor
    # anterior de ese campo cuando existe.
    if previous:
        for field in (
            "titulo_original",
            "anio",
            "fecha_estreno",
            "duracion_minutos",
            "generos",
            "director",
            "actores",
            "sinopsis",
            "poster",
            "trailers",
        ):
            empty = movie.get(field) in (None, "", [])
            if empty and previous.get(field) not in (None, "", []):
                movie[field] = previous[field]

    return movie


def main() -> None:
    token = os.environ.get("TMDB_API_TOKEN", "").strip()
    if not token:
        print("ERROR: falta TMDB_API_TOKEN.")
        print("Configuralo como GitHub Actions Secret.")
        sys.exit(2)

    if not CINEMA_FILE.exists():
        print(f"ERROR: no existe {CINEMA_FILE}")
        sys.exit(3)

    cinema_data = json.loads(CINEMA_FILE.read_text(encoding="utf-8"))
    current = cinema_data.get("cartelera", {}).get("movies", [])

    # Una ficha por título, no una ficha por variante 2D/3D/idioma.
    titles: list[str] = []
    seen_titles: set[str] = set()
    for movie in current:
        title = (movie.get("title") or "").strip()
        key = normalize(title)
        if title and key not in seen_titles:
            seen_titles.add(key)
            titles.append(title)

    previous_data: dict[str, Any] = {}
    if OUTPUT_FILE.exists():
        try:
            old = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
            for movie in old.get("peliculas", []):
                key = normalize(movie.get("titulo_cinemacenter") or movie.get("titulo"))
                if key:
                    previous_data[key] = movie
        except Exception as exc:
            print(f"ADVERTENCIA: no se pudo leer el catálogo anterior: {exc}")

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "accept": "application/json",
        "User-Agent": "AgendaTucuman/1.0",
    })

    movies = []
    unresolved = []

    print("=" * 70)
    print("AGENDA TUCUMÁN - ENRIQUECIMIENTO DE PELÍCULAS CON TMDB")
    print("=" * 70)
    print(f"Películas únicas en cartelera: {len(titles)}")
    print()

    for title in titles:
        key = normalize(title)
        print(f"→ {title}")

        match = search_movie(session, title)

        if not match:
            print("  ⚠ No se encontró coincidencia confiable en TMDB.")
            old = previous_data.get(key)
            if old:
                print("  ✓ Se conserva la ficha anterior.")
                movies.append(old)
            else:
                movies.append({
                    "id": f"cinemacenter_{key.replace(' ', '_')}",
                    "titulo": title,
                    "titulo_original": "",
                    "anio": None,
                    "fecha_estreno": None,
                    "duracion_minutos": None,
                    "generos": [],
                    "director": [],
                    "actores": [],
                    "sinopsis": "",
                    "poster": None,
                    "trailers": [],
                    "tmdb_id": None,
                    "tmdb_url": None,
                    "fuente": None,
                    "titulo_cinemacenter": title,
                    "actualizado_at": datetime.now(timezone.utc).isoformat(),
                })
            unresolved.append(title)
            continue

        tmdb_id = match.get("id")
        print(f"  ✓ TMDB: {match.get('title')} [{tmdb_id}]")

        details = get_details(session, tmdb_id)
        if not details:
            print("  ⚠ No se pudieron obtener los detalles.")
            old = previous_data.get(key)
            if old:
                movies.append(old)
            else:
                movies.append({
                    "id": f"tmdb_{tmdb_id}",
                    "titulo": match.get("title") or title,
                    "titulo_original": match.get("original_title") or "",
                    "anio": year_from_date(match.get("release_date")),
                    "fecha_estreno": match.get("release_date"),
                    "duracion_minutos": None,
                    "generos": [],
                    "director": [],
                    "actores": [],
                    "sinopsis": match.get("overview") or "",
                    "poster": (
                        f"{IMAGE_BASE}/w500{match['poster_path']}"
                        if match.get("poster_path") else None
                    ),
                    "trailers": [],
                    "tmdb_id": tmdb_id,
                    "tmdb_url": f"https://www.themoviedb.org/movie/{tmdb_id}",
                    "fuente": "TMDB",
                    "titulo_cinemacenter": title,
                    "actualizado_at": datetime.now(timezone.utc).isoformat(),
                })
            unresolved.append(title)
            continue

        movies.append(build_movie(title, details, previous_data.get(key)))

    output = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "metadata": "TMDB",
            "cinema": "Cinemacenter",
            "tmdb_api": "https://developer.themoviedb.org/",
            "attribution_required": True,
            "attribution_notice": "This product uses the TMDB API but is not endorsed or certified by TMDB.",
        },
        "cinema_reference": {
            "week_start": cinema_data.get("cartelera", {}).get("week_start"),
            "week_end": cinema_data.get("cartelera", {}).get("week_end"),
        },
        "peliculas": movies,
        "summary": {
            "total": len(movies),
            "resueltas_tmdb": sum(1 for m in movies if m.get("tmdb_id")),
            "sinopsis_disponibles": sum(1 for m in movies if m.get("sinopsis")),
            "posters_disponibles": sum(1 for m in movies if m.get("poster")),
            "trailers_disponibles": sum(1 for m in movies if m.get("trailers")),
            "sin_resolver": unresolved,
        },
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print("=" * 70)
    print("RESULTADO")
    print("=" * 70)
    print(json.dumps(output["summary"], ensure_ascii=False, indent=2))
    print(f"Archivo: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
