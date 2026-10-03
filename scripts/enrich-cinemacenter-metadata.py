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
import os
import sys
import unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

BASE = "https://www.cinemacenter.com.ar"
CARTELERA_URL = f"{BASE}/cartelera#contenido"
ESTRENOS_URL = f"{BASE}/estrenos#contenido"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0 Safari/537.36 AgendaTucuman/1.0"
DIRECT_TIMEOUT = float(os.getenv("CINEMACENTER_DIRECT_TIMEOUT", "12"))
READER_TIMEOUT = int(os.getenv("CINEMACENTER_READER_TIMEOUT", "45"))
FETCH_MODE = os.getenv("CINEMACENTER_FETCH_MODE", "auto").lower()
READER_BASE = "https://r.jina.ai/"
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


def _fetch_direct(url: str) -> str:
    """Fetch Cinemacenter directly, trying both canonical hostnames.

    GitHub runners can receive a 403 from one hostname while the other is
    reachable. Both URLs still point directly to Cinemacenter; no external
    metadata provider is involved.
    """
    parsed = urlparse(url)
    variants = [url]
    if parsed.netloc == "www.cinemacenter.com.ar":
        variants.append(url.replace("https://www.cinemacenter.com.ar", "https://cinemacenter.com.ar", 1))
    elif parsed.netloc == "cinemacenter.com.ar":
        variants.append(url.replace("https://cinemacenter.com.ar", "https://www.cinemacenter.com.ar", 1))

    last_error = None
    for candidate in variants:
        req = Request(
            candidate,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "es-AR,es;q=0.9,en;q=0.7",
                "Referer": "https://www.cinemacenter.com.ar/",
                "Cache-Control": "no-cache",
            },
        )
        try:
            with urlopen(req, timeout=DIRECT_TIMEOUT) as response:
                raw = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                return raw.decode(charset, errors="replace")
        except Exception as exc:
            last_error = exc

    raise last_error or RuntimeError("falló la consulta directa")


def _fetch_reader(url: str) -> str:
    # GitHub-hosted runners can be unable to reach Cinemacenter directly.
    # Jina Reader acts only as an HTTP transport/proxy here; the content source
    # remains Cinemacenter. Request raw HTML so the existing parser keeps working.
    reader_url = READER_BASE + url
    req = Request(
        reader_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "X-Engine": "browser",
            "X-Timeout": str(READER_TIMEOUT),
            "X-No-Cache": "true",
        },
    )
    with urlopen(req, timeout=READER_TIMEOUT + 15) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        text = raw.decode(charset, errors="replace")
        if not text.strip():
            raise RuntimeError("Jina Reader devolvió una respuesta vacía")
        # With Accept: application/json Reader returns {url,title,content,...}.
        # Keep the content string because it is Markdown, not the original HTML.
        try:
            payload = json.loads(text)
            if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
                content = payload["data"].get("content")
                if content:
                    return str(content)
            if isinstance(payload, dict) and payload.get("content"):
                return str(payload["content"])
        except Exception:
            pass
        return text


def fetch(url: str) -> str:
    """Fetch content while keeping Cinemacenter as the only data source.

    `auto` is deliberately the default: direct Cinemacenter is attempted first
    and Jina Reader is only a transport fallback. The workflow must not force
    Jina because that service can return HTTP 403 for Cinemacenter.
    """
    errors = []
    if FETCH_MODE in {"auto", "direct"}:
        try:
            return _fetch_direct(url)
        except Exception as exc:
            errors.append(f"directo: {exc}")
            if FETCH_MODE == "direct":
                raise RuntimeError("No se pudo consultar Cinemacenter directamente: " + str(exc)) from exc
    if FETCH_MODE in {"auto", "jina", "reader"}:
        try:
            return _fetch_reader(url)
        except Exception as exc:
            errors.append(f"reader: {exc}")
    raise RuntimeError("No se pudo consultar Cinemacenter (" + "; ".join(errors) + ")")


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


