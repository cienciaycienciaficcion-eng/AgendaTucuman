#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AGENDA TUCUMÁN - EXTRACTOR UNIFICADO DE CINEMACENTER

Fuente exclusiva: Cinemacenter.

Flujo:
  1. Descarga la cartelera semanal oficial de Tucumán (PDF).
  2. Obtiene desde la cartelera HTML los movieId/showId internos mediante
     seleccionarMovie(...).
  3. Para cada película/versión consulta ajax_movieSlider.php con movieId.
  4. Usa el enlace /ficha/{movieId}-... entregado por Cinemacenter.
  5. Extrae la metadata directamente de esa ficha.
  6. Genera cine_cinemacenter_tucuman.json y cine_metadata.json.

No usa TMDB, IMDb, Google, Jina ni ninguna otra fuente de metadata.
Si Cinemacenter no publica un campo, se deja vacío/null.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pypdf import PdfReader

try:
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:
    pass

BASE_URL = "https://www.cinemacenter.com.ar"
CARTELERA_URL = BASE_URL + "/cartelera#contenido"
SELECT_CITY_URL = BASE_URL + "/actions.php?action=select_city&cityid=13&ref=/cartelera"
PDF_URL = BASE_URL + "/pdf/horariospdf.php?cityId=13"
CITY_ID = 13
CITY_NAME = "Tucuman"
CINEMA_NAME = "Cinemacenter Tucumán"
MIBOLETERIA_URL = "https://www.miboleteria.com.ar"
ESTRENOS_URL = BASE_URL + "/estrenos#contenido"

SLIDER_URL = BASE_URL + "/modules/parts/ajax_movieSlider.php"
OUTPUT = Path("cine_cinemacenter_tucuman.json")
METADATA_OUTPUT = Path("cine_metadata.json")

# El runner de GitHub puede tardar en conectar con Cinemacenter. No usamos
# Jina: si Cinemacenter no responde, el workflow conserva la versión anterior.
TIMEOUT = (45, 90)
REQUEST_RETRIES = 3
RETRY_BACKOFF = 2
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0 Safari/537.36 AgendaTucuman/2.0"
    ),
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

