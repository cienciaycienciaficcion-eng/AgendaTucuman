#!/usr/bin/env python3
"""Complete missing Cinemacenter movie metadata using TMDB.

This script is GitHub-side only.  It never runs from the APK.

Order of trust:
  1. Existing Cinemacenter metadata is preserved.
  2. Missing fields are filled from TMDB.
  3. Argentina release certification from TMDB is used for `classification`.

The current cartelera is the authoritative list: movies that disappear from
Cinemacenter are removed from cine_metadata.json; if they return later they are
resolved again.
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

ROOT = Path(__file__).resolve().parents[1]
REPO_CINEMA = ROOT / "datos" / "cine_cinemacenter_tucuman.json"
REPO_METADATA = ROOT / "datos" / "cine_metadata.json"
LOCAL_CINEMA = ROOT / "src" / "data" / "cine_cinemacenter_tucuman.json"
LOCAL_METADATA = ROOT / "src" / "data" / "cine_metadata.json"

BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p"
TIMEOUT = 25
SLEEP = 0.15

REQUIRED_FIELDS = (
    "title",
    "year",
    "release_date",
    "duration_minutes",
    "genres",
    "director",
    "cast",
    "synopsis",
    "poster",
)


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"ADVERTENCIA: no se pudo leer {path}: {exc}")
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def year_from_date(value: str | None) -> int | None:
    if not value or len(value) < 4:
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None


def tmdb_request(session: requests.Session, path: str, params: dict[str, Any]) -> dict[str, Any] | None:
    token = os.environ.get("TMDB_API_TOKEN", "").strip()
    if not token:
        return None

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    try:
        response = session.get(
            f"{BASE_URL}{path}",
            params=params,
            headers=headers,
            timeout=TIMEOUT,
        )
        if response.status_code == 429:
            retry_after = min(int(response.headers.get("Retry-After", "2")), 10)
            print(f"  TMDB rate limit; esperando {retry_after}s...")
            time.sleep(retry_after)
            response = session.get(
                f"{BASE_URL}{path}",
                params=params,
                headers=headers,
                timeout=TIMEOUT,
            )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        print(f"  TMDB {path}: {exc}")
        return None


def title_variants(title: str) -> list[str]:
    """Generate conservative search variants for Cinemacenter titles."""
    raw = re.sub(r"\s+", " ", title or "").strip()
    variants: list[str] = []

    def add(value: str) -> None:
        value = re.sub(r"\s+", " ", value).strip(" :-–—")
        if value and value not in variants:
            variants.append(value)

    add(raw)
    add(re.sub(r"\s*[:|]\s*", " ", raw))
    # Cinemacenter frequently appends these Spanish/English descriptors.
    stripped = re.sub(r"\s+(la\s+pel[ií]cula|the\s+movie)\s*$", "", raw, flags=re.I)
    add(stripped)
    add(re.sub(r"\s*[:|]\s*", " ", stripped))

    # If a colon is present, search the main title as a last resort.
    if ":" in stripped:
        add(stripped.split(":", 1)[0])

    # Cinemacenter often uses a Spanish subtitle after " LA ...".
    # Search the principal title as an additional, conservative variant.
    parts = re.split(r"\s+LA\s+", stripped, maxsplit=1, flags=re.I)
    if len(parts) == 2 and len(parts[0].split()) <= 6:
        add(parts[0])

    # Search a compact form without accents/punctuation.
    add(normalize(stripped))
    return variants


def choose_result(query: str, results: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not results:
        return None

    nq = normalize(query)
    q_words = set(nq.split())

    def score(item: dict[str, Any]) -> float:
        title = normalize(item.get("title"))
        original = normalize(item.get("original_title"))
        title_words = set(title.split())
        original_words = set(original.split())
        candidates = [title, original]
        value = 0.0

        if title == nq:
            value += 140
        elif original == nq:
            value += 138
        elif nq and nq in candidates:
            value += 105
        elif nq and any(nq in c or c in nq for c in candidates if c):
            value += 78

        overlaps = []
        for words in (title_words, original_words):
            if words:
                overlaps.append(len(q_words & words) / max(1, len(q_words)))
        overlap = max(overlaps or [0.0])
        value += overlap * 55

        # Penalize a result that only matches one tiny word of a long title.
        if len(q_words) >= 3 and overlap < 0.50:
            value -= 30

        popularity = float(item.get("popularity") or 0)
        value += min(popularity, 20) / 20
        return value

    ranked = sorted(results, key=score, reverse=True)
    best = ranked[0]
    best_score = score(best)

    # Conservative threshold: don't attach metadata to a clearly unrelated movie.
    if best_score < 70:
        return None
    return best


def search_movie(session: requests.Session, title: str) -> dict[str, Any] | None:
    all_results: list[dict[str, Any]] = []
    seen: set[int] = set()

    for variant in title_variants(title):
        for language, region in (("es-AR", "AR"), ("en-US", "AR")):
            data = tmdb_request(
                session,
                "/search/movie",
                {
                    "query": variant,
                    "language": language,
                    "region": region,
                    "include_adult": "false",
                    "page": 1,
                },
            )
            if data:
                for item in data.get("results", []):
                    movie_id = item.get("id")
                    if movie_id and movie_id not in seen:
                        seen.add(movie_id)
                        all_results.append(item)
            time.sleep(SLEEP)

        # If an exact/strong result is already present, stop issuing requests.
        candidate = choose_result(title, all_results)
        if candidate:
            return candidate

    return choose_result(title, all_results)

def get_details(session: requests.Session, movie_id: int) -> dict[str, Any] | None:
    data = tmdb_request(
        session,
        f"/movie/{movie_id}",
        {
            "language": "es-AR",
            "append_to_response": "credits,videos,external_ids",
            "include_image_language": "es,null,en",
        },
    )
    time.sleep(SLEEP)
    return data


def get_argentina_certification(session: requests.Session, movie_id: int) -> str | None:
    data = tmdb_request(session, f"/movie/{movie_id}/release_dates", {})
    time.sleep(SLEEP)
    if not data:
        return None

    for country in data.get("results", []):
        if country.get("iso_3166_1") != "AR":
            continue
        dates = country.get("release_dates") or []
        # Prefer entries that actually contain a certification.
        for entry in dates:
            cert = str(entry.get("certification") or "").strip()
            if cert:
                return cert
    return None


def build_tmdb(details: dict[str, Any], certification: str | None) -> dict[str, Any]:
    release_date = details.get("release_date") or None

    genres = [
        g.get("name")
        for g in details.get("genres", [])
        if g.get("name")
    ]

    directors: list[str] = []
    seen_directors: set[str] = set()
    for person in details.get("credits", {}).get("crew", []):
        if person.get("job") != "Director":
            continue
        name = person.get("name")
        if name and name not in seen_directors:
            seen_directors.add(name)
            directors.append(name)

    cast: list[str] = []
    seen_cast: set[str] = set()
    for person in details.get("credits", {}).get("cast", [])[:20]:
        name = person.get("name")
        if name and name not in seen_cast:
            seen_cast.add(name)
            cast.append(name)

    poster_path = details.get("poster_path")
    poster = f"{IMAGE_BASE}/w500{poster_path}" if poster_path else None

    trailers = details.get("videos", {}).get("results", [])
    trailer_url = None
    ranked = sorted(
        trailers,
        key=lambda v: (
            (v.get("site") or "").lower() == "youtube",
            (v.get("type") or "").lower() == "trailer",
            bool(v.get("official")),
            (v.get("iso_3166_1") or "").upper() == "AR",
        ),
        reverse=True,
    )
    for video in ranked:
        if (video.get("site") or "").lower() == "youtube" and video.get("key"):
            trailer_url = f"https://www.youtube.com/watch?v={video['key']}"
            break

    result = {
        "title": details.get("title"),
        "original_title": details.get("original_title"),
        "year": year_from_date(release_date),
        "release_date": release_date,
        "duration_minutes": details.get("runtime"),
        "genres": genres,
        "director": directors,
        "cast": cast,
        "synopsis": details.get("overview") or None,
        "poster": poster,
        "trailer": trailer_url,
        "tmdb_id": details.get("id"),
        "tmdb_url": f"https://www.themoviedb.org/movie/{details.get('id')}" if details.get("id") else None,
        "imdb_id": (details.get("external_ids") or {}).get("imdb_id"),
        "imdb_url": (
            f"https://www.imdb.com/title/{(details.get("external_ids") or {}).get("imdb_id")}/"
            if (details.get("external_ids") or {}).get("imdb_id") else None
        ),
    }

    if certification:
        result["classification"] = certification
        result["rating"] = certification
        result["classification_source"] = "TMDB / Argentina"

    return {k: v for k, v in result.items() if v not in (None, "", [], {})}


def is_missing(value: Any) -> bool:
    return value in (None, "", [], {})


def metadata_complete(item: dict[str, Any]) -> bool:
    return all(not is_missing(item.get(field)) for field in REQUIRED_FIELDS)


def missing_fields(item: dict[str, Any]) -> list[str]:
    fields = list(REQUIRED_FIELDS)
    if is_missing(item.get("classification")):
        fields.append("classification")
    return [field for field in fields if is_missing(item.get(field))]


def main() -> int:
    token = os.environ.get("TMDB_API_TOKEN", "").strip()
    if not token:
        print("TMDB_API_TOKEN no está configurado; se omite el fallback de metadata.")
        return 0

    cinema = load_json(REPO_CINEMA, None)
    if not cinema:
        print(f"ERROR: no existe una cartelera válida en {REPO_CINEMA}", file=sys.stderr)
        return 1

    movies = (cinema.get("cartelera") or {}).get("movies") or []
    if not movies:
        print("La cartelera actual está vacía; no se modifica cine_metadata.json.")
        return 0

    metadata = load_json(REPO_METADATA, {"movies": []})
    previous = metadata.get("movies", []) if isinstance(metadata, dict) else []

    by_alias: dict[str, dict[str, Any]] = {}
    for item in previous:
        for alias in [*(item.get("match") or []), item.get("title"), item.get("original_title")]:
            if alias:
                by_alias[normalize(alias)] = item

    titles: list[str] = []
    seen_titles: set[str] = set()
    for movie in movies:
        title = str(movie.get("title") or "").strip()
        key = normalize(title)
        if title and key not in seen_titles:
            seen_titles.add(key)
            titles.append(title)

    session = requests.Session()
    enriched: list[dict[str, Any]] = []
    resolved = 0
    unresolved = 0

    print("=" * 70)
    print("COMPLETAR METADATA FALTANTE CON TMDB")
    print("=" * 70)

    for title in titles:
        key = normalize(title)
        old = dict(by_alias.get(key) or {})
        current = dict(old)
        current.setdefault("title", title)

        missing_before = missing_fields(current)
        if not missing_before:
            current["metadata_status"] = "complete"
            current["metadata_missing"] = []
            current["sources_checked"] = list(dict.fromkeys([*(current.get("sources_checked") or []), "Cinemacenter", "TMDB"]))
            enriched.append(current)
            print(f"= {title}: completa; no se modifica.")
            continue

        result = search_movie(session, title)
        if not result:
            current["metadata_status"] = "partial"
            current["metadata_missing"] = missing_before
            current["sources_checked"] = list(dict.fromkeys([*(current.get("sources_checked") or []), "Cinemacenter", "TMDB"]))
            enriched.append(current)
            unresolved += 1
            print(f"? {title}: TMDB no encontró una coincidencia segura; faltan {', '.join(missing_before)}")
            continue

        details = get_details(session, int(result["id"]))
        if not details:
            current["metadata_status"] = "partial"
            current["metadata_missing"] = missing_before
            current["sources_checked"] = list(dict.fromkeys([*(current.get("sources_checked") or []), "Cinemacenter", "TMDB"]))
            enriched.append(current)
            unresolved += 1
            print(f"? {title}: TMDB encontró la película pero no devolvió detalles.")
            continue

        certification = get_argentina_certification(session, int(result["id"]))
        fresh = build_tmdb(details, certification)

        # TMDB solo rellena huecos. No pisa información ya obtenida de Cinemacenter.
        for field, value in fresh.items():
            if is_missing(current.get(field)) and not is_missing(value):
                current[field] = value

        aliases = list(dict.fromkeys([
            *(current.get("match") or []),
            title,
            current.get("title") or title,
            current.get("original_title") or "",
        ]))
        current["match"] = [x for x in aliases if x]
        current["source"] = "Cinemacenter + TMDB"
        current["sources_checked"] = list(dict.fromkeys([*(current.get("sources_checked") or []), "Cinemacenter", "TMDB"]))
        current["metadata_missing"] = missing_fields(current)
        current["metadata_status"] = "complete" if not current["metadata_missing"] else "partial"
        current["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

        if current["metadata_status"] == "complete":
            resolved += 1
        else:
            unresolved += 1
        enriched.append(current)

        print(
            f"+ {title}: {current['metadata_status']}"
            f"; faltan: {', '.join(current['metadata_missing']) if current['metadata_missing'] else 'ninguno'}"
        )

    output = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "source_policy": (
            "Cinemacenter is the primary movie-metadata source; TMDB fills only missing fields. "
            "Existing values are preserved."
        ),
        "source": "https://www.cinemacenter.com.ar/cartelera#contenido",
        "movies": enriched,
    }

    # Keep a useful top-level summary for the workflow/logs without changing
    # the schema consumed by the app.
    output["summary"] = {
        "total": len(enriched),
        "complete": sum(1 for x in enriched if x.get("metadata_status") == "complete"),
        "partial": sum(1 for x in enriched if x.get("metadata_status") == "partial"),
        "resolved_this_run": resolved,
        "still_missing": unresolved,
    }

    write_json(REPO_METADATA, output)
    write_json(LOCAL_METADATA, output)

    print("=" * 70)
    print(f"Metadata final: {len(enriched)} películas")
    print(f"Completas: {output['summary']['complete']}")
    print(f"Parciales: {output['summary']['partial']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
