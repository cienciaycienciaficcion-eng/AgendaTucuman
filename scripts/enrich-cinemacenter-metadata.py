#!/usr/bin/env python3
"""Enrich Cinemacenter cartelera JSON with metadata from Cinemacenter movie pages.

Primary source: cinemacenter.com.ar.
The script is intentionally dependency-free so it can run in GitHub Actions.
It preserves previous metadata when a field cannot be read from the site.
"""
from __future__ import annotations

import html
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

BASE = "https://www.cinemacenter.com.ar"
CARTELERA_URL = f"{BASE}/cartelera#contenido"
USER_AGENT = "AgendaTucuman/1.0 (+https://github.com/cienciaycienciaficcion-eng/AgendaTucuman)"
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "src" / "data"
LOCAL_CINEMA = DATA_DIR / "cine_cinemacenter_tucuman.json"
LOCAL_METADATA = DATA_DIR / "cine_metadata.json"
REPO_DATA_DIR = ROOT / "datos"
REPO_CINEMA = REPO_DATA_DIR / "cine_cinemacenter_tucuman.json"
REPO_METADATA = REPO_DATA_DIR / "cine_metadata.json"


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower().replace("&", " y ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch(url: str) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with urlopen(req, timeout=30) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.metas: dict[str, str] = {}
        self.json_ld: list[str] = []
        self.text_parts: list[str] = []
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []
        self._script_type: str | None = None
        self._script_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self._anchor_href = a["href"]
            self._anchor_text = []
        if tag == "meta":
            key = a.get("property") or a.get("name") or a.get("itemprop")
            if key and a.get("content"):
                self.metas[key.lower()] = a["content"]
        if tag == "script":
            self._script_type = (a.get("type") or "").lower()
            self._script_text = []

    def handle_data(self, data: str) -> None:
        if self._anchor_href is not None:
            self._anchor_text.append(data)
        if self._script_type == "application/ld+json":
            self._script_text.append(data)
        else:
            cleaned = re.sub(r"\s+", " ", data).strip()
            if cleaned:
                self.text_parts.append(cleaned)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor_href is not None:
            text = re.sub(r"\s+", " ", " ".join(self._anchor_text)).strip()
            self.links.append((text, urljoin(BASE, self._anchor_href)))
            self._anchor_href = None
            self._anchor_text = []
        if tag == "script":
            if self._script_type == "application/ld+json" and self._script_text:
                self.json_ld.append("".join(self._script_text))
            self._script_type = None
            self._script_text = []


def parse_json_ld(parser: PageParser) -> list[dict]:
    out: list[dict] = []
    for raw in parser.json_ld:
        try:
            value = json.loads(html.unescape(raw))
        except Exception:
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, dict) and isinstance(item.get("@graph"), list):
                values.extend(x for x in item["@graph"] if isinstance(x, dict))
            elif isinstance(item, dict):
                out.append(item)
    return out


def first_nonempty(*values):
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, list) and not value:
            continue
        return value
    return None


def people(value) -> list[str]:
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, str):
                result.append(item.strip())
            elif isinstance(item, dict) and item.get("name"):
                result.append(str(item["name"]).strip())
        return list(dict.fromkeys(x for x in result if x))
    if isinstance(value, dict) and value.get("name"):
        return [str(value["name"]).strip()]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return []


def parse_duration(value: object) -> int | None:
    if value is None:
        return None
    text = str(value)
    m = re.search(r"PT(?:(\d+)H)?(?:(\d+)M)?", text, re.I)
    if m:
        return (int(m.group(1) or 0) * 60) + int(m.group(2) or 0)
    m = re.search(r"(\d+)\s*h(?:oras?)?\s*(?:(\d+)\s*m(?:in)?)?", text, re.I)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2) or 0)
    m = re.search(r"(\d{2,3})\s*(?:min|mins|minutos)", text, re.I)
    if m:
        return int(m.group(1))
    return None


def clean_date(value: object) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    m = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](20\d{2})", text)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return None


def label_value(text: str, labels: list[str]) -> str | None:
    pattern = r"(?:" + "|".join(re.escape(x) for x in labels) + r")\s*[:\-]?\s*([^\n|]+)"
    m = re.search(pattern, text, re.I)
    return m.group(1).strip() if m else None


