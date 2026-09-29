#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Agenda Tucumán - Extractor de contenidos V5
-------------------------------------------
Extrae:
  1) Cine: cartelera vigente + próximos estrenos desde la portada.
  2) Cine histórico/backup desde /estrenos-cine/.
  3) Radio: página + reproductor Shock Media/SonicPanel y URLs directas de audio.

Salidas:
  - cine_tucuman.json
  - radio_tucuman.json
  - errores_contenidos.json
  - informe_contenidos.txt

Dependencias:
    pip install requests beautifulsoup4

Uso:
    python extraer_contenidos_agenda_v7.py

Notas:
- No inventa una URL de streaming. Si SonicPanel/API no la expone,
  conserva el player_url como fallback.
- La cartelera vigente se obtiene de la portada, donde Agenda Tucumán
  etiqueta explícitamente las películas como "Cartelera vigente".
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup


BASE = "https://agendatucuman.com.ar"
HOME = BASE + "/"
CINE_ARCHIVE = BASE + "/estrenos-cine/"
RADIO_URL = BASE + "/radio/"

# Player encontrado en la web de Agenda Tucumán.
RADIO_PLAYER_URL = (
    "https://streaming01.shockmedia.com.ar/"
    "cp/widgets/player/single/?p=8718"
)

# Endpoint habitual del panel SonicPanel. Se consulta solo como fuente
# adicional: si no responde o no contiene una URL, no se considera error fatal.
RADIO_API_URL = (
    "https://streaming01.shockmedia.com.ar/"
    "cp/get_info.php?p=8718"
)

OUT_DIR = Path.cwd()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
}

TIMEOUT = 25
SLEEP = 0.25


class Extractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.errors = []
        self.ok = []

    # ---------------------------------------------------------
    # HTTP
    # ---------------------------------------------------------

    def get(self, url: str, **kwargs):
        try:
            r = self.session.get(url, timeout=TIMEOUT, **kwargs)
            r.raise_for_status()
            self.ok.append({
                "url": url,
                "status": r.status_code,
                "content_type": r.headers.get("content-type", ""),
            })
            time.sleep(SLEEP)
            return r
        except Exception as e:
            self.errors.append({
                "url": url,
                "error": str(e),
            })
            return None

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    @staticmethod
    def clean(value):
        if value is None:
            return ""
        if hasattr(value, "get_text"):
            value = value.get_text(" ", strip=True)
        value = re.sub(r"\s+", " ", str(value))
        return value.strip()

    @staticmethod
    def absolute(url, base=BASE):
        if not url:
            return ""
        url = str(url).strip()
        if url.startswith("//"):
            return "https:" + url
        return urljoin(base, url)

    @staticmethod
    def unique(values):
        out = []
        seen = set()
        for value in values:
            if not value:
                continue
            value = str(value).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            out.append(value)
        return out

    @staticmethod
    def normalize_url(url):
        url = unquote(str(url or "").strip())
        return url

    def extract_urls(self, soup):
        urls = []

        for a in soup.find_all("a", href=True):
            href = self.absolute(a.get("href"))
            if href:
                urls.append(href)

        for tag in soup.find_all(["audio", "source", "iframe", "video"]):
            for attr in ("src", "data-src", "data-url", "data-stream"):
                value = tag.get(attr)
                if value:
                    urls.append(self.absolute(value))

        return self.unique(urls)

    @staticmethod
    def image_from_node(node):
        if not node:
            return ""

        # Prefer full-size/source images.
        for tag in node.find_all(["img", "source"]):
            for attr in (
                "data-src",
                "data-lazy-src",
                "data-original",
                "src",
                "srcset",
            ):
                value = tag.get(attr)
                if not value:
                    continue

                if attr == "srcset":
                    # Tomar el último candidato normalmente más grande.
                    parts = [x.strip() for x in value.split(",") if x.strip()]
                    if parts:
                        value = parts[-1].split()[0]

                return Extractor.absolute(value)

        style = node.get("style", "")
        m = re.search(r"url\(['\"]?([^'\")]+)", style)
        if m:
            return Extractor.absolute(m.group(1))

        return ""

    @staticmethod
    def slug_from_url(url):
        path = urlparse(url).path.strip("/")
        if not path:
            return ""
        return path.split("/")[-1]

    # ---------------------------------------------------------
    # CINE
    # ---------------------------------------------------------

    def parse_movie_card(self, card, source_url, movie_type):
        # En la portada las películas aparecen como enlaces a /estrenos-cine/...
        link = None

        for a in card.find_all("a", href=True):
            href = self.absolute(a["href"])
            if "/estrenos-cine/" in href:
                link = a
                break

        if link is None:
            link = card.find("a", href=True)

        if not link:
            return None

        url = self.absolute(link.get("href"))
        title = self.clean(link)

        if not title:
            h = card.find(["h1", "h2", "h3", "h4", "h5"])
            title = self.clean(h)

        if not title:
            return None

        # El texto puede contener la etiqueta y la fecha.
        text = self.clean(card)

        release_date = ""
        m = re.search(
            r"(?:Estreno|Fecha de estreno)\s*:\s*"
            r"([0-9]{1,2}\s+[A-Za-zÁÉÍÓÚáéíóúÑñ]+\s+[0-9]{4})",
            text,
            re.I,
        )
        if m:
            release_date = m.group(1)

        image = self.image_from_node(card)

        # Si la imagen está en un enlace vecino, buscar en el contenedor.
        if not image:
            parent = card
            for _ in range(3):
                parent = parent.parent if parent else None
                if not parent:
                    break
                image = self.image_from_node(parent)
                if image:
                    break

        return {
            "id": self.slug_from_url(url) or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-"),
            "title": title,
            "type": movie_type,
            "url": url,
            "source_url": source_url,
            "release_date": release_date,
            "image": image,
            "description": "",
        }

    def find_movie_blocks(self, soup):
        """
        Detecta las tarjetas de cine aunque cambien las clases del tema.
        La estrategia principal busca enlaces /estrenos-cine/ y asciende
        hasta un contenedor razonable.
        """
        results = []

        for a in soup.find_all("a", href=True):
            href = self.absolute(a.get("href"))
            if "/estrenos-cine/" not in href:
                continue

            # /estrenos-cine/ es el índice general, no una película.
            parsed_path = urlparse(href).path.rstrip("/")
            if parsed_path == "/estrenos-cine":
                continue

            title = self.clean(a)
            if not title:
                h = a.find(["h1", "h2", "h3", "h4", "h5"])
                title = self.clean(h)

            # Ascender buscando una tarjeta que tenga imagen o encabezado.
            node = a
            best = a

            for _ in range(5):
                node = node.parent
                if not node:
                    break

                txt = self.clean(node)
                img = self.image_from_node(node)
                has_heading = bool(node.find(["h2", "h3", "h4", "h5"]))

                # Evitar tomar toda la página.
                if len(txt) > 700:
                    break

                if img or has_heading:
                    best = node

            results.append((best, href, title))

        return results

    def extract_current_cinema(self, soup):
        """
        Extrae exclusivamente la sección cuyo encabezado/etiqueta
        indica "Cartelera vigente".
        """
        movies = []

        # Buscar encabezados con "Cartelera Cinemacenter".
        cine_heading = None
        for tag in soup.find_all(["h1", "h2", "h3"]):
            if "cartelera" in self.clean(tag).lower():
                cine_heading = tag
                break

        # Estrategia robusta: localizar todos los enlaces de películas
        # y decidir por la etiqueta de contexto cercana.
        seen = set()

        for a in soup.find_all("a", href=True):
            href = self.absolute(a["href"])
            if "/estrenos-cine/" not in href:
                continue

            # /estrenos-cine/ es el índice general, no una película.
            parsed_path = urlparse(href).path.rstrip("/")
            if parsed_path == "/estrenos-cine":
                continue

            title = self.clean(a)
            if not title:
                continue

            node = a
            context = ""

            # Buscar contexto hacia arriba, pero sin tragarnos toda la página.
            for _ in range(5):
                node = node.parent
                if not node:
                    break
                txt = self.clean(node)
                if txt and len(txt) < 1000:
                    context = txt
                    if "cartelera vigente" in txt.lower() or "próximo estreno" in txt.lower():
                        break

            low = context.lower()

            # Si el enlace está asociado a un bloque de próximo estreno,
            # no incluirlo en vigente.
            if "próximo estreno" in low or "proximo estreno" in low:
                continue

            # Si contiene "cartelera vigente", es una coincidencia fuerte.
            if "cartelera vigente" not in low:
                continue

            # Subir a una tarjeta para obtener imagen.
            card = a
            for _ in range(4):
                card = card.parent
                if not card:
                    break
                if self.image_from_node(card):
                    break

            item = self.parse_movie_card(card or a, HOME, "cartelera_vigente")
            if not item:
                item = {
                    "id": self.slug_from_url(href),
                    "title": title,
                    "type": "cartelera_vigente",
                    "url": href,
                    "source_url": HOME,
                    "release_date": "",
                    "image": "",
                    "description": "",
                }

            key = item["url"] or item["title"]
            if key not in seen:
                seen.add(key)
                movies.append(item)

        return movies

    def extract_upcoming_cinema(self, soup):
        movies = []
        seen = set()

        for a in soup.find_all("a", href=True):
            href = self.absolute(a["href"])
            if "/estrenos-cine/" not in href:
                continue

            title = self.clean(a)
            if not title:
                continue

            node = a
            context = ""

            for _ in range(5):
                node = node.parent
                if not node:
                    break
                txt = self.clean(node)
                if txt and len(txt) < 1000:
                    context = txt
                    if "próximo estreno" in txt.lower() or "proximo estreno" in txt.lower():
                        break

            low = context.lower()
            if "próximo estreno" not in low and "proximo estreno" not in low:
                continue

            card = a
            for _ in range(4):
                card = card.parent
                if not card:
                    break
                if self.image_from_node(card):
                    break

            item = self.parse_movie_card(card or a, HOME, "proximos_estrenos")
            if item:
                key = item["url"] or item["title"]
                if key not in seen:
                    seen.add(key)
                    movies.append(item)

        return movies

    def enrich_movie(self, movie):
        """
        Visita la ficha individual para completar imagen/descripción/fecha.
        Si la ficha no aporta datos, conserva lo encontrado en portada.
        """
        r = self.get(movie["url"])
        if not r:
            return movie

        soup = BeautifulSoup(r.text, "html.parser")

        if not movie.get("image"):
            movie["image"] = self.image_from_node(soup)

        # Meta image suele ser la mejor fuente.
        for prop in ("og:image", "twitter:image"):
            meta = soup.find("meta", attrs={"property": prop}) or soup.find(
                "meta", attrs={"name": prop}
            )
            if meta and meta.get("content"):
                movie["image"] = self.absolute(meta["content"])
                break

        if not movie.get("description"):
            meta = soup.find("meta", attrs={"name": "description"})
            if meta and meta.get("content"):
                movie["description"] = self.clean(meta["content"])

        if not movie.get("release_date"):
            text = self.clean(soup)
            m = re.search(
                r"(?:Estreno|Fecha de estreno)\s*:\s*"
                r"([0-9]{1,2}\s+[A-Za-zÁÉÍÓÚáéíóúÑñ]+\s+[0-9]{4})",
                text,
                re.I,
            )
            if m:
                movie["release_date"] = m.group(1)

        return movie

    def parse_release_date(self, value):
        """Convierte fechas españolas habituales a date."""
        if not value:
            return None
        text = self.clean(value).lower()
        text = re.sub(r"[,|]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        months = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
            "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
            "septiembre": 9, "setiembre": 9, "octubre": 10,
            "noviembre": 11, "diciembre": 12,
        }
        # Normalizar acentos del mes.
        text = text.replace("setiembre", "septiembre")
        m = re.search(
            r"\b(\d{1,2})\s+([a-záéíóúñ]+)\s+(\d{4})\b", text, re.I
        )
        if not m:
            m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", text)
            if m:
                try:
                    return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date()
                except ValueError:
                    return None
            return None

        day = int(m.group(1))
        month = months.get(m.group(2).lower())
        year = int(m.group(3))
        if not month:
            return None
        try:
            return datetime(year, month, day).date()
        except ValueError:
            return None

    def extract_release_date_from_text(self, text):
        """Busca una fecha de estreno tanto con etiqueta como en texto cercano."""
        text = self.clean(text)
        patterns = [
            r"(?:estreno|fecha de estreno)\s*:?\s*(\d{1,2}\s+[A-Za-zÁÉÍÓÚáéíóúÑñ]+\s+\d{4})",
            r"(?:estreno|fecha de estreno)\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.I)
            if m:
                return m.group(1)
        return ""

    def extract_cinema(self):
        """
        Extrae únicamente cine útil para la aplicación:
          - cartelera vigente: estrenos de los últimos 14 días hasta hoy;
          - próximos estrenos: estrenos posteriores a hoy.

        No recorre el archivo histórico /estrenos-cine/ como catálogo.
        """
        today = datetime.now().astimezone().date()
        cutoff = today.fromordinal(today.toordinal() - 14)

        r = self.get(HOME)
        if not r:
            return {
                "schema_version": "5.0",
                "generated_at": self.now(),
                "reference_date": today.isoformat(),
                "current_window_start": cutoff.isoformat(),
                "current_source": HOME,
                "movies": [],
            }

        soup = BeautifulSoup(r.text, "html.parser")
        candidates = self.extract_current_cinema(soup) + self.extract_upcoming_cinema(soup)

        # Deduplicar antes de visitar fichas individuales.
        unique_candidates = []
        seen = set()
        for movie in candidates:
            url = movie.get("url", "")
            path = urlparse(url).path.rstrip("/").lower()
            if path == "/estrenos-cine":
                continue
            key = url or movie.get("title", "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            unique_candidates.append(movie)

        final = []
        for movie in unique_candidates:
            try:
                self.enrich_movie(movie)
            except Exception as e:
                self.errors.append({
                    "url": movie.get("url", ""),
                    "error": f"enriquecimiento cine: {e}",
                })

            release_text = movie.get("release_date", "")
            release = self.parse_release_date(release_text)

            # Si la ficha tenía una fecha pero el parser de la tarjeta no la
            # capturó, intentar nuevamente con la descripción/título disponible.
            if release is None:
                release_text = self.extract_release_date_from_text(
                    movie.get("description", "")
                ) or release_text
                release = self.parse_release_date(release_text)

            # Sin fecha no podemos garantizar que pertenezca a la ventana.
            if release is None:
                continue

            movie["release_date"] = release.isoformat()
            movie["reference_date"] = today.isoformat()

            if release > today:
                movie["type"] = "proximos_estrenos"
            elif cutoff <= release <= today:
                movie["type"] = "cartelera_vigente"
            else:
                # Histórico: queda fuera del JSON de la app.
                continue

            final.append(movie)

        # Orden cronológico: próximos desde el estreno más cercano; vigentes
        # desde el estreno más reciente.
        final.sort(key=lambda x: (x.get("type") != "cartelera_vigente", x.get("release_date", "")))

        return {
            "schema_version": "5.0",
            "generated_at": self.now(),
            "reference_date": today.isoformat(),
            "current_window_start": cutoff.isoformat(),
            "current_source": HOME,
            "movies": final,
            "current_count": sum(1 for x in final if x.get("type") == "cartelera_vigente"),
            "upcoming_count": sum(1 for x in final if x.get("type") == "proximos_estrenos"),
        }

    # ---------------------------------------------------------
    # RADIO / SHOCK MEDIA / SONICPANEL
    # ---------------------------------------------------------

    @staticmethod
    def looks_like_audio_url(url):
        if not url:
            return False

        u = url.lower()

        patterns = (
            ".mp3",
            ".aac",
            ".ogg",
            ".m3u",
            ".m3u8",
            "/stream",
            "/listen",
            "/radio",
            "/live",
            "icecast",
            "shoutcast",
        )

        return any(p in u for p in patterns)

    def parse_radio_player(self):
        """
        Intenta descubrir URLs dentro del HTML/JS del widget.
        No fuerza una URL: devuelve únicamente las que aparecen
        realmente en la respuesta.
        """
        result = {
            "player_url": RADIO_PLAYER_URL,
            "provider": "Shock Media / SonicPanel",
            "player_id": "8718",
            "api_url": RADIO_API_URL,
            "stream_urls": [],
            "audio_urls": [],
            "external_urls": [],
            "raw_candidates": [],
            "http_status": None,
        }

        r = self.get(RADIO_PLAYER_URL)

        if r:
            result["http_status"] = r.status_code

            text = r.text
            soup = BeautifulSoup(text, "html.parser")

            candidates = []

            # Atributos de tags.
            for tag in soup.find_all(True):
                for attr in (
                    "src",
                    "href",
                    "data-src",
                    "data-url",
                    "data-stream",
                    "data-audio",
                    "data-play-url",
                    "data-stream-url",
                ):
                    value = tag.get(attr)
                    if value:
                        candidates.append(self.absolute(value, RADIO_PLAYER_URL))

            # URLs escritas en JS/HTML.
            candidates += re.findall(
                r'https?://[^"\'\s<>\\]+',
                text,
                flags=re.I,
            )

            # Protocolos de audio sin http explícito.
            candidates += re.findall(
                r'(?:https?|icy)://[^"\'\s<>\\]+',
                text,
                flags=re.I,
            )

            candidates = self.unique(
                self.normalize_url(x).rstrip(");,")
                for x in candidates
            )

            result["raw_candidates"] = candidates

            for url in candidates:
                low = url.lower()

                # Stream real: extensiones de audio, /stream, /listen,
                # /live o protocolos de streaming. JS/CSS/imágenes quedan fuera.
                is_direct_stream = bool(
                    re.search(r"\.(mp3|aac|ogg|wav|m4a|m3u|m3u8)(?:\?|$)", low)
                    or re.search(r"/(?:stream|listen|live)(?:\?|$)", low)
                    or low.startswith("icy://")
                )

                if is_direct_stream:
                    result["stream_urls"].append(url)

                if re.search(r"\.(mp3|aac|ogg|wav|m4a)(?:\?|$)", low):
                    result["audio_urls"].append(url)

                if "spotify.com" in low or "youtube.com" in low or "youtu.be" in low:
                    result["external_urls"].append(url)

            result["stream_urls"] = self.unique(result["stream_urls"])
            result["audio_urls"] = self.unique(result["audio_urls"])
            result["external_urls"] = self.unique(result["external_urls"])

        # Consulta adicional del endpoint de SonicPanel.
        ar = self.get(RADIO_API_URL)

        result["api"] = {
            "url": RADIO_API_URL,
            "http_status": ar.status_code if ar else None,
            "stream_urls": [],
            "raw": "",
        }

        if ar:
            raw = ar.text.strip()
            result["api"]["raw"] = raw[:10000]

            # Puede ser JSON o HTML/texto.
            try:
                data = ar.json()
                result["api"]["json"] = data

                # Buscar recursivamente strings que parezcan URLs.
                def walk(value):
                    if isinstance(value, dict):
                        for v in value.values():
                            yield from walk(v)
                    elif isinstance(value, list):
                        for v in value:
                            yield from walk(v)
                    elif isinstance(value, str):
                        yield value

                values = list(walk(data))
            except Exception:
                values = re.findall(
                    r'https?://[^"\'\s<>\\]+',
                    raw,
                    flags=re.I,
                )

            for value in values:
                if self.looks_like_audio_url(value):
                    result["api"]["stream_urls"].append(value)

            result["api"]["stream_urls"] = self.unique(
                result["api"]["stream_urls"]
            )

            result["stream_urls"].extend(result["api"]["stream_urls"])
            result["stream_urls"] = self.unique(result["stream_urls"])

        return result

    def extract_radio(self):
        # La página de radio se conserva como fuente principal.
        page = {
            "url": RADIO_URL,
            "title": "Agenda Radio",
            "description": "",
        }

        r = self.get(RADIO_URL)

        if r:
            soup = BeautifulSoup(r.text, "html.parser")

            title = soup.find("h1")
            if title:
                page["title"] = self.clean(title)

            meta = soup.find("meta", attrs={"name": "description"})
            if meta:
                page["description"] = self.clean(meta.get("content"))

        player = self.parse_radio_player()

        # Buscar además links de streaming visibles en la página.
        page_streams = []
        if r:
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = self.absolute(a["href"])
                low = href.lower()
                if (
                    re.search(r"\.(mp3|aac|ogg|wav|m4a|m3u|m3u8)(?:\?|$)", low)
                    or re.search(r"/(?:stream|listen|live)(?:\?|$)", low)
                    or low.startswith("icy://")
                ):
                    page_streams.append(href)

        player["stream_urls"] = self.unique(
            player.get("stream_urls", []) + page_streams
        )

        # Último filtro: solo URLs que realmente puedan ser streams de audio.
        # Esto elimina imágenes como nowplay_*.png y nodj.png que SonicPanel
        # también expone dentro del widget.
        def is_real_stream(url):
            low = str(url).lower().split("?", 1)[0].rstrip("/")
            return bool(
                re.search(r"\.(mp3|aac|ogg|wav|m4a|m3u|m3u8)$", low)
                or re.search(r"/(stream|listen|live)$", low)
                or low.startswith("icy://")
            )

        player["stream_urls"] = self.unique(
            u for u in player.get("stream_urls", []) if is_real_stream(u)
        )
        player["audio_urls"] = self.unique(
            u for u in player.get("audio_urls", []) if is_real_stream(u)
        )

        return {
            "schema_version": "4.0",
            "generated_at": self.now(),
            "page": page,
            "player": player,
            "stream_urls": player["stream_urls"],
            "audio_urls": player.get("audio_urls", []),
            "spotify_urls": [],
            "youtube_urls": [],
            "external_urls": player.get("external_urls", []),
        }

    # ---------------------------------------------------------
    # OUTPUT
    # ---------------------------------------------------------

    @staticmethod
    def now():
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    def save_json(self, filename, data):
        path = OUT_DIR / filename
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def save_report(self, cine, radio):
        report = []

        report.append("INFORME EXTRACCIÓN AGENDA TUCUMÁN V5")
        report.append("=" * 60)
        report.append(f"Fecha: {self.now()}")
        report.append("")

        movies = cine.get("movies", [])
        current = [x for x in movies if x.get("type") == "cartelera_vigente"]
        upcoming = [x for x in movies if x.get("type") == "proximos_estrenos"]

        report.append("CINE")
        report.append("-" * 60)
        report.append(f"Total películas: {len(movies)}")
        report.append(f"Cartelera vigente: {len(current)}")
        report.append(f"Próximos estrenos: {len(upcoming)}")
        report.append("")

        for movie in movies:
            report.append(
                f"- [{movie.get('type')}] "
                f"{movie.get('title')} | {movie.get('url')}"
            )

        report.append("")
        report.append("RADIO")
        report.append("-" * 60)
        report.append(f"Página: {radio.get('page', {}).get('url')}")
        report.append(f"Player: {radio.get('player', {}).get('player_url')}")
        report.append(f"Provider: {radio.get('player', {}).get('provider')}")
        report.append(f"Player ID: {radio.get('player', {}).get('player_id')}")
        report.append(f"API: {radio.get('player', {}).get('api_url')}")
        report.append(
            f"Streams encontrados: "
            f"{len(radio.get('stream_urls', []))}"
        )

        for url in radio.get("stream_urls", []):
            report.append(f"- STREAM: {url}")

        report.append("")
        report.append("HTTP")
        report.append("-" * 60)
        report.append(f"Requests OK: {len(self.ok)}")
        report.append(f"Errores: {len(self.errors)}")

        if self.errors:
            report.append("")
            for error in self.errors:
                report.append(
                    f"- {error.get('url')}: {error.get('error')}"
                )

        path = OUT_DIR / "informe_contenidos.txt"
        path.write_text("\n".join(report), encoding="utf-8")
        return path

    def run(self):
        print("=" * 70)
        print("AGENDA TUCUMÁN - EXTRACTOR V5")
        print("=" * 70)
        print()

        print("[1/2] Extrayendo cine (últimos 14 días + futuros)...")
        cine = self.extract_cinema()

        print("[2/2] Extrayendo radio + Shock Media...")
        radio = self.extract_radio()

        self.save_json("cine_tucuman.json", cine)
        self.save_json("radio_tucuman.json", radio)

        errors_path = OUT_DIR / "errores_contenidos.json"
        errors_path.write_text(
            json.dumps(
                {
                    "generated_at": self.now(),
                    "errors": self.errors,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        self.save_report(cine, radio)

        print()
        print("=" * 70)
        print("RESULTADO")
        print("=" * 70)
        print(f"Cine total:          {len(cine.get('movies', []))}")
        print(
            "Cartelera vigente:   "
            f"{sum(1 for x in cine.get('movies', []) if x.get('type') == 'cartelera_vigente')}"
        )
        print(
            "Próximos estrenos:   "
            f"{sum(1 for x in cine.get('movies', []) if x.get('type') == 'proximos_estrenos')}"
        )
        print(f"Radio streams:       {len(radio.get('stream_urls', []))}")
        print(f"Radio audio:         {len(radio.get('audio_urls', []))}")
        print(f"Requests OK:         {len(self.ok)}")
        print(f"Errores:             {len(self.errors)}")
        print()
        print("Archivos generados:")
        print("  cine_tucuman.json")
        print("  radio_tucuman.json")
        print("  errores_contenidos.json")
        print("  informe_contenidos.txt")


if __name__ == "__main__":
    try:
        Extractor().run()
    except KeyboardInterrupt:
        print("\nCancelado por el usuario.")
        sys.exit(130)
    except Exception as e:
        print(f"\nERROR FATAL: {e}")
        sys.exit(1)