class MarkdownParser:
    """Minimal parser for Jina Reader Markdown output.

    Jina Reader returns clean Markdown rather than the original HTML. We only
    need links, images and text for the Cinemacenter pages.
    """
    def __init__(self, source: str):
        self.source = source or ""
        self.links: list[tuple[str, str]] = []
        self.images: list[str] = []
        self.text = re.sub(r"\s+", " ", self.source).strip()
        for m in re.finditer(r"!?\[([^\]]*)\]\((https?://[^)\s]+)", self.source):
            label, url = m.group(1).strip(), m.group(2).strip()
            if m.group(0).startswith("!"):
                self.images.append(url)
            else:
                self.links.append((label, url))


def parse_markdown_links(source: str) -> list[tuple[str, str]]:
    parser = MarkdownParser(source)
    return parser.links


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


def classification_value(text: str) -> str | None:
    """Extract the age classification without swallowing the next metadata label."""
    labels = [
        "Género", "Generos", "Director", "Dirección", "Protagonistas",
        "Actores", "Reparto", "Duración", "Nacionalidad", "Origen",
        "País de origen", "Distribuidora", "Distribuidor", "Estreno",
        "Fecha de estreno", "Lanzamiento", "Sinopsis", "Tráiler",
        "Trailer", "Formato", "Horarios",
    ]
    stop = "|".join(re.escape(x) for x in labels)
    pattern = rf"Clasificación\s*[:\-]?\s*(.+?)(?=\s+(?:{stop})\s*[:\-]?|$)"
    m = re.search(pattern, text, re.I | re.S)
    if not m:
        return None
    value = re.sub(r"\s+", " ", m.group(1)).strip(" -:")
    return value or None


def parse_movie_page(url: str, expected_title: str) -> dict:
    source = fetch(url)
    # Direct Cinemacenter responses are HTML; Jina Reader responses are Markdown.
    looks_html = "<html" in source[:2000].lower() or "<meta" in source[:5000].lower()
    if not looks_html:
        return parse_movie_markdown(source, url, expected_title)

    parser = PageParser()
    parser.feed(source)
    json_items = parse_json_ld(parser)
    movie = next((x for x in json_items if str(x.get("@type", "")).lower() in {"movie", "movieevent"}), {})
    text = " ".join(parser.text_parts)

    title = first_nonempty(movie.get("name"), parser.metas.get("og:title"))
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

    original_title = first_nonempty(movie.get("alternateName"), parser.metas.get("movie:original_title"))
    classification = first_nonempty(movie.get("contentRating"), movie.get("rating"))
    if isinstance(original_title, list):
        original_title = original_title[0] if original_title else None

    result = {
        "title": str(title).strip() if title else None,
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
        "classification": None,
        "distributor": None,
    }
    if classification is not None:
        result["classification"] = str(classification).strip()
    for key, labels in {
        "nationality": ["Nacionalidad", "Origen", "País de origen"],
        "classification": ["Clasificación"],
        "distributor": ["Distribuidora", "Distribuidor"],
    }.items():
        value = classification_value(text) if key == "classification" else label_value(text, labels)
        if value:
            result[key] = value
    if movie.get("countryOfOrigin"):
        result["nationality"] = ", ".join(people(movie["countryOfOrigin"])) or str(movie["countryOfOrigin"])
    result["year"] = int(release_date[:4]) if release_date else None
    if not result.get("title") or not strict_title_match(expected_title, result["title"]):
        raise ValueError(f"La ficha de Cinemacenter no corresponde a '{expected_title}' (título leído: {result.get('title')!r})")
    return {k: v for k, v in result.items() if v not in (None, "", [], {})}