WEEKDAYS = ["jueves", "viernes", "sábado", "domingo", "lunes", "martes", "miércoles"]
SHOWTIME_RE = re.compile(r"^(?:[01]?\d|2[0-3]):[0-5]\d$")
SHOWTIME_CELL_RE = re.compile(r"^(?:-|(?:[01]?\d|2[0-3]):[0-5]\d)$")
MOVIE_HEADER_RE = re.compile(
    r"^(?P<title>.+?)\s*-\s*(?P<format>[23]D)\s+(?P<language>CAST|SUB)\s*$",
    re.IGNORECASE,
)
DATE_RANGE_RE = re.compile(
    r"CARTELERA\s+VALIDA\s+DESDE\s+(\d{2}/\d{2}/\d{4})\s+AL\s+(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)


def clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize(value: object) -> str:
    """Normaliza títulos para comparar fichas sin depender de acentos, ñ, símbolos o formato."""
    text = clean_text(value)

    # Corrige casos de mojibake frecuentes (UTF-8 interpretado como Latin-1/CP1252).
    # Se aplica solo si el resultado mejora claramente la presencia de caracteres
    # latinos mal decodificados.
    mojibake_markers = ("Ã", "Â", "â", "ð", "�")
    if any(marker in text for marker in mojibake_markers):
        try:
            repaired = text.encode("latin1").decode("utf-8")
            # Si la secuencia es un caso real de mojibake, la versión reparada
            # será válida en UTF-8 y eliminará las marcas Ã/Â/â/ð.
            if repaired != text and not any(
                marker in repaired for marker in ("Ã", "Â", "â", "ð")
            ):
                text = repaired
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

    # Normaliza diacríticos: CORAZÓN -> CORAZON, NIÑO -> NINO.
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")

    text = text.lower()

    # Los dos puntos, guiones, apóstrofes, paréntesis, etc. se consideran
    # separadores, no diferencias entre la película y la ficha.
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def titles_match(expected: object, actual: object) -> bool:
    """Compara títulos después de reparar mojibake, acentos, símbolos y
    sufijos técnicos 2D/3D CAST/SUB."""
    a = normalize_movie_title(expected)
    b = normalize_movie_title(actual)
    return bool(a and b and (a == b or a in b or b in a))


def normalize_movie_title(value: object) -> str:
    text = normalize(value)
    text = re.sub(r"\b2d\s+(cast|sub)\b", " ", text)
    text = re.sub(r"\b3d\s+(cast|sub)\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def slugify(value: str) -> str:
    value = normalize(value).replace(" ", "-")
    return value.strip("-")



def parse_date(value: str) -> date | None:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def parse_release_date(value: str) -> str | None:
    text = clean_text(value)
    m = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
    if m:
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            # Cinemacenter currently has fichas that expose the Unix epoch
            # placeholder 31/12/1969. Never publish that as a real estreno.
            if d <= date(1970, 1, 1):
                return None
            return d.isoformat()
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](20\d{2})", text)
    if m:
        try:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if d <= date(1970, 1, 1):
                return None
            return d.isoformat()
        except ValueError:
            return None
    return None


def parse_duration(value: object) -> int | None:
    text = clean_text(value)
    m = re.search(r"(\d{2,3})\s*(?:min|mins|minutos)", text, re.I)
    return int(m.group(1)) if m else None


def split_people(value: str | None) -> list[str]:
    if not value:
        return []
    parts = re.split(r"\s*,\s*|\s+ y \s+|\s*;\s*", clean_text(value))
    return list(dict.fromkeys(x.strip() for x in parts if x.strip()))


def split_genres(value: str | None) -> list[str]:
    if not value:
        return []
    parts = re.split(r"\s*,\s*|\s*/\s*|\s+ y \s+|\s*·\s*", clean_text(value))
    return list(dict.fromkeys(x.strip() for x in parts if x.strip()))


def configure_session(session: requests.Session) -> None:
    """Configura reintentos para fallos transitorios de red del runner de GitHub."""
    retry = Retry(
        total=REQUEST_RETRIES,
        connect=REQUEST_RETRIES,
        read=REQUEST_RETRIES,
        status=REQUEST_RETRIES,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)


def request(session: requests.Session, url: str, *, method: str = "GET", data: dict | None = None) -> requests.Response:
    """Petición HTTP con timeout amplio y reintentos ante fallos transitorios."""
    try:
        if method == "POST":
            response = session.post(url, data=data or {}, timeout=TIMEOUT, headers=HEADERS)
        else:
            response = session.get(url, timeout=TIMEOUT, headers=HEADERS)
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        raise RuntimeError(f"No se pudo acceder a Cinemacenter: {url} ({exc})") from exc


def extract_week_range(text: str) -> tuple[date | None, date | None]:
    m = DATE_RANGE_RE.search(clean_text(text))
    if not m:
        return None, None
    return parse_date(m.group(1)), parse_date(m.group(2))


def download_pdf(session: requests.Session) -> tuple[bytes, str]:
    print(f"[1/5] Cartelera oficial: {PDF_URL}")
    response = request(session, PDF_URL)
    if not response.content.startswith(b"%PDF"):
        raise RuntimeError("Cinemacenter no devolvió un PDF válido para Tucumán")
    reader = PdfReader(BytesIO(response.content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return response.content, text


def extract_movie_blocks(text: str) -> list[dict]:
    lines = [clean_text(x) for x in text.splitlines() if clean_text(x)]
    movies: list[dict] = []
    current: dict | None = None
    for line in lines:
        m = MOVIE_HEADER_RE.match(line)
        if m:
            if current:
                movies.append(current)
            current = {
                "title": clean_text(m.group("title")),
                "format": m.group("format").upper(),
                "language": m.group("language").upper(),
                "schedule_rows": [],
            }
            continue
        if current is None:
            continue
        low = line.lower()
        if "jueves" in low and "viernes" in low and "miércoles" in low:
            continue
        if "jue" in low and "vie" in low and "mié" in low:
            continue
        cells = [clean_text(x) for x in line.strip().strip("|").split("|")] if "|" in line else line.split()
        if len(cells) == 7 and all(SHOWTIME_CELL_RE.match(x) for x in cells):
            current["schedule_rows"].append(cells)
    if current:
        movies.append(current)
    return movies


def build_schedule(rows: list[list[str]], week_start: date | None) -> tuple[dict, list[dict]]:
    schedule = {day: [] for day in WEEKDAYS}
    if not week_start:
        return schedule, []
    for row in rows:
        if len(row) != 7:
            continue
        for idx, value in enumerate(row):
            if SHOWTIME_RE.match(value):
                schedule[WEEKDAYS[idx]].append(value)
    for day in schedule:
        schedule[day] = sorted(set(schedule[day]))
    occurrences = []
    for idx, day_name in enumerate(WEEKDAYS):
        day_date = week_start.fromordinal(week_start.toordinal() + idx)
        for hour in schedule[day_name]:
            occurrences.append({
                "date": day_date.isoformat(),
                "time": hour,
                "datetime": f"{day_date.isoformat()}T{hour}:00",
                "weekday": day_name,
            })
    return schedule, occurrences


def select_tucuman_and_get_cartelera(session: requests.Session) -> str:
    """Selecciona Tucumán y obtiene las variantes de cartelera que publica Cinemacenter.

    Cinemacenter no mantiene una única estructura HTML estable. En algunas respuestas
    ya no aparecen las llamadas JavaScript seleccionarMovie(), pero sí existe el selector
    de películas con enlaces directos /ficha/{id}-.... Por eso consultamos la cartelera
    y, como respaldo, /tucuman, y dejamos que extract_movie_links() combine ambas fuentes.
    """
    print("[2/5] Consultando cartelera HTML de Cinemacenter para Tucumán...")
    errors = []
    try:
        request(session, SELECT_CITY_URL)
    except Exception as exc:
        errors.append(f"select_city: {exc}")
        print(f"  Aviso: no fue necesario/posible seleccionar ciudad por endpoint: {exc}")

    html_parts = []
    for url in (BASE_URL + "/cartelera", BASE_URL + "/tucuman"):
        try:
            response = request(session, url)
            html_parts.append(response.text)
            print(f"  HTML obtenido: {response.url} ({len(response.text):,} bytes)")
        except Exception as exc:
            errors.append(f"{url}: {exc}")
            print(f"  Aviso: no se pudo obtener {url}: {exc}")

    if not html_parts:
        raise RuntimeError("Cinemacenter no devolvió HTML de cartelera; " + " | ".join(errors))
    return "\n".join(html_parts)


def extract_movie_links(html_text: str) -> list[dict]:
    """Extrae fichas oficiales de Cinemacenter desde el HTML.

    Prioridad:
      1. enlaces directos /ficha/{movieId}-... (estructura actualmente visible),
      2. llamadas seleccionarMovie(...) de versiones antiguas del sitio.

    No se usa similitud difusa: el título se valida después contra la ficha oficial.
    """
    result = []
    seen = set()

    def add(item: dict):
        movie_id = item.get("movie_id")
        title = clean_text(item.get("title"))
        if not movie_id or not title:
            return
        item["title"] = title
        key = (int(movie_id), normalize_movie_title(title))
        if key in seen:
            return
        seen.add(key)
        result.append(item)

    # Estructura actual: el selector de películas contiene enlaces directos
    # /ficha/{movieId}-... (en <option value="..."> o <a href="...">).
    soup = BeautifulSoup(html_text, "html.parser")
    for node in soup.find_all(["option", "a"]):
        href = node.get("value") if node.name == "option" else node.get("href")
        href = clean_text(href)
        if "/ficha/" not in href.lower():
            continue
        match = re.search(r"/ficha/(\d+)-", href, re.I)
        if not match:
            continue
        title = clean_text(node.get_text(" ", strip=True))
        if not title:
            continue
        add({
            "cinema_title": "Cinemacenter Tucumán",
            "city_title": "Tucuman",
            "cinema_id": 0,
            "movie_id": int(match.group(1)),
            "city_id": CITY_ID,
            "title": title,
            "ficha_url": urljoin(BASE_URL, href.split("#", 1)[0]),
            "source": "direct_ficha_link",
        })

    # Estructura anterior: seleccionarMovie(..., cinemaId, movieId, cityId) ... título.
    pattern = re.compile(
        r"seleccionarMovie\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\s*[^>]*>\s*([^<]+)",
        re.I,
    )
    for m in pattern.finditer(html_text):
        cinema_title, city_title, cinema_id, show_id, city_id, title = m.groups()
        add({
            "cinema_title": clean_text(cinema_title),
            "city_title": clean_text(city_title),
            "cinema_id": int(cinema_id),
            "movie_id": int(show_id),
            "city_id": int(city_id),
            "title": clean_text(title),
            "ficha_url": None,
            "source": "seleccionarMovie",
        })

    return result

def find_movie_id(movie_links: list[dict], title: str, fmt: str, language: str) -> dict | None:
    wanted = normalize_movie_title(title)
    exact = [x for x in movie_links if normalize_movie_title(x["title"]) == wanted]
    if exact:
        # Si hay varias fichas de la misma película, preferimos la versión que
        # aparece explícitamente en la cartelera (CAST/SUB), si está en el título.
        lang = language.upper()
        for x in exact:
            xt = normalize(x["title"])
            if lang == "SUB" and " sub" in xt:
                return x
            if lang == "CAST" and " cast" in xt:
                return x
        return exact[0]
    return None


def fetch_slider(session: requests.Session, movie_id: int) -> tuple[str, str | None]:
    response = request(session, SLIDER_URL, method="POST", data={"movieId": str(movie_id)})
    soup = BeautifulSoup(response.text, "html.parser")
    poster = soup.select_one("img.poster")
    link = soup.select_one("a[href*='/ficha/']")
    return response.text, (urljoin(BASE_URL, link.get("href")) if link and link.get("href") else None)


def is_real_youtube_url(url: str) -> bool:
    """Devuelve True solo para URLs reales de videos de YouTube."""
    if not url:
        return False
    low = url.lower().split("#", 1)[0].rstrip("/")
    if low in {
        "https://www.youtube.com/webcinemacenter",
        "http://www.youtube.com/webcinemacenter",
    }:
        return False
    return (
        "youtube.com/watch?" in low
        or "youtube.com/embed/" in low
        or "youtu.be/" in low
    )


def parse_details_from_ficha(html_text: str, ficha_url: str, expected_title: str) -> dict:
    soup = BeautifulSoup(html_text, "html.parser")
    title_node = soup.select_one(".moviedetails .the-title")
    poster_node = soup.select_one(".moviedetails-left img.poster")
    synopsis_node = soup.select_one(".moviedetails-right .synopsis")
    title = clean_text(title_node.get_text(" ", strip=True)) if title_node else expected_title
    poster = urljoin(ficha_url, poster_node.get("src")) if poster_node and poster_node.get("src") else None
    synopsis = clean_text(synopsis_node.get_text(" ", strip=True)) if synopsis_node else None

    fields: dict[str, str] = {}
    for li in soup.select(".moviedetails-left ul.details li"):
        label = clean_text(li.select_one(".label").get_text(" ", strip=True) if li.select_one(".label") else "")
        data = clean_text(li.select_one(".data").get_text(" ", strip=True) if li.select_one(".data") else "")
        if label and data:
            fields[label.lower()] = data

    raw_release = fields.get("fecha de estreno en argentina") or fields.get("fecha de estreno") or fields.get("estreno")
    release_date = parse_release_date(raw_release)
    warnings = []
    if raw_release and release_date is None:
        warnings.append(f"Fecha de estreno de Cinemacenter no válida: {raw_release}")

    classification = fields.get("calificación") or fields.get("clasificación")
    if classification and classification.lower() in {"desconocido", "desconocida", "n/a", "-"}:
        classification = classification.strip()

    metadata = {
        "title": title,
        "original_title": None,
        "year": int(release_date[:4]) if release_date else None,
        "release_date": release_date,
        "duration_minutes": parse_duration(fields.get("duración")),
        "genres": split_genres(fields.get("género")),
        "director": split_people(fields.get("director")),
        "cast": split_people(fields.get("protagonistas") or fields.get("actores") or fields.get("reparto")),
        "synopsis": synopsis,
        "poster": poster,
        "classification": classification,
        "nationality": fields.get("nacionalidad") or fields.get("origen") or fields.get("país de origen"),
        "distributor": fields.get("distribuidora") or fields.get("distribuidor"),
        "trailer": None,
        "source_url": ficha_url,
        "source": "Cinemacenter",
    }

    # Cinemacenter puede publicar el tráiler como enlace, YouTube o iframe.
    # Solo aceptamos URLs que estén realmente presentes en la ficha oficial.
    # Trailer: Cinemacenter puede cargar YouTube dinámicamente.
    # En esos casos la ficha puede no exponer el iframe directamente, pero
    # el thumbnail generado por YouTube contiene el ID en i.ytimg.com/vi/ID/.
    trailer_candidates = []
    trailer_sources = []

    for a in soup.find_all("a", href=True):
        label = normalize(a.get_text(" ", strip=True))
        href = a.get("href") or ""
        href_low = href.lower()
        if href and ("trailer" in label or "youtube.com" in href_low or "youtu.be/" in href_low):
            trailer_candidates.append(urljoin(ficha_url, href))
            trailer_sources.append((urljoin(ficha_url, href), "link"))

    for iframe in soup.find_all("iframe", src=True):
        src = iframe.get("src") or ""
        src_low = src.lower()
        if "youtube.com" in src_low or "youtu.be/" in src_low or "vimeo.com" in src_low:
            value = urljoin(ficha_url, src)
            trailer_candidates.append(value)
            trailer_sources.append((value, "iframe"))

    # YouTube móvil/web puede dejar únicamente la miniatura:
    # https://i.ytimg.com/vi/s_qpMMkvHYE/sddefault.jpg
    YT_THUMB_RE = re.compile(
        r"https?://i\.ytimg\.com/vi/([A-Za-z0-9_-]{11})/[^\"' )]+",
        re.IGNORECASE,
    )
    html_text = str(soup)
    for match in YT_THUMB_RE.finditer(html_text):
        video_id = match.group(1)
        value = f"https://www.youtube.com/watch?v={video_id}"
        if value not in trailer_candidates:
            trailer_candidates.append(value)
            trailer_sources.append((value, "ytimg_thumbnail"))

    # Preferimos iframe/link reales. Si Cinemacenter solo dejó la miniatura,
    # usamos el ID de YouTube que aparece en ella.
    if trailer_candidates:
        preferred = next(
            ((url, source) for url, source in trailer_sources if source == "iframe"),
            None,
        )
        if preferred is None:
            preferred = next(
                ((url, source) for url, source in trailer_sources if source == "link" and ("youtube.com" in url.lower() or "youtu.be/" in url.lower())),
                None,
            )
        if preferred is None:
            preferred = next(
                ((url, source) for url, source in trailer_sources if source == "ytimg_thumbnail"),
                None,
            )
        if preferred:
            metadata["trailer"] = preferred[0]
            metadata["trailer_source"] = preferred[1]

    source_expected = [
        "duration_minutes", "genres", "director", "cast", "synopsis",
        "poster", "classification", "nationality", "distributor",
    ]
    missing = [k for k in source_expected if metadata.get(k) in (None, "", [])]
    unavailable = []
    for k in ("original_title", "year", "release_date"):
        if metadata.get(k) in (None, "", []):
            unavailable.append(k)
    metadata["metadata_missing"] = missing
    metadata["metadata_unavailable_on_source"] = unavailable
    metadata["metadata_warnings"] = warnings
    metadata["metadata_status"] = "complete_source" if not missing else "partial_source"

    # Verificación estricta: la ficha debe corresponder a la película solicitada.
    expected_norm = normalize_movie_title(expected_title)
    actual_norm = normalize_movie_title(title)
    if expected_norm != actual_norm:
        # Cinemacenter puede agregar 2D CAST/SUB al título de la ficha.
        if expected_norm not in actual_norm and actual_norm not in expected_norm:
            raise RuntimeError(
                f"Ficha incorrecta para '{expected_title}': Cinemacenter devolvió '{title}'"
            )

    # Nunca devolver el enlace genérico de Cinemacenter como trailer.
    if metadata.get("trailer") and not is_real_youtube_url(metadata["trailer"]):
        metadata["trailer"] = None
        metadata["trailer_source"] = None

    return metadata


def fetch_metadata_for_movie(session: requests.Session, movie: dict, movie_link: dict) -> dict:
    """Obtiene la ficha oficial directamente desde Cinemacenter."""
    ficha_url = movie_link.get("ficha_url")
    if not ficha_url:
        # Compatibilidad con la estructura antigua: obtener /ficha/ mediante AJAX.
        _, ficha_url = fetch_slider(session, movie_link["movie_id"])
    if not ficha_url:
        raise RuntimeError(
            f"movieId={movie_link['movie_id']} no devolvió enlace /ficha/ desde Cinemacenter"
        )

    response = request(session, ficha_url)
    metadata = parse_details_from_ficha(response.text, ficha_url, movie["title"])
    metadata["cinemacenter_movie_id"] = movie_link["movie_id"]
    metadata["cinemacenter_cinema_id"] = movie_link.get("cinema_id") or None
    metadata["cinemacenter_city_id"] = movie_link.get("city_id") or CITY_ID
    metadata["cinemacenter_ficha_source"] = movie_link.get("source", "unknown")
    return metadata


def parse_spanish_date(value: str) -> str | None:
    months = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
        "noviembre": 11, "diciembre": 12,
    }
    text = normalize(value)
    m = re.search(r"\b(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(20\d{2})\b", text)
    if not m:
        return None
    month = months.get(m.group(2))
    if not month:
        return None
    try:
        return date(int(m.group(3)), month, int(m.group(1))).isoformat()
    except ValueError:
        return None


def extract_upcoming_releases(session: requests.Session) -> list[dict]:
    """Extrae próximos estrenos exclusivamente desde la página oficial de Cinemacenter."""
    print("[3/5] Consultando próximos estrenos de Cinemacenter...")
    response = request(session, ESTRENOS_URL)
    soup = BeautifulSoup(response.text, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = urljoin(BASE_URL, a.get("href", ""))
        if "/ficha/" not in href:
            continue
        title = clean_text(a.get_text(" ", strip=True))
        if not title or normalize(title) in {"mas info", "ver ficha", "info"}:
            continue

        node = a
        context = ""
        for _ in range(6):
            node = node.parent
            if not node:
                break
            txt = clean_text(node.get_text(" ", strip=True))
            if txt and len(txt) <= 1200:
                context = txt
                if "estreno" in normalize(txt):
                    break

        release_date = parse_release_date(context) or parse_spanish_date(context)
        key = href.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "id": slugify(title) or key.rsplit("/", 1)[-1],
            "title": title,
            "release_date": release_date,
            "source_url": href,
            "source": "Cinemacenter",
        })

    # Si el listado no contiene tarjetas reconocibles, no inventamos datos.
    # Conservamos el enlace oficial para que la app siempre pueda mostrarlo.
    items.sort(key=lambda x: (x.get("release_date") or "9999-99-99", normalize(x.get("title"))))
    print(f"  Próximos estrenos detectados: {len(items)}")
    return items


def make_metadata_file(movies: list[dict]) -> dict:
    return {
        "schema_version": "3.0",
        "generated_at": datetime.now().astimezone().isoformat(),
        "source_policy": "Cinemacenter-only",
        "movies": [m["metadata"] for m in movies if m.get("metadata")],
        "summary": {
            "total": len(movies),
            "complete_source": sum(1 for m in movies if m.get("metadata", {}).get("metadata_status") == "complete_source"),
            "partial_source": sum(1 for m in movies if m.get("metadata", {}).get("metadata_status") == "partial_source"),
            "without_metadata": sum(1 for m in movies if not m.get("metadata")),
        },
    }


def run_test_ids(ids: list[int]) -> int:
    """Prueba local de IDs concretos sin depender del PDF/cartelera."""
    session = requests.Session()
    session.headers.update(HEADERS)
    configure_session(session)
    print("=" * 72)
    print("PRUEBA DIRECTA DE MOVIE IDs DE CINEMACENTER")
    print("Fuente exclusiva: Cinemacenter")
    print("=" * 72)
    failures = 0
    for movie_id in ids:
        try:
            slider_html, ficha_url = fetch_slider(session, movie_id)
            if not ficha_url:
                raise RuntimeError("ajax_movieSlider.php no devolvió /ficha/")
            soup = BeautifulSoup(slider_html, "html.parser")
            slider_title = clean_text(soup.select_one("img.poster").get("alt", "") if soup.select_one("img.poster") else "")
            response = request(session, ficha_url)
            metadata = parse_details_from_ficha(response.text, ficha_url, slider_title or f"movieId {movie_id}")
            print(f"\nmovieId={movie_id}")
            print(f"  título:       {metadata.get('title')}")
            print(f"  ficha:        {metadata.get('source_url')}")
            print(f"  duración:     {metadata.get('duration_minutes')}")
            print(f"  género:       {metadata.get('genres')}")
            print(f"  director:     {metadata.get('director')}")
            print(f"  protagonistas:{metadata.get('cast')}")
            print(f"  clasificación:{metadata.get('classification')}")
            print(f"  nacionalidad: {metadata.get('nationality')}")
            print(f"  distribuidora:{metadata.get('distributor')}")
            print(f"  poster:       {metadata.get('poster')}")
            print(f"  estado:       {metadata.get('metadata_status')}")
            if metadata.get('metadata_warnings'):
                print(f"  avisos:       {metadata['metadata_warnings']}")
        except Exception as exc:
            failures += 1
            print(f"\nmovieId={movie_id} ERROR: {exc}")
        time.sleep(0.2)
    print("\n" + "=" * 72)
    print(f"PRUEBA FINALIZADA: {len(ids) - failures}/{len(ids)} OK")
    print("=" * 72)
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Extractor unificado de Cinemacenter")
    parser.add_argument("--test-ids", help="Prueba directa de movieId, separados por coma; no actualiza JSON")
    args = parser.parse_args()
    if args.test_ids:
        ids = [int(x.strip()) for x in args.test_ids.split(",") if x.strip()]
        return run_test_ids(ids)

    print("=" * 72)
    print("AGENDA TUCUMÁN - CINEMACENTER UNIFICADO")
    print("Fuente exclusiva: Cinemacenter")
    print("=" * 72)

    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        pdf_bytes, pdf_text = download_pdf(session)
        week_start, week_end = extract_week_range(pdf_text)
        if not week_start or not week_end:
            raise RuntimeError("No se pudo detectar la semana de la cartelera oficial")
        print(f"  Semana: {week_start} -> {week_end}")

        raw_movies = extract_movie_blocks(pdf_text)
        if not raw_movies:
            raise RuntimeError("No se detectaron películas en el PDF oficial")

        upcoming = extract_upcoming_releases(session)
        html = select_tucuman_and_get_cartelera(session)
        movie_links = extract_movie_links(html)
        print(f"  IDs internos encontrados en Cinemacenter: {len(movie_links)}")
        if not movie_links:
            raise RuntimeError("No se encontraron fichas /ficha/ ni llamadas seleccionarMovie() en la cartelera HTML de Cinemacenter")

        movies = []
        failures = []
        for raw in raw_movies:
            schedule, occurrences = build_schedule(raw.get("schedule_rows", []), week_start)
            if not occurrences:
                continue
            movie = {
                "id": f"cinemacenter-tucuman-{slugify(raw['title'])}-{raw['format'].lower()}-{raw['language'].lower()}",
                "source": "cinemacenter",
                "source_url": CARTELERA_URL,
                "cinema": CINEMA_NAME,
                "city": "San Miguel de Tucumán",
                "title": raw["title"],
                "status": "cartelera_vigente",
                "format": raw["format"],
                "language": raw["language"],
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "schedule": schedule,
                "occurrences": occurrences,
            }

            link = find_movie_id(movie_links, movie["title"], movie["format"], movie["language"])
            if not link:
                failures.append({"title": movie["title"], "format": movie["format"], "language": movie["language"], "reason": "movieId no encontrado en cartelera HTML"})
                movies.append(movie)
                continue

            movie["cinemacenter_movie_id"] = link["movie_id"]
            try:
                print(f"  Metadata: {movie['title']} [{movie['format']} {movie['language']}] -> movieId={link['movie_id']}")
                movie["metadata"] = fetch_metadata_for_movie(session, movie, link)
                # Para Agenda Tucumán, "fecha de estreno" significa la primera
                # fecha en que la película aparece en la cartelera de Tucumán
                # que estamos procesando. Nunca reemplazamos esto por una fecha
                # externa ni por la fecha defectuosa que pueda publicar la ficha.
                first_showing = min((o["date"] for o in occurrences), default=None)
                movie["metadata"]["release_date"] = first_showing
                movie["metadata"]["year"] = int(first_showing[:4]) if first_showing else None
                movie["metadata"]["release_date_source"] = "Cinemacenter cartelera Tucumán"
                unavailable = movie["metadata"].get("metadata_unavailable_on_source") or []
                movie["metadata"]["metadata_unavailable_on_source"] = [
                    x for x in unavailable if x not in {"release_date", "year"}
                ]
                if movie["metadata"].get("metadata_warnings"):
                    movie["metadata"]["metadata_warnings"].append(
                        "La fecha de estreno de la ficha no se utiliza; se usa la primera fecha de cartelera de Tucumán."
                    )
            except Exception as exc:
                failures.append({"title": movie["title"], "format": movie["format"], "language": movie["language"], "movie_id": link["movie_id"], "reason": str(exc)})
                print(f"    ERROR metadata: {exc}")
            time.sleep(0.2)
            movies.append(movie)

        metadata_file = make_metadata_file(movies)
        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
        output = {
            "schema_version": "3.0",
            "generated_at": datetime.now().astimezone().isoformat(),
            "reference_date": date.today().isoformat(),
            "source": {
                "name": "Cinemacenter",
                "homepage": CARTELERA_URL,
                "city": "Tucumán",
                "city_id": CITY_ID,
                "official_schedule_url": PDF_URL,
                "pdf_sha256": pdf_hash,
            },
            "cinema": {
                "name": CINEMA_NAME,
                "address": "Av. Néstor Kirchner (Ex Roca) 3450",
                "city": "San Miguel de Tucumán",
                "country": "Argentina",
            },
            "cartelera": {
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "movies": movies,
            },
            "proximos_estrenos": upcoming,
            "mi_boleteria_url": MIBOLETERIA_URL,
            "summary": {
                "cartelera_total": len(movies),
                "metadata_con_movie_id": sum(1 for m in movies if m.get("cinemacenter_movie_id")),
                "metadata_ok": sum(1 for m in movies if m.get("metadata")),
                "metadata_failures": len(failures),
                "metadata_source": "Cinemacenter-only",
                "failures": failures,
            },
        }

        OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        METADATA_OUTPUT.write_text(json.dumps(metadata_file, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        print()
        print("=" * 72)
        print("RESUMEN CINEMACENTER")
        print("=" * 72)
        print(f"Semana:                  {week_start} -> {week_end}")
        print(f"Películas con funciones: {len(movies)}")
        print(f"Con movieId:             {output['summary']['metadata_con_movie_id']}")
        print(f"Metadata obtenida:       {output['summary']['metadata_ok']}")
        print(f"Errores metadata:        {len(failures)}")
        for failure in failures:
            print(f"  - {failure['title']}: {failure['reason']}")
        print(f"Archivo: {OUTPUT.resolve()}")
        print(f"Metadata: {METADATA_OUTPUT.resolve()}")
        print("=" * 72)
        return 0

    except Exception as exc:
        print(f"ERROR CRÍTICO: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