def parse_movie_page(url: str, expected_title: str) -> dict:
    parser = PageParser()
    source = fetch(url)
    parser.feed(source)
    json_items = parse_json_ld(parser)
    movie = next((x for x in json_items if str(x.get("@type", "")).lower() in {"movie", "movieevent"}), {})
    text = " ".join(parser.text_parts)

    title = first_nonempty(movie.get("name"), parser.metas.get("og:title"), expected_title)
    image = first_nonempty(movie.get("image"), parser.metas.get("og:image"))
    if isinstance(image, list):
        image = image[0] if image else None
    description = first_nonempty(movie.get("description"), parser.metas.get("description"), parser.metas.get("og:description"))
    director = people(movie.get("director"))
    cast = people(movie.get("actor"))
    genres = movie.get("genre") or []
    if isinstance(genres, str):
        genres = [genres]
    release_date = clean_date(first_nonempty(movie.get("dateCreated"), movie.get("datePublished"), movie.get("releaseDate")))
    if not release_date:
        release_date = clean_date(label_value(text, ["Fecha de estreno", "Estreno", "Lanzamiento"]))
    duration = parse_duration(first_nonempty(movie.get("duration"), label_value(text, ["Duración"])))

    if not director:
        director = [x.strip() for x in re.split(r",| y ", label_value(text, ["Director"]) or "") if x.strip()]
    if not cast:
        cast = [x.strip() for x in re.split(r",| y ", label_value(text, ["Protagonistas", "Actores", "Reparto"]) or "") if x.strip()]
    if not genres:
        g = label_value(text, ["Género", "Generos"])
        genres = [x.strip() for x in re.split(r",|/| y |·", g or "") if x.strip()]

    original_title = first_nonempty(movie.get("alternateName"), parser.metas.get("og:site_name"))
    if isinstance(original_title, list):
        original_title = original_title[0] if original_title else None

    result = {
        "title": str(title).strip() if title else expected_title,
        "source_url": url,
        "original_title": str(original_title).strip() if original_title else None,
        "release_date": release_date,
        "duration_minutes": duration,
        "genres": list(dict.fromkeys(genres)),
        "director": director,
        "cast": cast,
        "synopsis": str(description).strip() if description else None,
        "poster": urljoin(url, str(image)) if image else None,
        "trailer": movie.get("trailer", {}).get("url") if isinstance(movie.get("trailer"), dict) else (movie.get("trailer") if isinstance(movie.get("trailer"), str) else None),
        "nationality": None,
        "rating": None,
        "distributor": None,
    }

    for key, labels in {
        "nationality": ["Nacionalidad", "Origen", "País de origen"],
        "rating": ["Calificación", "Clasificación"],
        "distributor": ["Distribuidora", "Distribuidor"],
    }.items():
        value = label_value(text, labels)
        if value:
            result[key] = value

    if movie.get("countryOfOrigin"):
        result["nationality"] = ", ".join(people(movie["countryOfOrigin"])) or str(movie["countryOfOrigin"])

    year = None
    if release_date:
        year = int(release_date[:4])
    result["year"] = year
    return {k: v for k, v in result.items() if v not in (None, "", [], {})}


def candidate_score(title: str, link_text: str, url: str) -> int:
    a = normalize(title)
    b = normalize(link_text + " " + url)
    if not a or not b:
        return 0
    if a == b:
        return 100
    score = 0
    tokens = [x for x in a.split() if len(x) > 2]
    for token in tokens:
        if token in b:
            score += 10
    if a in b:
        score += 40
    if "/ficha" in url.lower():
        score += 10
    return score


def find_movie_url(parser: PageParser, title: str) -> str | None:
    candidates = []
    for text, url in parser.links:
        path = urlparse(url).path.lower()
        if "/ficha" not in path:
            continue
        score = candidate_score(title, text, url)
        if score:
            candidates.append((score, url))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    cinema = load_json(LOCAL_CINEMA, None)
    if not cinema or not isinstance(cinema.get("cartelera", {}).get("movies"), list):
        print("No se encontró una cartelera local válida", file=sys.stderr)
        return 1

    try:
        cartelera_html = fetch(CARTELERA_URL)
    except Exception as exc:
        print(f"No se pudo consultar Cinemacenter: {exc}", file=sys.stderr)
        return 1

    cartelera_parser = PageParser()
    cartelera_parser.feed(cartelera_html)
    previous = load_json(LOCAL_METADATA, {"movies": []})
    previous_movies = previous.get("movies", []) if isinstance(previous, dict) else []
    by_title = {}
    for item in previous_movies:
        for alias in item.get("match", []) + [item.get("title"), item.get("original_title")]:
            if alias:
                by_title[normalize(alias)] = item

    enriched = []
    seen = set()
    failures = []
    for movie in cinema["cartelera"]["movies"]:
        title = str(movie.get("title") or "").strip()
        key = normalize(title)
        if not key or key in seen:
            continue
        seen.add(key)
        old = by_title.get(key, {})
        url = find_movie_url(cartelera_parser, title)
        fresh = {}
        if url:
            try:
                fresh = parse_movie_page(url, title)
            except Exception as exc:
                failures.append(f"{title}: {exc}")
        else:
            failures.append(f"{title}: no se encontró ficha en la cartelera")

        merged = dict(old)
        merged.update({k: v for k, v in fresh.items() if v not in (None, "", [], {})})
        aliases = list(dict.fromkeys([*(old.get("match") or []), title, merged.get("title", title), merged.get("original_title", "")]))
        merged["match"] = [x for x in aliases if x]
        merged["source"] = "Cinemacenter"
        enriched.append(merged)

    metadata = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "source_policy": "Cinemacenter is the primary movie-metadata source; previous metadata is retained when a field is unavailable.",
        "source": CARTELERA_URL,
        "movies": enriched,
    }

    # Inject metadata into the remote cinema JSON too, so the app no longer needs a
    # separate manual metadata table for current films.
    for movie in cinema["cartelera"]["movies"]:
        key = normalize(movie.get("title"))
        match = next((x for x in enriched if key in {normalize(a) for a in x.get("match", [])}), None)
        if match:
            movie["metadata"] = {k: v for k, v in match.items() if k != "match"}

    write_json(LOCAL_METADATA, metadata)
    write_json(LOCAL_CINEMA, cinema)
    if REPO_DATA_DIR.exists():
        write_json(REPO_METADATA, metadata)
        write_json(REPO_CINEMA, cinema)

    print(f"Metadata Cinemacenter actualizada: {len(enriched)} películas")
    if failures:
        print("Avisos:")
        for item in failures:
            print(f"  - {item}")
        # Partial enrichment is useful; keep the workflow green so existing data remains deployable.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