def markdown_label_value(text: str, labels: list[str]) -> str | None:
    # Handles both **Director:** X and plain "Director: X" in Reader Markdown.
    joined = "|".join(re.escape(x) for x in labels)
    patterns = [
        rf"(?:^|\n|\s)(?:\*\*)?(?:{joined})(?:\*\*)?\s*[:\-]\s*([^\n]+)",
        rf"(?:{joined})\s+([^\n|]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            value = re.sub(r"\*+", "", m.group(1)).strip(" -:")
            if value:
                return value
    return None


def parse_movie_markdown(source: str, url: str, expected_title: str) -> dict:
    text = source or ""
    links = parse_markdown_links(text)
    images = MarkdownParser(text).images

    # Reader may expose OpenGraph values as metadata text or as headings.
    title = None
    m = re.search(r"(?im)^#\s+(.+?)\s*$", text)
    if m:
        title = re.sub(r"[*_`]+", "", m.group(1)).strip()
    description = markdown_label_value(text, ["Sinopsis", "Descripción", "Descripcion"])
    if not description:
        # Cinemacenter fichas normally put the synopsis after a heading.
        m = re.search(r"(?is)(?:^|\n)#{1,4}\s*(?:Sinopsis|Descripción|Descripcion)\s*\n(.+?)(?:\n#{1,4}\s|$)", text)
        if m:
            description = re.sub(r"\s+", " ", m.group(1)).strip()

    release_date = clean_date(markdown_label_value(text, ["Fecha de estreno", "Estreno", "Lanzamiento"]))
    duration = parse_duration(markdown_label_value(text, ["Duración", "Duracion"]))
    director_text = markdown_label_value(text, ["Director"])
    cast_text = markdown_label_value(text, ["Protagonistas", "Actores", "Reparto"])
    genre_text = markdown_label_value(text, ["Género", "Genero", "Generos"])
    nationality = markdown_label_value(text, ["Nacionalidad", "Origen", "País de origen"])
    classification = markdown_label_value(text, ["Clasificación"])
    if not classification:
        classification = markdown_label_value(text, ["Calificación"])
    if classification:
        classification = re.sub(r"\s+", " ", classification).strip(" -:")
    distributor = markdown_label_value(text, ["Distribuidora", "Distribuidor"])
    original_title = markdown_label_value(text, ["Título original", "Titulo original"])

    # Prefer a Cinemacenter image from Markdown. Avoid generic logos.
    poster = next((u for u in images if any(x in u.lower() for x in ["cartel", "poster", "pelicula", "ficha", "movie"]) and "logo" not in u.lower()), None)
    if not poster and images:
        poster = next((u for u in images if "logo" not in u.lower()), images[0])

    trailer = next((u for label, u in links if "trailer" in normalize(label)), None)
    genres = [x.strip() for x in re.split(r",|/| y |·", genre_text or "") if x.strip()]
    director = [x.strip() for x in re.split(r",| y ", director_text or "") if x.strip()]
    cast = [x.strip() for x in re.split(r",| y ", cast_text or "") if x.strip()]

    result = {
        "title": title,
        "source_url": url,
        "original_title": original_title,
        "release_date": release_date,
        "duration_minutes": duration,
        "genres": list(dict.fromkeys(genres)),
        "director": list(dict.fromkeys(director)),
        "cast": list(dict.fromkeys(cast)),
        "synopsis": description,
        "poster": poster,
        "trailer": trailer,
        "nationality": nationality,
        "classification": classification,
        "distributor": distributor,
        "year": int(release_date[:4]) if release_date else None,
    }
    if not result.get("title") or not strict_title_match(expected_title, result["title"]):
        raise ValueError(f"La ficha de Cinemacenter no corresponde a '{expected_title}' (título leído: {result.get('title')!r})")
    return {k: v for k, v in result.items() if v not in (None, "", [], {})}


def title_variants(value: str) -> set[str]:
    """Return conservative variants that still identify the same movie title."""
    raw = re.sub(r"\s+", " ", str(value or "")).strip()
    variants = set()

    def add(v: str) -> None:
        v = normalize(v)
        v = re.sub(r"\s+", " ", v).strip()
        if v:
            variants.add(v)

    add(raw)
    # Cinemacenter may append these to the displayed title.
    add(re.sub(r"\s+(la pelicula|la película|the movie)\s*$", "", raw, flags=re.I))
    # The PDF/cartelera can use a colon where the ficha uses a space, but we
    # do NOT reduce a title to only one token. That is what caused false
    # positives such as VERTIGO 2 -> U2 VERTIGO.
    add(raw.replace(":", " "))
    return variants


def strict_title_match(expected: str, actual: str) -> bool:
    expected_variants = title_variants(expected)
    actual_variants = title_variants(actual)
    if not expected_variants or not actual_variants:
        return False
    return bool(expected_variants & actual_variants)


def candidate_score(title: str, link_text: str, url: str) -> int:
    """Score ONLY exact/near-exact Cinemacenter ficha titles.

    A candidate must match the complete movie title after conservative
    normalization. Token overlap is intentionally not used: it can associate
    a movie with an unrelated page such as U2 / Vertigo.
    """
    expected = title_variants(title)
    actual = title_variants(link_text)
    if not expected or not actual:
        return 0
    if expected & actual:
        return 100

    # Some pages have no visible anchor text. In that case use the final URL
    # slug, but only if the complete normalized slug matches the full title.
    slug = urlparse(url).path.rsplit("/", 1)[-1]
    slug = re.sub(r"\.(html?|php)$", "", slug, flags=re.I)
    if strict_title_match(title, slug.replace("-", " ")):
        return 90
    return 0


def find_movie_url(parser, title: str) -> str | None:
    if parser is None:
        return None
    links = parser.links if hasattr(parser, "links") else parse_markdown_links(getattr(parser, "source", ""))
    candidates = []
    for text, url in links:
        if urlparse(url).netloc and urlparse(url).netloc.lower() not in {"www.cinemacenter.com.ar", "cinemacenter.com.ar"}:
            continue
        path = urlparse(url).path.lower()
        if not ("/ficha" in path or "/ficham" in path or "/pelicula" in path or "/movie" in path):
            continue
        score = candidate_score(title, text, url)
        if score:
            candidates.append((score, url, text))

    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best = candidates[0]
    # Never accept an ambiguous candidate.
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0] and candidates[0][1] != candidates[1][1]:
        return None
    return best[1]


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


