#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AGENDA TUCUMÁN - EXTRACTOR DE CINE DESDE CINEMACENTER
V9

Fuente principal:
  https://www.cinemacenter.com.ar/

Para Tucumán:
  https://www.cinemacenter.com.ar/pdf/horariospdf.php?cityId=XX

El script NO usa Agenda Tucumán para obtener películas.

1) Descubre automáticamente el cityId correspondiente a Tucumán.
2) Descarga el PDF semanal oficial.
3) Extrae películas, formato, idioma y horarios.
4) Consulta la página oficial para próximos estrenos.
5) Genera cine_cinemacenter_tucuman.json

Dependencias:
  pip install requests beautifulsoup4 pypdf

Opcional:
  pip install lxml
"""

from __future__ import annotations

import json
import re
import sys
import time
import hashlib
from io import BytesIO
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urljoin

# GitHub Actions no ejecuta Python en un terminal interactivo; forzamos salida
# inmediata para poder ver exactamente en qué consulta está trabajando.
try:
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:
    pass

import requests
from bs4 import BeautifulSoup

try:
    from pypdf import PdfReader
except ImportError:
    print("Falta pypdf.")
    print("Instalá con: pip install pypdf")
    sys.exit(1)


BASE_URL = "https://www.cinemacenter.com.ar"
HOME_URL = BASE_URL + "/cartelera#contenido"
ESTRENOS_URL = BASE_URL + "/estrenos#contenido"
PDF_URL = BASE_URL + "/pdf/horariospdf.php?cityId=13"
CITY_ID = 13

OUTPUT = Path("cine_cinemacenter_tucuman.json")

CONNECT_TIMEOUT = 8
READ_TIMEOUT = 15
REQUEST_TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)
JINA_TIMEOUT = (8, 20)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
}

WEEKDAYS = [
    "jueves",
    "viernes",
    "sábado",
    "domingo",
    "lunes",
    "martes",
    "miércoles",
]

WEEKDAYS_SHORT = [
    "jue",
    "vie",
    "sáb",
    "dom",
    "lun",
    "mar",
    "mié",
]

SHOWTIME_RE = re.compile(r"^(?:[01]?\d|2[0-3]):[0-5]\d$")
SHOWTIME_CELL_RE = re.compile(r"^(?:-|(?:[01]?\d|2[0-3]):[0-5]\d)$")

# Títulos de película que aparecen en los PDFs con:
#   NOMBRE - 2D CAST
#   NOMBRE - 2D SUB
#   NOMBRE - 3D CAST
#   NOMBRE - 3D SUB
MOVIE_HEADER_RE = re.compile(
    r"^(?P<title>.+?)\s*-\s*(?P<format>[23]D)\s+(?P<language>CAST|SUB)\s*$",
    re.IGNORECASE,
)

DATE_RANGE_RE = re.compile(
    r"CARTELERA\s+VALIDA\s+DESDE\s+"
    r"(\d{2}/\d{2}/\d{4})\s+AL\s+(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)

# Para próximas películas, Cinemacenter puede mostrar fechas en distintos formatos.
RELEASE_DATE_PATTERNS = [
    re.compile(r"estreno\s*:?\s*(\d{1,2})[/-](\d{1,2})[/-](\d{4})", re.I),
    re.compile(r"estreno\s*:?\s*(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})", re.I),
    re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})"),
]


def clean_text(value: str) -> str:
    value = value or ""
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_title(value: str) -> str:
    value = clean_text(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" -–—")


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9áéíóúüñ]+", "-", value)
    value = value.strip("-")
    return value


def parse_date(value: str) -> date | None:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def parse_release_date(text: str) -> date | None:
    months = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
        "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
        "septiembre": 9, "setiembre": 9, "octubre": 10,
        "noviembre": 11, "diciembre": 12,
    }

    text = clean_text(text)

    m = RELEASE_DATE_PATTERNS[0].search(text)
    if m:
        d, mo, y = map(int, m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            return None

    m = RELEASE_DATE_PATTERNS[1].search(text)
    if m:
        d = int(m.group(1))
        mo = months.get(m.group(2).lower())
        y = int(m.group(3))
        if mo:
            try:
                return date(y, mo, d)
            except ValueError:
                return None

    m = RELEASE_DATE_PATTERNS[2].search(text)
    if m:
        d, mo, y = map(int, m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            return None

    return None


def request(session: requests.Session, url: str, **kwargs) -> requests.Response | None:
    try:
        response = session.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers=HEADERS,
            **kwargs,
        )
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        print(f"  ERROR directo: {url}")
        print(f"         {exc}")
        return None


def request_jina(session: requests.Session, url: str) -> str | None:
    """
    Fallback para cuando el runner de GitHub no puede conectar directamente
    con Cinemacenter. Jina Reader actúa solamente como transporte/lector;
    Cinemacenter sigue siendo la fuente de datos.
    """
    reader_url = "https://r.jina.ai/" + url
    print(f"  Fallback Reader: {reader_url}")

    try:
        response = session.get(
            reader_url,
            timeout=JINA_TIMEOUT,
            headers={
                "User-Agent": "AgendaTucuman/1.0",
                "Accept": "text/plain,text/markdown;q=0.9,*/*;q=0.8",
            },
        )
        response.raise_for_status()
        return response.text
    except requests.RequestException as exc:
        print(f"  ERROR Reader: {exc}")
        return None


def download_tucuman_pdf(session: requests.Session) -> tuple[bytes, str] | None:
    url = PDF_URL
    print(f"Descargando cartelera oficial de Tucumán: {url}")

    # 1) Intento directo: es la fuente preferida.
    response = request(session, url)
    if response and response.content.startswith(b"%PDF"):
        try:
            reader = PdfReader(BytesIO(response.content))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            print("  OK: PDF obtenido directamente.")
            return response.content, text
        except Exception as exc:
            print(f"  ERROR leyendo PDF directo: {exc}")

    # 2) Fallback: Jina Reader. No cambia la fuente, solamente el transporte.
    reader_text = request_jina(session, url)
    if reader_text:
        print("  OK: contenido obtenido mediante Reader.")
        # Jina puede devolver Markdown en lugar del PDF binario. Lo tratamos
        # como texto de cartelera y lo convertimos a bytes para el hash.
        return reader_text.encode("utf-8"), reader_text

    # 3) Último fallback: conservar el último JSON válido.
    # Esto evita que una caída temporal de Cinemacenter borre la cartelera.
    previous_candidates = [
        Path("../../datos/cine_cinemacenter_tucuman.json"),
        Path("../../src/data/cine_cinemacenter_tucuman.json"),
    ]
    for previous_path in previous_candidates:
        if previous_path.exists():
            try:
                previous = json.loads(previous_path.read_text(encoding="utf-8"))
                movies = previous.get("cartelera", {}).get("movies", [])
                if movies:
                    print(f"  AVISO: Cinemacenter no respondió; conservando {len(movies)} películas del JSON anterior.")
                    # Marcamos la salida como fallback pero devolvemos una
                    # representación textual mínima; main la reconocerá.
                    previous["_fallback_previous"] = True
                    return json.dumps(previous, ensure_ascii=False).encode("utf-8"), ""
            except Exception as exc:
                print(f"  ERROR leyendo JSON anterior: {exc}")

    return None


def extract_week_range(text: str) -> tuple[date | None, date | None]:
    m = DATE_RANGE_RE.search(clean_text(text))
    if not m:
        return None, None

    return parse_date(m.group(1)), parse_date(m.group(2))


def extract_movie_blocks(text: str) -> list[dict]:
    """
    Extrae bloques:
        PELICULA - 2D CAST
        días
        horarios...
    """

    raw_lines = [clean_text(line) for line in text.splitlines()]
    lines = [line for line in raw_lines if line]

    movies = []
    current = None

    for line in lines:
        # Jina Reader suele devolver Markdown. Quitamos encabezados, negritas
        # y separadores de tabla antes de aplicar las mismas reglas del PDF.
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = line.replace("**", "").replace("__", "")
        if "|" in line:
            cells = [clean_text(c) for c in line.strip().strip("|").split("|")]
            cells = [re.sub(r"`", "", c) for c in cells]
            if len(cells) == 7 and all(SHOWTIME_CELL_RE.match(c) for c in cells):
                if current is not None:
                    current.setdefault("schedule_rows", []).append(cells)
                continue
            line = " ".join(cells)
            line = clean_text(line)

        match = MOVIE_HEADER_RE.match(line)
        if match:
            if current:
                movies.append(current)

            current = {
                "title": normalize_title(match.group("title")),
                "format": match.group("format").upper(),
                "language": match.group("language").upper(),
                "schedule_rows": [],
            }
            continue

        if current is None:
            continue

        # Saltamos encabezados de días.
        lower = line.lower()
        if "jueves" in lower and "viernes" in lower and "miércoles" in lower:
            continue
        if "jue" in lower and "vie" in lower and "mié" in lower:
            continue

        # Una fila válida tiene 7 celdas:
        # jueves viernes sábado domingo lunes martes miércoles
        tokens = line.split()

        if len(tokens) == 7 and all(SHOWTIME_CELL_RE.match(t) for t in tokens):
            current["schedule_rows"].append(tokens)
            continue

        # A veces el PDF corta una fila en más de una línea.
        # Guardamos texto auxiliar para intentar recuperarlo después.
        current.setdefault("raw_lines", []).append(line)

    if current:
        movies.append(current)

    return movies


def schedule_from_rows(rows: list[list[str]], week_start: date | None) -> dict:
    result = {day: [] for day in WEEKDAYS}

    if not week_start:
        return result

    # El PDF está ordenado JUEVES -> MIÉRCOLES.
    # La semana comienza el jueves indicado por el PDF.
    for row in rows:
        if len(row) != 7:
            continue

        for idx, value in enumerate(row):
            if not SHOWTIME_RE.match(value):
                continue

            day_name = WEEKDAYS[idx]
            result[day_name].append(value)

    for day in result:
        result[day] = sorted(set(result[day]))

    return result


def flatten_occurrences(schedule: dict, week_start: date | None) -> list[dict]:
    if not week_start:
        return []

    occurrences = []

    for idx, day_name in enumerate(WEEKDAYS):
        day_date = week_start.fromordinal(week_start.toordinal() + idx)

        for hour in schedule.get(day_name, []):
            occurrences.append({
                "date": day_date.isoformat(),
                "time": hour,
                "datetime": f"{day_date.isoformat()}T{hour}:00",
                "weekday": day_name,
            })

    return sorted(occurrences, key=lambda x: (x["date"], x["time"]))


def build_current_movies(raw_movies: list[dict], week_start: date | None, week_end: date | None) -> list[dict]:
    movies = []
    seen = set()

    for movie in raw_movies:
        title = normalize_title(movie["title"])

        if not title:
            continue

        # Evita basura del PDF.
        bad_titles = {
            "boleteria",
            "las entradas son numeradas",
            "salas con aire acondicionado",
        }
        if title.lower() in bad_titles:
            continue

        schedule = schedule_from_rows(movie.get("schedule_rows", []), week_start)
        occurrences = flatten_occurrences(schedule, week_start)

        # Si el bloque no tiene funciones reales, no lo incluimos.
        if not occurrences:
            continue

        key = (
            title.lower(),
            movie["format"],
            movie["language"],
        )

        if key in seen:
            continue
        seen.add(key)

        movies.append({
            "id": "cinemacenter-tucuman-" + slugify(title) + "-" +
                  movie["format"].lower() + "-" + movie["language"].lower(),
            "source": "cinemacenter",
            "source_url": HOME_URL,
            "cinema": "Cinemacenter Tucumán",
            "city": "San Miguel de Tucumán",
            "title": title,
            "status": "cartelera_vigente",
            "format": movie["format"],
            "language": movie["language"],
            "week_start": week_start.isoformat() if week_start else None,
            "week_end": week_end.isoformat() if week_end else None,
            "schedule": schedule,
            "occurrences": occurrences,
        })

    return movies


def extract_upcoming_from_home(session: requests.Session) -> list[dict]:
    """
    Extrae únicamente la sección oficial de próximos estrenos.
    No usa Agenda Tucumán.
    """

    print(f"Consultando próximos estrenos en Cinemacenter: {ESTRENOS_URL}")

    response = request(session, ESTRENOS_URL)
    if not response:
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    # Buscamos cualquier encabezado o texto relacionado con PROXIMOS ESTRENOS.
    marker = None

    for element in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "a", "li", "div", "span"]):
        txt = clean_text(element.get_text(" ", strip=True))
        normalized = txt.upper().replace("Ó", "O")

        if "PROXIMOS ESTRENOS" in normalized or "PRÓXIMOS ESTRENOS" in normalized:
            marker = element
            break

    candidates = []

    if marker:
        # Primero intentamos el contenedor inmediato.
        containers = []
        parent = marker.parent
        for _ in range(5):
            if parent:
                containers.append(parent)
                parent = parent.parent

        for container in containers:
            for node in container.find_all(["a", "article", "li", "div"], limit=300):
                txt = clean_text(node.get_text(" ", strip=True))
                if not txt:
                    continue

                # Un candidato debe parecer una ficha de película.
                if len(txt) < 3 or len(txt) > 300:
                    continue

                if "estreno" not in txt.lower():
                    continue

                href = None
                if node.name == "a":
                    href = node.get("href")
                else:
                    a = node.find("a", href=True)
                    if a:
                        href = a.get("href")

                candidates.append((txt, href))

            if candidates:
                break

    # Fallback: recorrer todos los enlaces de la página buscando fechas.
    if not candidates:
        for a in soup.find_all("a", href=True):
            txt = clean_text(a.get_text(" ", strip=True))
            if "estreno" in txt.lower() or parse_release_date(txt):
                candidates.append((txt, a.get("href")))

    results = []
    seen = set()
    today = date.today()

    for txt, href in candidates:
        release = parse_release_date(txt)
        if not release or release <= today:
            continue

        # Intentamos extraer un título razonable.
        title = clean_text(txt)
        title = re.sub(
            r"estreno\s*:?\s*\d{1,2}(?:[/-]\d{1,2}[/-]\d{4}|"
            r"\s+de\s+[a-záéíóú]+\s+de\s+\d{4})",
            "",
            title,
            flags=re.I,
        )
        title = clean_text(title)

        # Si quedó demasiado genérico, descartamos.
        if not title or len(title) < 2:
            continue

        # Limpieza de textos comunes del sitio.
        title = re.sub(r"^(próximo estreno|proximo estreno)\s*", "", title, flags=re.I)
        title = clean_text(title)

        # Si contiene demasiada información, intentamos quedarnos con la primera parte.
        if " | " in title:
            title = title.split(" | ", 1)[0].strip()

        key = (title.lower(), release.isoformat())
        if key in seen:
            continue
        seen.add(key)

        results.append({
            "id": "cinemacenter-tucuman-upcoming-" + slugify(title),
            "source": "cinemacenter",
            "source_url": urljoin(BASE_URL, href) if href else HOME_URL,
            "cinema": "Cinemacenter Tucumán",
            "city": "San Miguel de Tucumán",
            "title": title,
            "status": "proximo_estreno",
            "release_date": release.isoformat(),
        })

    # Orden cronológico.
    results.sort(key=lambda x: x["release_date"])

    return results


def make_output(
    pdf_bytes: bytes,
    pdf_text: str,
    current_movies: list[dict],
    upcoming_movies: list[dict],
) -> dict:

    week_start, week_end = extract_week_range(pdf_text)

    pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()

    return {
        "schema_version": "2.0",
        "generated_at": datetime.now().astimezone().isoformat(),
        "reference_date": date.today().isoformat(),

        "source": {
            "name": "Cinemacenter",
            "homepage": HOME_URL,
            "city": "Tucumán",
            "city_id": CITY_ID,
            "official_schedule_url": PDF_URL,
            "pdf_sha256": pdf_hash,
        },

        "cinema": {
            "name": "Cinemacenter Tucumán",
            "address": "Av. Néstor Kirchner (Ex Roca) 3450",
            "city": "San Miguel de Tucumán",
            "country": "Argentina",
        },

        "cartelera": {
            "week_start": week_start.isoformat() if week_start else None,
            "week_end": week_end.isoformat() if week_end else None,
            "movies": current_movies,
        },

        "proximos_estrenos": upcoming_movies,

        "summary": {
            "cartelera_total": len(current_movies),
            "proximos_estrenos_total": len(upcoming_movies),
            "formats": sorted(set(
                movie["format"]
                for movie in current_movies
                if movie.get("format")
            )),
            "languages": sorted(set(
                movie["language"]
                for movie in current_movies
                if movie.get("language")
            )),
        },
    }


def main():
    print("=" * 70)
    print("       AGENDA TUCUMÁN - CINEMACENTER TUCUMÁN V10")
    print("=" * 70)
    print()
    print(f"Fuente cartelera: {HOME_URL}")
    print(f"Fuente estrenos:   {ESTRENOS_URL}")
    print(f"Fuente horarios:   {PDF_URL}")
    print(f"City ID Tucumán:  {CITY_ID}")
    print()

    session = requests.Session()

    pdf_result = download_tucuman_pdf(session)

    if pdf_result is None:
        print("No se pudo descargar la cartelera oficial.")
        sys.exit(3)

    pdf_bytes, pdf_text = pdf_result

    # Si el extractor tuvo que conservar el JSON anterior, reutilizamos sus
    # datos directamente y no intentamos reinterpretarlos como PDF/Markdown.
    if not pdf_text and pdf_bytes.startswith(b"{"):
        try:
            previous = json.loads(pdf_bytes.decode("utf-8"))
            previous["generated_at"] = datetime.now().astimezone().isoformat()
            previous["reference_date"] = date.today().isoformat()
            previous.setdefault("source", {})["fallback_reason"] = (
                "Cinemacenter no respondió; se conservó la última cartelera válida."
            )
            OUTPUT.write_text(
                json.dumps(previous, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print("Cartelera anterior conservada correctamente.")
            print(f"Archivo: {OUTPUT.resolve()}")
            sys.exit(0)
        except Exception as exc:
            print(f"ERROR procesando fallback anterior: {exc}")
            sys.exit(3)

    week_start, week_end = extract_week_range(pdf_text)

    print()
    print("Semana detectada:")
    print("  Desde:", week_start)
    print("  Hasta:", week_end)

    print()
    print("Extrayendo funciones del PDF oficial...")

    raw_movies = extract_movie_blocks(pdf_text)

    print(f"  Bloques de películas detectados: {len(raw_movies)}")

    current_movies = build_current_movies(
        raw_movies,
        week_start,
        week_end,
    )

    print(f"  Películas con funciones: {len(current_movies)}")

    print()
    upcoming_movies = extract_upcoming_from_home(session)
    print(f"  Próximos estrenos detectados: {len(upcoming_movies)}")

    output = make_output(
        pdf_bytes,
        pdf_text,
        current_movies,
        upcoming_movies,
    )

    OUTPUT.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 70)
    print("RESULTADO")
    print("=" * 70)
    print(f"City ID:              {CITY_ID}")
    print(f"Cartelera:            {len(current_movies)}")
    print(f"Próximos estrenos:    {len(upcoming_movies)}")
    print(f"Archivo:              {OUTPUT.resolve()}")
    print()

    if current_movies:
        print("CARTELERA:")
        for movie in current_movies:
            print(
                f"  - {movie['title']} "
                f"({movie['format']} {movie['language']})"
            )

    if upcoming_movies:
        print()
        print("PRÓXIMOS ESTRENOS:")
        for movie in upcoming_movies:
            print(
                f"  - {movie['title']} "
                f"({movie['release_date']})"
            )

    print()
    print("Fuente: Cinemacenter oficial")
    print("=" * 70)


if __name__ == "__main__":
    main()