def _section_movies(cinema: dict) -> list[tuple[str, dict]]:
    """Return current cartelera + upcoming releases with explicit section labels."""
    result: list[tuple[str, dict]] = []
    cartelera = cinema.get("cartelera") or {}
    for movie in cartelera.get("movies") or []:
        if isinstance(movie, dict):
            result.append(("cartelera", movie))

    upcoming = cinema.get("proximos_estrenos")
    # Support both a direct list and a common nested {"movies": [...]} shape.
    if isinstance(upcoming, dict):
        upcoming = upcoming.get("movies") or upcoming.get("estrenos") or []
    if isinstance(upcoming, list):
        for movie in upcoming:
            if isinstance(movie, dict):
                result.append(("proximos_estrenos", movie))
    return result


def _load_page_parser(source: str):
    if "<html" in source[:2000].lower() or "<meta" in source[:5000].lower():
        parser = PageParser()
        parser.feed(source)
        return parser
    return MarkdownParser(source)


def _fetch_section_parser(url: str, label: str):
    source = fetch(url)
    parser = _load_page_parser(source)
    print(f"{label} Cinemacenter consultada para localizar fichas exactas.")
    return parser


def _build_result(movie: dict, section: str, fresh: dict, url: str | None) -> dict:
    title = str(movie.get("title") or "").strip()
    result = {
        "title": title,
        "match": [title],
        "source": "Cinemacenter",
        "section": section,
    }

    # Preserve fields explicitly supplied by the current extractor first.
    embedded = movie.get("metadata")
    if isinstance(embedded, dict):
        for key, value in embedded.items():
            if key not in {"title", "match"} and value not in (None, "", [], {}):
                result[key] = value

    # Fresh Cinemacenter ficha data wins over embedded metadata.
    result.update({
        k: v for k, v in fresh.items()
        if k not in {"title", "source_url"} and v not in (None, "", [], {})
    })
    if url:
        result["source_url"] = url

    # Keep classification/rating supplied by the official current JSON if present.
    for field in ("classification", "rating"):
        if movie.get(field) not in (None, "", [], {}):
            result[field] = movie[field]

    required = [
        "title", "original_title", "year", "release_date", "duration_minutes",
        "genres", "director", "cast", "synopsis", "poster",
    ]
    missing = [field for field in required if result.get(field) in (None, "", [], {})]
    if not result.get("classification"):
        missing.append("classification")
    result["metadata_status"] = "complete" if not missing else "partial"
    result["metadata_missing"] = missing
    return result


def main() -> int:
    cinema = load_json(LOCAL_CINEMA, None)
    if not cinema or not isinstance(cinema.get("cartelera", {}).get("movies"), list):
        print("No se encontró una cartelera local válida", file=sys.stderr)
        return 1

    section_movies = _section_movies(cinema)
    if not section_movies:
        print("No se encontraron películas de cartelera ni próximos estrenos.")
        return 1

    # Query both Cinemacenter sections. A temporary failure in one section must
    # not erase data already obtained from the other section.
    parsers: dict[str, object] = {}
    for section, url, label in (
        ("cartelera", CARTELERA_URL, "Cartelera"),
        ("proximos_estrenos", ESTRENOS_URL, "Estrenos"),
    ):
        try:
            parsers[section] = _fetch_section_parser(url, label)
        except Exception as exc:
            print(f"ADVERTENCIA: no se pudo consultar {label} de Cinemacenter: {exc}", file=sys.stderr)

    if not parsers:
        print("ERROR: no se pudo consultar ninguna sección de Cinemacenter.", file=sys.stderr)
        return 1

    enriched: list[dict] = []
    seen: set[tuple[str, str]] = set()
    failures: list[str] = []
    complete = 0
    partial = 0

    for section, movie in section_movies:
        title = str(movie.get("title") or "").strip()
        key = normalize(title)
        identity = (section, key)
        if not key or identity in seen:
            continue
        seen.add(identity)

        parser = parsers.get(section)
        url = find_movie_url(parser, title) if parser else None
        fresh: dict = {}

        if url:
            print(f"  > [{section}] {title}: ficha candidata exacta -> {url}")
            try:
                fresh = parse_movie_page(url, title)
            except Exception as exc:
                failures.append(f"[{section}] {title}: {exc}")
                print(f"  ! [{section}] {title}: {exc}")
        else:
            failures.append(f"[{section}] {title}: no se encontró una ficha exacta en Cinemacenter")
            print(f"  ! [{section}] {title}: no se encontró una ficha exacta en Cinemacenter")

        result = _build_result(movie, section, fresh, url)
        enriched.append(result)

        if result["metadata_status"] == "complete":
            complete += 1
        else:
            partial += 1

    metadata = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "source_policy": (
            "Cinemacenter is the primary source. Current cartelera and upcoming "
            "releases are processed separately; no external metadata is added here."
        ),
        "source": {
            "cartelera": CARTELERA_URL,
            "proximos_estrenos": ESTRENOS_URL,
        },
        "movies": enriched,
        "summary": {
            "total": len(enriched),
            "cartelera": sum(1 for x in enriched if x.get("section") == "cartelera"),
            "proximos_estrenos": sum(1 for x in enriched if x.get("section") == "proximos_estrenos"),
            "complete": complete,
            "partial": partial,
            "resolved_this_run": sum(1 for item in enriched if item.get("source_url")),
            "still_missing": sum(len(item.get("metadata_missing") or []) for item in enriched),
        },
    }

    # Inject metadata back into both current JSON sections.
    matches = {
        (item.get("section"), normalize(item.get("title"))): item
        for item in enriched
    }
    for section, movie in section_movies:
        key = (section, normalize(movie.get("title")))
        match = matches.get(key)
        if match:
            movie["metadata"] = {k: v for k, v in match.items() if k != "match"}

    write_json(LOCAL_METADATA, metadata)
    write_json(LOCAL_CINEMA, cinema)
    if REPO_DATA_DIR.exists():
        write_json(REPO_METADATA, metadata)
        write_json(REPO_CINEMA, cinema)

    print("")
    print("==============================================")
    print("RESUMEN DE METADATA CINEMACENTER")
    print("==============================================")
    print(f"Películas procesadas: {len(enriched)}")
    print(f"  Cartelera: {metadata['summary']['cartelera']}")
    print(f"  Próximos estrenos: {metadata['summary']['proximos_estrenos']}")
    print(f"Completas: {complete}")
    print(f"Parciales: {partial}")
    print(f"Fichas exactas encontradas: {metadata['summary']['resolved_this_run']}")
    print("")

    for item in enriched:
        missing = ", ".join(item.get("metadata_missing") or []) or "ninguno"
        print(
            f"- [{item.get('section')}] {item.get('title')}: "
            f"{item.get('metadata_status')}; faltan: {missing}"
        )

    if failures:
        print("")
        print("AVISOS:")
        for failure in failures:
            print(f"  - {failure}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
