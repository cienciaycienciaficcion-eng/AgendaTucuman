#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AGENDA TUCUMÁN - EXTRACCIÓN MEC V11.2

Fuente principal:
    https://agendatucuman.com.ar/eventos/

MEC:
    POST /wp-admin/admin-ajax.php
    action=mec_tile_load_month

Enfoque V10:
- MEC es la fuente primaria de fecha/hora visibles.
- Filtra tarjetas según el mes realmente consultado.
- Deduplica por MEC ID.
- Conserva ocurrencias individuales para eventos de varios días.
- Construye datetimes locales de Tucumán sin conversión UTC.
- Prioridad de horario:
      tarjeta MEC > contenido editorial > JSON-LD
- Hora de fin opcional: si la fuente sólo informa inicio, time_end queda vacío.
- No se inventa una hora de fin a partir de la hora de inicio.
- Prioridad de fecha:
      rango explícito del título/contenido > tarjeta MEC > JSON-LD
- Limpia HTML residual de lugares.
- Extrae dirección y ciudad.
- Detecta enlaces de inscripción/reserva/entradas.
- Google Calendar y enlaces sociales no son inscripción.
- REST WordPress se usa para enriquecer el registro.
"""

import argparse
import html
import csv
import json
import re
import time
from collections import OrderedDict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import quote_plus
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE = "https://agendatucuman.com.ar"
EVENTOS_URL = BASE + "/eventos/"
AJAX_URL = BASE + "/wp-admin/admin-ajax.php"
REST_EVENT = BASE + "/wp-json/wp/v2/mec-events/{id}?_embed=1"
REST_CATEGORY = BASE + "/wp-json/wp/v2/mec_category"
REST_TAGS = BASE + "/wp-json/wp/v2/tags"
REST_MEDIA = BASE + "/wp-json/wp/v2/media"

TZ = "-03:00"
ARGENTINA_TZ = ZoneInfo("America/Argentina/Tucuman")

MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/140 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.7",
}


def clean_text(value):
    if value is None:
        return ""
    value = BeautifulSoup(str(value), "html.parser").get_text(" ", strip=True)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t\r\n|-")


def strip_html(value):
    if not value:
        return ""
    return clean_text(value)


def uniq(values):
    out = []
    seen = set()
    for v in values or []:
        v = str(v).strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--start-year", type=int, default=2026)
    p.add_argument("--start-month", type=int, default=9)
    p.add_argument("--months", type=int, default=12)
    p.add_argument("--lookback-months", type=int, default=2, help="Meses anteriores adicionales para capturar eventos en curso")
    p.add_argument("--delay", type=float, default=0.15)
    p.add_argument("--out", default="agenda_extraccion_mec_v7")
    return p.parse_args()


def month_sequence(year, month, count):
    result = []
    y, m = year, month
    for _ in range(count):
        result.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return result


def normalize_month_name(s):
    return MONTHS_ES.get((s or "").lower().strip())


def make_local_datetime(d, hhmm):
    if not d:
        return ""
    if not hhmm:
        return f"{d}T00:00:00{TZ}"
    return f"{d}T{hhmm}:00{TZ}"


def parse_time_token(token):
    if not token:
        return ""
    s = token.lower().strip()
    s = s.replace(".", ":")
    s = s.replace("hs", "").replace("h", "")
    s = s.strip()
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\b", s)
    if not m:
        return ""
    hh = int(m.group(1))
    mm = int(m.group(2) or 0)
    if hh > 23 or mm > 59:
        return ""
    return f"{hh:02d}:{mm:02d}"


def extract_time_range(text):
    text = strip_html(text)
    if not text:
        return "", ""

    patterns = [
        r"(?:de|desde)\s+las?\s+(\d{1,2}(?::\d{2})?)\s*(?:a|hasta|-)\s*(?:las?\s*)?(\d{1,2}(?::\d{2})?)",
        r"entre\s+las?\s+(\d{1,2}(?::\d{2})?)\s*(?:y|a|-)\s*(?:las?\s*)?(\d{1,2}(?::\d{2})?)",
        r"(\d{1,2}(?::\d{2})?)\s*(?:a|hasta|-)\s*(\d{1,2}(?::\d{2})?)\s*(?:horas?|hs\.?|h\b)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return parse_time_token(m.group(1)), parse_time_token(m.group(2))

    m = re.search(
        r"(?:a partir de|a las?|desde las?|horario(?: de)?|largada:|hora:)\s*"
        r"(\d{1,2}(?::\d{2})?)\s*(?:horas?|hs\.?|h\b)?",
        text, re.I
    )
    if m:
        return parse_time_token(m.group(1)), ""

    return "", ""


def extract_mec_card_time(article):
    # La tarjeta visible suele contener:
    # "3 Oct 08:00 Título"
    text = clean_text(article.get_text(" ", strip=True))
    m = re.search(
        r"\b(?:\d{1,2}\s+)?(?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)"
        r"\b\s+(\d{1,2}:\d{2})\b",
        text, re.I
    )
    if m:
        return parse_time_token(m.group(1)), ""

    # fallback: cualquier hora visible en la cabecera de la tarjeta
    head = article.get_text(" ", strip=True)[:500]
    m = re.search(r"\b(\d{1,2}:\d{2})\b", head)
    if m:
        return parse_time_token(m.group(1)), ""

    return "", ""


def parse_title_dates(title, default_year):
    """
    Devuelve (start_date, end_date, source, score).

    Casos:
      30 de septiembre al 2 de octubre
      8, 9, 10 y 11 de octubre
      9, 10 y 11 de octubre
      3 de octubre
      Octubre
    """
    t = clean_text(title).lower()
    if not t:
        return "", "", "", 0

    # rango explícito: 30 de septiembre al 2 de octubre
    m = re.search(
        r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+"
        r"(?:al|hasta|-)\s+(\d{1,2})\s+de\s+([a-záéíóúñ]+)",
        t, re.I
    )
    if m:
        d1, mo1 = int(m.group(1)), normalize_month_name(m.group(2))
        d2, mo2 = int(m.group(3)), normalize_month_name(m.group(4))
        if mo1 and mo2:
            y1 = default_year
            y2 = default_year + (1 if mo2 < mo1 else 0)
            try:
                a = date(y1, mo1, d1)
                b = date(y2, mo2, d2)
                return a.isoformat(), b.isoformat(), "title_range", 0.95
            except ValueError:
                pass

    # lista: 8, 9, 10 y 11 de octubre
    m = re.search(
        r"(\d{1,2}(?:\s*,\s*\d{1,2})*(?:\s*,)?\s+y\s+\d{1,2})\s+de\s+([a-záéíóúñ]+)",
        t, re.I
    )
    if m:
        nums = [int(x) for x in re.findall(r"\d{1,2}", m.group(1))]
        mo = normalize_month_name(m.group(2))
        if nums and mo:
            try:
                dates = [date(default_year, mo, n) for n in nums]
                return min(dates).isoformat(), max(dates).isoformat(), "title_days", 0.95
            except ValueError:
                pass

    # un solo día
    m = re.search(r"\b(\d{1,2})\s+de\s+([a-záéíóúñ]+)\b", t, re.I)
    if m:
        d = int(m.group(1))
        mo = normalize_month_name(m.group(2))
        if mo:
            try:
                dt = date(default_year, mo, d)
                return dt.isoformat(), dt.isoformat(), "title_day", 0.95
            except ValueError:
                pass

    return "", "", "", 0


def parse_card_date(article, query_year, query_month):
    """
    Lee la fecha real mostrada por MEC.
    No toma la fecha de publicación de WordPress.
    """
    text = clean_text(article.get_text(" ", strip=True))

    # 30 Sep ...
    months_abbr = {
        "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
        "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
    }
    m = re.search(
        r"\b(\d{1,2})\s+(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)\b",
        text, re.I
    )
    if m:
        d = int(m.group(1))
        mo = months_abbr[m.group(2).lower()]
        try:
            dt = date(query_year, mo, d)
            return dt.isoformat(), 1.0
        except ValueError:
            pass

    # fallback: día numérico de la tarjeta
    m = re.search(r"\b(\d{1,2})\b", text)
    if m:
        d = int(m.group(1))
        try:
            dt = date(query_year, query_month, d)
            return dt.isoformat(), 0.35
        except ValueError:
            pass

    return "", 0


def parse_jsonld(soup):
    items = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
            if isinstance(obj, list):
                items.extend(obj)
            else:
                items.append(obj)
        except Exception:
            continue
    return items


def flatten_jsonld(items):
    out = []

    def walk(x):
        if isinstance(x, dict):
            out.append(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    for item in items:
        walk(item)
    return out


def jsonld_event(items):
    for x in flatten_jsonld(items):
        typ = x.get("@type")
        types = typ if isinstance(typ, list) else [typ]
        if any(str(t).lower() in {"event", "business", "sportsEvent".lower()} for t in types):
            return x
    for x in flatten_jsonld(items):
        if "startDate" in x or "endDate" in x:
            return x
    return {}


def extract_jsonld_datetime(obj, key):
    """Siempre devuelve una tupla (fecha, hora), incluso si el campo no existe."""
    value = obj.get(key) if isinstance(obj, dict) else None
    if not value:
        return "", ""
    s = str(value)
    m = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})", s)
    if m:
        return m.group(1), m.group(2)
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        return m.group(1), ""
    return "", ""


def clean_location(value):
    """Normaliza un nombre de lugar sin absorber texto narrativo."""
    if not value:
        return ""
    s = str(value)
    s = re.sub(r"</?strong[^>]*>", " ", s, flags=re.I)
    s = strip_html(s)
    s = re.sub(r"^(?:📍\s*)?(?:lugar|ubicación|ubicacion|sede|dirección|direccion|punto de partida)\s*:\s*", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" .,:;|–—-\n\t")
    # Emojis al final suelen ser separadores de la siguiente ficha.
    s = re.sub(r"\s+[🔥🏆🌎🇦🇷👥🎶🎟️🤝📅🕗🕓🕐🎈💙]+\s*$", "", s)
    return s.strip(" .,:;|–—-")


def _trim_place(value):
    """Recorta un lugar cuando el regex capturó el comienzo del texto siguiente."""
    if not value:
        return ""
    s = clean_location(value)
    # Separadores típicos de bloques/fichas.
    s = re.split(r"\s+(?:actividad|lema|convoca|organizan|organiza|entrada|inscripción|inscripcion|participación|participacion|fecha|hora|horario|evento|premio|competidores)\s*:", s, maxsplit=1, flags=re.I)[0]
    # Evita que el nombre del evento quede pegado al lugar.
    s = re.split(r"\s+el\s+\d{1,3}(?:°|º|ª)?\s+", s, maxsplit=1, flags=re.I)[0]
    s = re.split(r"\s+la\s+\d{1,3}(?:°|º|ª)?\s+", s, maxsplit=1, flags=re.I)[0]
    return clean_location(s)



def _looks_like_address(value):
    """Determina si un texto parece una dirección física y no un nombre."""
    s = clean_location(value)
    if not s:
        return False
    if re.search(r"\b\d{1,5}\b", s):
        return True
    if re.search(
        r"\b(?:av\.?|avenida|calle|pasaje|pje\.?|ruta|camino|boulevard|bvd\.?|"
        r"esquina|esq\.?)\b",
        s,
        re.I,
    ):
        return True
    # Intersecciones como "Jujuy y Crisóstomo Álvarez".
    if re.search(r"\s+y\s+", s, re.I) and len(s.split()) >= 3:
        return True
    return False


def extract_highlighted_metadata(text):
    """Extrae campos del bloque editorial 'Datos destacados'.

    El sitio está incorporando al final de algunos artículos un bloque
    semiestructurado con etiquetas como:
        📍 Lugar: Centro Cultural Virla
        📌 Dirección: San Martín 251, San Miguel de Tucumán

    Se usa como fuente prioritaria cuando está presente, pero NO reemplaza
    los extractores narrativos/laterales para artículos que no tienen este
    bloque.
    """
    text = strip_html(text)
    marker = re.search(r"\bDatos\s+destacados\b", text, re.I)
    if not marker:
        return {}

    tail = text[marker.end():].strip(" :-–—")

    # Un nuevo campo del bloque suele comenzar con un emoji y una etiqueta
    # seguida de ':'. La expresión es deliberadamente amplia para aceptar
    # etiquetas nuevas sin tener que actualizar el extractor cada vez.
    emoji = r"[\U0001F000-\U0001FAFF\u2600-\u27BF](?:\uFE0F|\u200D[\U0001F000-\U0001FAFF\u2600-\u27BF])*"
    label = r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ][^:]{0,70}?"
    next_field = rf"(?=\s+(?:{emoji}\s*)+{label}\s*:|$)"
    pattern = re.compile(
        rf"(?:^|\s)(?:{emoji}\s*)?(?P<label>{label})\s*:\s*"
        rf"(?P<value>.*?){next_field}",
        re.I | re.S,
    )

    fields = {}
    for match in pattern.finditer(tail):
        key = re.sub(r"\s+", " ", match.group("label")).strip().lower()
        value = clean_location(match.group("value"))
        if value:
            if key in fields:
                if isinstance(fields[key], list):
                    fields[key].append(value)
                else:
                    fields[key] = [fields[key], value]
            else:
                fields[key] = value

    return fields


def remove_highlighted_metadata_block(text, fields=None):
    """Quita el bloque final `Datos destacados` de la descripción.

    Sólo elimina el bloque cuando realmente fue reconocido como ficha
    estructurada; si el texto menciona esas palabras sin campos válidos,
    conserva la descripción original.
    """
    if not text:
        return text
    plain = strip_html(text)
    parsed = fields if fields is not None else extract_highlighted_metadata(plain)
    if len(parsed) < 2:
        return text
    marker = re.search(r"\bDatos\s+destacados\b", plain, re.I)
    if not marker:
        return text
    # El bloque editorial está al final del contenido.
    cleaned = plain[:marker.start()].strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

    # Los campos estructurados ya se guardan por separado y la app no
    # necesariamente renderiza todos los campos arbitrarios de
    # `highlighted_metadata`. Para no perder esa información en
    # "Información completa", reconstruimos sólo los campos adicionales
    # como texto limpio, sin conservar el encabezado "Datos destacados"
    # ni duplicar los campos básicos que la app ya muestra en la ficha.
    if parsed:
        hidden_in_card = {
            "fecha", "fechas", "hora", "horario", "horarios",
            "lugar", "sede", "ubicación", "ubicacion",
            "dirección", "direccion", "dirección del lugar",
            "direccion del lugar",
        }
        extra_lines = []
        for key, value in parsed.items():
            if key in hidden_in_card:
                continue
            values = value if isinstance(value, list) else [value]
            label = key[:1].upper() + key[1:]
            for item in values:
                item = clean_location(item)
                if item:
                    extra_lines.append(f"{label}: {item}")

        if extra_lines:
            if cleaned:
                cleaned += "\n\n"
            cleaned += "\n".join(extra_lines)

    return cleaned


def _field_values(fields, key):
    value = fields.get(key)
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def extract_highlighted_location(text):
    """Obtiene Lugar/Ubicación y Dirección del bloque 'Datos destacados'."""
    fields = extract_highlighted_metadata(text)
    if not fields:
        return "", "", "", "", 0

    location = ""
    location_key = ""
    for key in ("lugar", "sede", "punto de encuentro", "ubicación", "ubicacion"):
        values = _field_values(fields, key)
        if values:
            location = values[0]
            location_key = key
            break

    address = ""
    address_key = ""

    # "Dirección" puede aparecer dos veces: como nombre del director de la
    # obra y como dirección física. Buscamos entre todas sus apariciones la
    # que realmente tenga aspecto de dirección.
    for key in ("dirección", "direccion", "dirección del lugar", "direccion del lugar"):
        for candidate in _field_values(fields, key):
            if candidate and _looks_like_address(candidate):
                address = candidate
                address_key = key
                break
        if address:
            break

    # Algunas notas usan "Ubicación:" en lugar de "Dirección:" para indicar
    # la referencia física del lugar. Sólo la usamos como dirección si tiene
    # evidencia de calle/número/intersección.
    if not address:
        for key in ("ubicación", "ubicacion"):
            for candidate in _field_values(fields, key):
                if candidate and _looks_like_address(candidate):
                    address = candidate
                    address_key = key
                    break
            if address:
                break

    return (
        clean_location(location),
        clean_location(address),
        f"highlighted_{location_key}" if location_key else "",
        f"highlighted_{address_key}" if address_key else "",
        0.99 if location or address else 0,
    )


def extract_labeled_location(text):
    text = strip_html(text)
    patterns = [
        # Fichas explícitas: Lugar: ..., Ubicación: ..., Sede: ...
        r"(?:📍\s*)?(?:lugar|ubicación|ubicacion|sede)\s*:\s*(.+?)(?=\s+(?:🔥|🏆|🌎|🇦🇷|👥|🎶|🎟️|🤝|📅|🕗|🕓|🕐|🎈|💙)|\s+(?:actividad|lema|convoca|organizan|organiza|entrada|inscripción|inscripcion|participación|participacion|fecha|hora|horario|evento|premio|competidores)\s*:|$)",
        r"(?:punto de partida)\s*:\s*(.+?)(?=\s+(?:distancias|modalidad|inscripción|inscripcion|organizan|organiza|evento|fecha|horario)\s*:|$)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I | re.S)
        if m:
            v = _trim_place(m.group(1))
            if v and len(v) <= 160:
                return v, "label", 0.95
    return "", "", 0


def extract_narrative_location(text):
    text = strip_html(text)
    patterns = [
        # Venue + address clause: capture until the comma before "ubicado/ubicada".
        r"(?:actividades se desarrollarán principalmente en|actividades se desarrollaran principalmente en)\s+(?:el|la)?\s*(.+?)(?=,\s*(?:ubicado|ubicada)\s+en|$)",
        # Generic event-location constructions.
        r"(?:se realizará|se realizara|se lleva a cabo|se llevará a cabo|se llevara a cabo|se llevarán a cabo|se llevaran a cabo|tendrá lugar|tendra lugar)\s+en\s+(?:el|la)\s+(.+?)(?=[.!?](?:\s|$)|\s+el\s+\d{1,3}(?:°|º|ª)?\s+)",
        r"(?:se realizará|se realizara|se lleva a cabo|se llevará a cabo|se llevara a cabo|se llevarán a cabo|se llevaran a cabo|tendrá lugar|tendra lugar)\s+en\s+(?:el|la)\s+(.+?)(?=[.!?](?:\s|$)|$)",
        r"(?:punto de partida(?: será| es)?|con punto de partida)\s+(?:la|el)?\s*(.+?)(?=[.!?](?:\s|$)|$)",
        r"\ben\s+(?:el|la)\s+([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑ0-9'’./\- ]{2,100}?)(?=[.!?](?:\s|$)|$)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.I | re.S):
            v = _trim_place(m.group(1))
            if not v or len(v) < 3 or len(v) > 120:
                continue
            if re.search(r"\b(?:se realizará|se llevará|se llevarán|tendrá lugar|el próximo|los próximos|este próximo)\b", v, re.I):
                continue
            return v, "narrative", 0.65
    return "", "", 0

def extract_address(text):
    """Extrae direcciones sólo cuando la fuente aporta evidencia suficiente."""
    text = strip_html(text)
    patterns = [
        r"(?:dirección|direccion)\s*:\s*([^.;\n]+)",
        r"(?:ubicado|ubicada)\s+en\s+([A-ZÁÉÍÓÚÑ][^.;\n]{2,100}?\s+\d{1,5})(?=\s*,|[.;]|$)",
        r"\b(?:calle|av\.?|avenida|pasaje|pje\.?|ruta|camino|boulevard|bvd\.?)\s+([A-ZÁÉÍÓÚÑ][^.;\n]{1,80}?)\s+(\d{1,5})\b",
    ]
    stop_words = re.compile(r"\b(?:se realizará|se llevar|el próximo|el proximo|los días|los dias|evento|actividad|festival|congreso)\b", re.I)
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if not m:
            continue
        if len(m.groups()) == 2:
            value = f"{m.group(1).strip()} {m.group(2).strip()}"
        else:
            value = m.group(1).strip()
        value = clean_location(value)
        if not value or not re.search(r"\d", value):
            continue
        if stop_words.search(value):
            continue
        if re.match(r"^(?:el|la|los|las|próximo|proximo|día|dia|sábado|sabado|domingo)\b", value, re.I):
            continue
        return value, "address", 0.95 if re.search(r"dirección|direccion", pat, re.I) else 0.9
    return "", "", 0

def infer_city(text, location="", address=""):
    source = f"{location} {address} {strip_html(text)}"

    cities = [
        "San Miguel de Tucumán", "Tafí del Valle", "Tafí Viejo",
        "San Pedro de Colalao", "El Mollar", "Monteros", "Yerba Buena",
        "Concepción", "Aguilares", "Lules", "Banda del Río Salí",
        "Simoca", "Trancas", "Famaillá", "Bella Vista",
    ]
    low = source.lower()
    for city in cities:
        if city.lower() in low:
            return city

    return ""


def extract_links(soup, event_url):
    registration = []
    maps = []
    external = []

    bad_hosts = {
        "agendatucuman.com.ar",
        "agendacontenidos.com.ar",
        "facebook.com",
        "www.facebook.com",
        "x.com",
        "twitter.com",
        "www.twitter.com",
        "telegram.me",
        "www.telegram.me",
        "api.whatsapp.com",
        "calendar.google.com",
        "www.cinemacenter.com.ar",
        "pinterest.com",
        "www.pinterest.com",
    }

    registration_words = re.compile(
        r"(inscrib|registro|registrar|reserv|entrada|entradas|tickets?|ticket|"
        r"comprar|boleter|cronobot|eventbrite|passline|"
        r"tuentrada|autoentrada|ticketek)",
        re.I
    )
    map_words = re.compile(r"(maps\.google|google\.com/maps|openstreetmap|waze)", re.I)

    for a in soup.find_all("a", href=True):
        href = urljoin(event_url, a.get("href"))
        txt = clean_text(a.get_text(" ", strip=True))
        low = href.lower()

        if href.startswith("#") or href.startswith("javascript:"):
            continue

        if map_words.search(low):
            maps.append(href)
            continue

        if "calendar.google.com" in low:
            external.append(href)
            continue

        host = re.sub(r"^https?://", "", low).split("/")[0]
        if host in bad_hosts:
            external.append(href)
            continue

        if registration_words.search(txt) or registration_words.search(href):
            registration.append(href)
        elif href.startswith("http"):
            external.append(href)

    return uniq(registration), uniq(maps), uniq(external)


def explicit_free(text):
    t = strip_html(text).lower()
    phrases = [
        "entrada libre y gratuita",
        "entrada libre",
        "entrada gratuita",
        "acceso gratuito",
        "acceso libre y gratuito",
        "gratis",
        "sin cargo",
        "gratuito",
        "gratuita",
    ]
    return any(p in t for p in phrases)


def extract_price(text):
    t = strip_html(text)
    patterns = [
        r"\$\s*([\d\.,]+)",
        r"(?:entrada|valor|precio|costo)\s*[:\-]?\s*\$?\s*([\d\.,]+)",
    ]
    for pat in patterns:
        m = re.search(pat, t, re.I)
        if m:
            raw = m.group(1).replace(".", "").replace(",", ".")
            try:
                return float(raw), "ARS"
            except Exception:
                pass
    return None, ""


def wp_get(session, url, delay):
    try:
        r = session.get(url, headers=HEADERS, timeout=30)
        time.sleep(delay)
        if r.status_code == 200:
            return r.json(), 200
        return {}, r.status_code
    except Exception:
        return {}, 0


def get_rest_enrichment(session, mec_id, delay):
    obj, status = wp_get(session, REST_EVENT.format(id=mec_id), delay)
    if not obj:
        return {}, status

    content = strip_html(obj.get("content", {}).get("rendered", ""))
    title = strip_html(obj.get("title", {}).get("rendered", ""))

    categories = []
    cat_ids = obj.get("mec_category") or []
    for cid in cat_ids:
        cat_obj, _ = wp_get(
            session,
            f"{REST_CATEGORY}/{cid}?per_page=100",
            delay
        )
        name = cat_obj.get("name")
        if name:
            categories.append(clean_text(name))

    tags = []
    for tid in obj.get("tags") or []:
        tag_obj, _ = wp_get(
            session,
            f"{REST_TAGS}/{tid}?per_page=100",
            delay
        )
        name = tag_obj.get("name")
        if name:
            tags.append(clean_text(name))

    image = ""
    emb = obj.get("_embedded", {})
    media = emb.get("wp:featuredmedia") or []
    if media:
        image = (
            media[0].get("source_url")
            or media[0].get("media_details", {}).get("sizes", {}).get("full", {}).get("source_url")
            or ""
        )

    return {
        "title": title,
        "content": content,
        "image": image,
        "categories": uniq(categories),
        "tags": uniq(tags),
        "rest": obj,
    }, status


def ajax_month(session, year, month, delay):
    data = {
        "id": "mecv7",
        "action": "mec_tile_load_month",
        "mec_year": str(year),
        "mec_month": str(month),
        "atts[label]": "",
        "atts[category]": "",
        "atts[location]": "",
        "atts[organizer]": "",
        "atts[tag]": "",
        "atts[author]": "",
        "atts[skin]": "tile",
        "atts[sk-options][list][style]": "standard",
        "atts[sk-options][list][start_date_type]": "today",
        "atts[sk-options][list][start_date]": "",
        "atts[sk-options][list][end_date_type]": "date",
        "atts[sk-options][list][maximum_date_range]": "",
    }

    try:
        r = session.post(
            AJAX_URL,
            data=data,
            headers=HEADERS,
            timeout=45
        )
        time.sleep(delay)

        if r.status_code != 200:
            return None, r.status_code, r.text

        try:
            obj = r.json()
        except Exception:
            return None, r.status_code, r.text

        html = obj.get("month", "")
        return html, r.status_code, obj
    except Exception as e:
        return None, 0, str(e)


def parse_cards(html, year, month):
    soup = BeautifulSoup(html or "", "html.parser")
    cards = []

    for article in soup.select("article.mec-event-article"):
        a = article.select_one("a[href]")
        if not a:
            continue

        url = urljoin(BASE, a.get("href"))
        title_node = article.select_one(".mec-event-title a") or article.select_one(".mec-event-title")
        title = clean_text(title_node.get_text(" ", strip=True) if title_node else "")

        if not title:
            continue

        mec_id = (
            article.get("data-event-id")
            or a.get("data-event-id")
            or article.select_one("[data-event-id]")
            and article.select_one("[data-event-id]").get("data-event-id")
            or ""
        )
        mec_id = str(mec_id).strip()

        card_date, card_score = parse_card_date(article, year, month)
        card_start_time, card_end_time = extract_mec_card_time(article)

        # IMPORTANTE:
        # Si la tarjeta pertenece al mes consultado, aceptamos su día.
        # Si tiene un mes explícito distinto, no la convertimos al mes consultado.
        if card_date:
            try:
                cd = datetime.strptime(card_date, "%Y-%m-%d").date()
                # permitimos eventos que caen realmente en el mes consultado
                if cd.month != month and cd.year != year:
                    continue
            except Exception:
                pass

        cards.append({
            "mec_id": mec_id,
            "url": url,
            "title": title,
            "display_date": card_date,
            "display_time": card_start_time,
            "time_end_card": card_end_time,
            "article_text": clean_text(article.get_text(" ", strip=True)),
            "query_year": year,
            "query_month": month,
        })

    return cards


def build_occurrences(start_date, end_date, time_start="", time_end=""):
    """
    Construye una ocurrencia por día.

    IMPORTANTE V9:
    - time_start y time_end son independientes.
    - Si no existe hora de fin en la fuente, time_end queda "".
    - Nunca se usa time_start como sustituto de time_end.
    - En ese caso end_datetime también queda "".
    """
    if not start_date:
        return []

    try:
        a = datetime.strptime(start_date, "%Y-%m-%d").date()
        b = datetime.strptime(end_date or start_date, "%Y-%m-%d").date()
    except Exception:
        return []

    out = []
    cur = a
    while cur <= b:
        start_dt = make_local_datetime(cur.isoformat(), time_start)
        end_dt = make_local_datetime(cur.isoformat(), time_end) if time_end else ""

        out.append({
            "date": cur.isoformat(),
            "time_start": time_start or "",
            "time_end": time_end or "",
            "start_datetime": start_dt,
            "end_datetime": end_dt,
        })
        cur += timedelta(days=1)

    return out



def normalize_url(url):
    if not url:
        return ""
    url = html.unescape(str(url)).strip()
    url = url.replace("&amp;", "&")
    return url


def unique_clean(values):
    out = []
    seen = set()
    for v in values or []:
        v = str(v or "").strip()
        if not v:
            continue
        k = v.lower()
        if k not in seen:
            seen.add(k)
            out.append(v)
    return out


def classify_link(url, text_label="", page_text=""):
    """
    Clasifica enlaces de una página de evento.
    No considera redes sociales ni Google Calendar como inscripción.
    """
    u = normalize_url(url)
    label = re.sub(r"\s+", " ", str(text_label or "")).strip().lower()
    low = u.lower()

    if not u or low.startswith(("javascript:", "mailto:", "tel:", "#")):
        return None

    # Navegación/social/sharing del propio sitio.
    excluded_domains = (
        "facebook.com", "instagram.com", "x.com", "twitter.com",
        "pinterest.com", "telegram.me", "t.me", "whatsapp.com",
        "calendar.google.com", "cinemacenter.com.ar"
    )
    if any(d in low for d in excluded_domains):
        return None

    # Mapa
    map_terms = (
        "google.com/maps", "maps.google", "goo.gl/maps",
        "maps.app.goo.gl", "openstreetmap.org",
        "waze.com", "maps.apple.com", "bing.com/maps"
    )
    if any(t in low for t in map_terms):
        return "map"

    # Inscripción / entradas / reservas.
    registration_terms = (
        "inscrip", "registro", "registr", "reserva", "reservar",
        "entrad", "ticket", "tickets", "boleto", "cronobot",
        "eventbrite", "passline", "ticketek", "tuentrada",
        "ventas", "comprar"
    )
    if any(t in label for t in registration_terms):
        return "registration"
    if any(t in low for t in registration_terms):
        return "registration"

    # IMPORTANTE:
    # No usamos el texto global de la página para convertir un enlace
    # cualquiera en inscripción. Una noticia puede mencionar "inscripción"
    # y contener además enlaces de navegación, publicidad o servicios ajenos.
    # La inscripción sólo se reconoce por el texto/URL del propio enlace.
    return "external"


def filter_external_urls(urls):
    """Conserva sólo URLs externas útiles para el evento."""
    excluded_domains = (
        "agendatucuman.com.ar",
        "agendacontenidos.com.ar",
        "facebook.com",
        "instagram.com",
        "x.com",
        "twitter.com",
        "pinterest.com",
        "telegram.me",
        "t.me",
        "whatsapp.com",
        "calendar.google.com",
        "cinemacenter.com.ar",
    )
    out = []
    for raw in urls or []:
        u = normalize_url(raw)
        if not u or not re.match(r"^https?://", u, flags=re.I):
            continue
        low = u.lower()
        if any(d in low for d in excluded_domains):
            continue
        out.append(u)
    return unique_clean(out)


def extract_links_from_soup(soup, page_text=""):
    registration = []
    maps = []
    external = []

    if soup is None:
        return registration, maps, external

    for a in soup.find_all("a", href=True):
        href = normalize_url(a.get("href"))
        label = " ".join(a.stripped_strings)
        kind = classify_link(href, label, page_text)

        if not kind:
            continue

        if kind == "map":
            maps.append(href)
        elif kind == "registration":
            registration.append(href)
        elif kind == "external":
            # Sólo externos útiles; no navegación interna.
            if "agendatucuman.com.ar" not in href.lower():
                external.append(href)

    return unique_clean(registration), unique_clean(maps), unique_clean(external)


def extract_contacts_from_text(text_value):
    text_value = html.unescape(str(text_value or ""))

    emails = re.findall(
        r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b",
        text_value,
        flags=re.I
    )

    phones = re.findall(
        r"(?<!\d)(?:\+?54[\s\-]?)?(?:9[\s\-]?)?"
        r"(?:0?38[0-9]{1,2}|0?[0-9]{2,4})?"
        r"[\s\-()]*[0-9]{3,5}[\s\-]?[0-9]{3,5}(?!\d)",
        text_value
    )

    phones_clean = []
    for p in phones:
        p = re.sub(r"\s+", " ", p).strip(" -")
        digits = re.sub(r"\D", "", p)
        # Evita números demasiado cortos o capturas obvias de fechas.
        if 8 <= len(digits) <= 13:
            phones_clean.append(p)

    return unique_clean(emails), unique_clean(phones_clean)


def extract_organizer(text_value):
    text_value = re.sub(r"\s+", " ", html.unescape(str(text_value or ""))).strip()

    patterns = [
        r"(?:Organiza|Organizado por|Organizan|Organización|A cargo de|Convoca|Convocado por)\s*:\s*([^.;|]+)",
        r"(?:organizado por|organizada por|organiza|convoca)\s+([^.;|]+)",
    ]

    for pat in patterns:
        m = re.search(pat, text_value, flags=re.I)
        if m:
            value = clean_text(m.group(1))
            # Si la fuente usa una etiqueta explícita con dos puntos
            # (por ejemplo, "Organizan:"), el grupo ya está delimitado
            # por puntuación y NO debemos cortar en palabras como "la"
            # dentro de nombres institucionales ("de la Municipalidad").
            explicit_label = re.search(
                r"(?:Organiza|Organizado por|Organizan|Organización|A cargo de|Convoca|Convocado por)\s*:",
                text_value,
                flags=re.I,
            )
            if not explicit_label or re.match(r"(?i)^convoca\s*:", explicit_label.group(0)):
                # En textos sin etiqueta puede faltar el punto después del
                # organizador; en "Convoca:" también puede faltar el punto
                # antes de la oración siguiente.
                value = re.split(
                    r"\s+(?=(?:La|El|Los|Las|Esta|Este|Quienes|Para|Durante|Si)\s+)",
                    value,
                    maxsplit=1,
                    flags=0,
                )[0]
            value = value.strip(" ,;:-")
            if 2 <= len(value) <= 180:
                return value

    return ""


def extract_price_info(text_value):
    text_value = re.sub(r"\s+", " ", html.unescape(str(text_value or ""))).strip()

    # Precio explícito. No interpreta números sueltos como precio.
    patterns = [
        r"(?:entrada|ingreso|precio|valor|costo|coste)\s*(?:es|:)?\s*\$?\s*([0-9][0-9.,]*)",
        r"\$\s*([0-9][0-9.,]*)",
    ]

    for pat in patterns:
        m = re.search(pat, text_value, flags=re.I)
        if m:
            raw = m.group(1).replace(".", "").replace(",", ".")
            try:
                value = float(raw)
                if value >= 0:
                    return value, "ARS"
            except Exception:
                pass

    return None, ""


def extract_jsonld_event_data(jsonlds):
    """
    Extrae sólo campos estructurados útiles que puedan mejorar la fuente
    principal. No reemplaza datos MEC/editoriales.
    """
    out = {
        "location": "",
        "address": "",
        "city": "",
        "organizer": v11_organizer or "",
        "map_urls": [],
        "registration_urls": [],
        "price": None,
        "currency": "",
        "email": [],
        "phone": [],
    }

    if not jsonlds:
        return out

    for obj in jsonlds:
        if not isinstance(obj, dict):
            continue

        typ = obj.get("@type", "")
        types = typ if isinstance(typ, list) else [typ]
        if not any(str(t).lower() in ("event", "business", "organization") for t in types):
            continue

        loc = obj.get("location")
        if isinstance(loc, dict):
            name = clean_text(loc.get("name", ""))
            addr = loc.get("address")
            if name and not out["location"]:
                out["location"] = name
            if isinstance(addr, dict):
                street = clean_text(addr.get("streetAddress", ""))
                city = clean_text(addr.get("addressLocality", ""))
                if street and not out["address"]:
                    out["address"] = street
                if city and not out["city"]:
                    out["city"] = city
            elif isinstance(addr, str) and addr.strip() and not out["address"]:
                out["address"] = clean_text(addr)

            maps = obj.get("url")
            if maps and isinstance(maps, str) and any(x in maps.lower() for x in ("maps", "waze")):
                out["map_urls"].append(maps)

        org = obj.get("organizer")
        if isinstance(org, dict):
            n = clean_text(org.get("name", ""))
            if n and not out["organizer"]:
                out["organizer"] = n
        elif isinstance(org, str) and org.strip():
            out["organizer"] = clean_text(org)

        offers = obj.get("offers")
        if isinstance(offers, dict):
            price = offers.get("price")
            currency = offers.get("priceCurrency")
            if price not in (None, "", "0"):
                try:
                    out["price"] = float(str(price).replace(",", "."))
                    out["currency"] = str(currency or "")
                except Exception:
                    pass

        for key in ("email",):
            val = obj.get(key)
            if isinstance(val, str):
                out["email"].append(val)
        for key in ("telephone", "phone"):
            val = obj.get(key)
            if isinstance(val, str):
                out["phone"].append(val)

    out["map_urls"] = unique_clean(out["map_urls"])
    out["email"] = unique_clean(out["email"])
    out["phone"] = unique_clean(out["phone"])
    return out




def build_map_search_url(location, address, city):
    """
    V11: genera una búsqueda de Google Maps sólo cuando existe información
    suficiente para identificar un lugar. No inventa coordenadas ni afirma
    que la fuente original haya publicado un mapa.
    """
    location = clean_location(location or "")
    address = clean_location(address or "")
    city = clean_location(city or "")

    if not location and not address:
        return ""

    parts = []
    if location:
        parts.append(location)
    if address and address.lower() not in location.lower():
        parts.append(address)
    if city and city.lower() not in " ".join(parts).lower():
        parts.append(city)

    # Para lugares sin ciudad conocida, acotamos la búsqueda a Tucumán.
    query = ", ".join(parts)
    if "tucum" not in query.lower():
        query += ", Tucumán, Argentina"

    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(query)

def process_event(session, card, delay, query_year, query_month):
    mec_id = card["mec_id"]
    page_url = card["url"]

    page_status = 0
    rest_status = 0

    # V10.2: inicializar siempre los campos de enriquecimiento.
    # Si una extracción secundaria falla, el evento principal no debe fallar.
    v11_registration = []
    v11_maps = []
    v11_external = []
    v11_emails = []
    v11_phones = []
    v11_organizer = ""
    v11_price = ""
    v11_currency = ""
    v11_link_error = ""

    try:
        r = session.get(page_url, headers=HEADERS, timeout=40)
        time.sleep(delay)
        page_status = r.status_code
        page_soup = BeautifulSoup(r.text, "html.parser")

    # V11.1: enlaces, contactos y metadatos editoriales.
        page_text_for_links = clean_text(page_soup.get_text(" ", strip=True)) if "page_soup" in locals() and page_soup else ""
        v11_registration, v11_maps, v11_external = extract_links_from_soup(
        page_soup if "page_soup" in locals() else None,
        page_text_for_links
        )
        v11_emails, v11_phones = extract_contacts_from_text(page_text_for_links)
        v11_organizer = extract_organizer(page_text_for_links)
        v11_price, v11_currency = extract_price_info(page_text_for_links)
    except Exception as exc:
        # La extracción de metadatos V10 es complementaria.
        # Nunca debe impedir que se procese el evento.
        v11_link_error = repr(exc)
        page_soup = BeautifulSoup("", "html.parser")

    jsonlds = parse_jsonld(page_soup)
    j_event = jsonld_event(jsonlds)

    rest, rest_status = get_rest_enrichment(session, mec_id, delay)

    # REST content es la fuente editorial más rica.
    content_html = rest.get("content", "") or ""
    content_text = strip_html(content_html)

    title = rest.get("title") or card["title"]
    description_source = content_html or str(page_soup.select_one(".mec-single-event-description") or "")
    highlighted_metadata = extract_highlighted_metadata(content_text)
    # Si existe la ficha estructurada, no la repetimos dentro de
    # "Descripción completa". Los datos quedan disponibles en campos
    # estructurados y en highlighted_metadata.
    description = remove_highlighted_metadata_block(description_source, highlighted_metadata)

    # Fecha
    title_start, title_end, title_source, title_score = parse_title_dates(
        title, query_year
    )

    card_date = card.get("display_date", "")
    card_score = 0.9 if card_date else 0

    j_start_date, j_start_time = extract_jsonld_datetime(j_event, "startDate")
    j_end_date, j_end_time = extract_jsonld_datetime(j_event, "endDate")

    if title_start:
        date_start = title_start
        date_end = title_end or title_start
        date_source = title_source
        date_score = title_score
    elif card_date:
        date_start = card_date
        date_end = card_date
        date_source = "card"
        date_score = card_score
    elif j_start_date:
        date_start = j_start_date
        date_end = j_end_date or j_start_date
        date_source = "jsonld"
        date_score = 0.45
    else:
        date_start = ""
        date_end = ""
        date_source = ""
        date_score = 0

    # Hora: MEC primero.
    card_time_start = card.get("display_time") or ""
    card_time_end = card.get("time_end_card") or ""

    content_time_start, content_time_end = extract_time_range(content_text)

    if card_time_start:
        time_start = card_time_start
        time_end = card_time_end or content_time_end
        time_source = "mec_card"
        time_score = 1.0
    elif content_time_start:
        time_start = content_time_start
        time_end = content_time_end
        time_source = "content"
        time_score = 0.9
    elif j_start_time:
        time_start = j_start_time
        time_end = j_end_time
        time_source = "jsonld"
        time_score = 0.45
    else:
        time_start = ""
        time_end = ""
        time_source = ""
        time_score = 0

    # Si el contenido da un horario explícito más completo que la tarjeta,
    # conserva la hora de inicio MEC pero puede completar la hora final.
    if card_time_start and content_time_end:
        time_end = content_time_end

    # Lugar
    location = ""
    location_source = ""
    location_score = 0

    loc_obj = j_event.get("location") if isinstance(j_event, dict) else None
    if isinstance(loc_obj, dict):
        location = clean_location(loc_obj.get("name", ""))
        if location:
            location_source = "jsonld"
            location_score = 0.9

    # El bloque editorial "Datos destacados" es una fuente estructurada y,
    # cuando existe, tiene prioridad sobre JSON-LD y sobre el texto narrativo.
    highlighted_location, highlighted_address, highlighted_location_source, highlighted_address_source, highlighted_score = extract_highlighted_location(content_text)
    if highlighted_location:
        location = highlighted_location
        location_source = highlighted_location_source
        location_score = highlighted_score

    # Fallback: fichas etiquetadas del contenido fuera de "Datos destacados".
    if not location:
        labeled_location, labeled_source, labeled_score = extract_labeled_location(content_text)
        if labeled_location and (not location or labeled_score > location_score):
            location, location_source, location_score = labeled_location, labeled_source, labeled_score

    # Fallback final: construcciones narrativas ("se realizará en...").
    if not location:
        location, location_source, location_score = extract_narrative_location(content_text)

    # Dirección
    address = ""
    address_source = ""
    address_score = 0

    if isinstance(loc_obj, dict):
        addr = loc_obj.get("address")
        if isinstance(addr, dict):
            address = clean_location(addr.get("streetAddress", ""))
            if address:
                address_source = "jsonld"
                address_score = 0.9
        elif isinstance(addr, str):
            address = clean_location(addr)
            if address:
                address_source = "jsonld"
                address_score = 0.9

    # La dirección explícita del bloque "Datos destacados" tiene prioridad.
    if highlighted_address:
        address = highlighted_address
        address_source = highlighted_address_source
        address_score = highlighted_score

    # Fallback para artículos sin bloque estructurado.
    if not address:
        address, address_source, address_score = extract_address(content_text)

    # Ciudad
    city = ""
    if isinstance(loc_obj, dict):
        addr = loc_obj.get("address")
        if isinstance(addr, dict):
            city = clean_location(addr.get("addressLocality", ""))

    if not city:
        city = infer_city(content_text, location, address)

    # Precio / gratis
    price, currency = extract_price(content_text)
    is_free = explicit_free(content_text)

    # Imagen
    image = rest.get("image", "")
    if not image:
        og = page_soup.find("meta", property="og:image")
        if og:
            image = og.get("content", "")

    registration_urls, map_urls, external_urls = extract_links(page_soup, page_url)

    # Si el contenido menciona Cronobot pero el HTML no tiene enlace,
    # no inventamos URL.
    if "cronobot" in content_text.lower() and not registration_urls:
        registration_urls = []

    categories = rest.get("categories") or []
    tags = rest.get("tags") or []

    # Ocurrencias:
    # Para eventos de varios días, una ocurrencia por día.
    occurrences = build_occurrences(
        date_start, date_end, time_start, time_end
    )

    start_datetime = (
        occurrences[0]["start_datetime"] if occurrences else
        make_local_datetime(date_start, time_start)
    )

    # V9: si no existe hora de fin, no fabricamos un end_datetime.
    end_datetime = (
        occurrences[-1]["end_datetime"] if occurrences else
        (make_local_datetime(date_end, time_end) if time_end else "")
    )

    overall = round(
        min(
            1.0,
            date_score * 0.35 +
            time_score * 0.30 +
            location_score * 0.20 +
            (0.10 if image else 0) +
            (0.05 if categories else 0)
        ),
        2
    )

    # V11.1: integrar enriquecimiento en el objeto del evento antes de
    # devolverlo. No depender de locals() desde clean_final_event().
    registration_urls = unique_clean(
        list(registration_urls or []) + list(v11_registration or [])
    )
    map_urls = unique_clean(
        list(map_urls or []) + list(v11_maps or [])
    )
    external_urls = filter_external_urls(
        list(external_urls or []) + list(v11_external or [])
    )

    return {
        "id": mec_id,
        "source": "MEC",
        "title": title,
        "url": page_url,
        "date_start": date_start,
        "date_end": date_end,
        "time_start": time_start,
        "time_end": time_end,
        "start_datetime": start_datetime,
        "end_datetime": end_datetime,
        "description": description,
        "highlighted_metadata": highlighted_metadata,
        "image": image,
        "price": price,
        "currency": currency,
        "is_free": is_free,
        "location": location,
        "address": address,
        "city": city,
        "organizer": v11_organizer or "",
        "contact_email": unique_clean(v11_emails or []),
        "contact_phone": unique_clean(v11_phones or []),
        "categories": uniq(categories),
        "tags": uniq(tags),
        "map_urls": map_urls,
        "map_search_url": build_map_search_url(location, address, city),
        "registration_urls": registration_urls,
        "external_urls": external_urls,
        "occurrences": occurrences,
        "confidence": {
            "date": {"source": date_source, "score": date_score},
            "time": {"source": time_source, "score": time_score, "has_start": bool(time_start), "has_end": bool(time_end)},
            "location": {"source": location_source, "score": location_score},
            "overall": overall,
        },
        "_sources": {
            "page_status": page_status,
            "rest_status": rest_status,
            "card_date": card_date,
            "card_time": card_time_start,
            "date": date_source,
            "time": time_source,
            "location": location_source,
            "jsonld_count": len(jsonlds),
            "v11_enrichment_error": v11_link_error,
            "query_month": f"{query_year:04d}-{query_month:02d}",
        },
    }


def clean_final_event(ev):
    # Limpieza final.
    ev["location"] = clean_location(ev.get("location", ""))
    ev["address"] = clean_location(ev.get("address", ""))
    ev["city"] = clean_text(ev.get("city", ""))

    # Si no hay precio explícito, queda null.
    if ev.get("price") is None:
        ev["price"] = None

    # Gratis sólo con evidencia.
    if not ev.get("is_free"):
        ev["is_free"] = False

    # Nunca convertir Google Calendar en inscripción.
    ev["registration_urls"] = [
        u for u in uniq(ev.get("registration_urls", []))
        if "calendar.google.com" not in u.lower()
    ]

    # Ocurrencias únicas.
    seen = set()
    occ = []
    for o in ev.get("occurrences", []):
        key = (
            o.get("date"),
            o.get("time_start"),
            o.get("time_end"),
        )
        if key not in seen:
            seen.add(key)
            occ.append(o)
    ev["occurrences"] = occ


    # V11.1: los campos de enriquecimiento ya vienen integrados desde
    # process_event(). Aquí sólo normalizamos y deduplicamos.
    ev["registration_urls"] = unique_clean(ev.get("registration_urls") or [])
    ev["map_urls"] = unique_clean(ev.get("map_urls") or [])
    ev["map_search_url"] = ev.get("map_search_url") or build_map_search_url(
        ev.get("location", ""), ev.get("address", ""), ev.get("city", "")
    )
    ev["external_urls"] = unique_clean(ev.get("external_urls") or [])
    ev["contact_email"] = unique_clean(ev.get("contact_email") or [])
    ev["contact_phone"] = unique_clean(ev.get("contact_phone") or [])

    # V11.1: garantía final de que la ausencia de hora de fin se conserva.
    # Nunca convertir inicio -> fin.
    if not ev.get("time_end"):
        ev["end_datetime"] = ""
        for o in ev["occurrences"]:
            o["time_end"] = ""
            o["end_datetime"] = ""

    return ev



def parse_wp_service_date(title, content, default_year):
    """Obtiene el período de vigencia de una publicación de Servicios."""
    texts = [clean_text(title), clean_text(content)]
    for normalized in texts:
        if not normalized:
            continue

        # 7 al 11 de septiembre / 26 y 27 de agosto
        m = re.search(
            r"\b(\d{1,2})\s*(?:al|hasta|y)\s*(\d{1,2})\s+de\s+([a-záéíóúñ]+)",
            normalized, re.I
        )
        if m:
            d1, d2 = int(m.group(1)), int(m.group(2))
            mo = normalize_month_name(m.group(3))
            if mo:
                try:
                    a = date(default_year, mo, d1)
                    b = date(default_year, mo, d2)
                    return a.isoformat(), b.isoformat(), "services_range", 0.95
                except ValueError:
                    pass

        # 31 de agosto hasta el 4 de septiembre / 30 de septiembre al 2 de octubre
        m = re.search(
            r"\b(?:desde\s+)?(?:este\s+|el\s+)?(?:lunes|martes|miércoles|jueves|viernes|sábado|domingo)?\s*"
            r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+"
            r"(?:al|hasta|-)\s+(?:el\s+|este\s+)?(?:lunes|martes|miércoles|jueves|viernes|sábado|domingo)?\s*"
            r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)",
            normalized, re.I
        )
        if m:
            d1, mo1, d2, mo2 = int(m.group(1)), normalize_month_name(m.group(2)), int(m.group(3)), normalize_month_name(m.group(4))
            if mo1 and mo2:
                try:
                    y2 = default_year + (1 if mo2 < mo1 else 0)
                    return date(default_year, mo1, d1).isoformat(), date(y2, mo2, d2).isoformat(), "services_range", 0.95
                except ValueError:
                    pass

        # Reutilizamos el parser general para formatos completos.
        a, b, source, score = parse_title_dates(normalized, default_year)
        if a:
            return a, b or a, f"services_{source}", score

        # Caso: "hasta el viernes 4 de septiembre".
        m = re.search(
            r"(?:hasta|finaliza|termina|terminará)\s+(?:el\s+)?(?:lunes|martes|miércoles|jueves|viernes|sábado|domingo)?\s*"
            r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)", normalized, re.I
        )
        if m:
            d = int(m.group(1)); mo = normalize_month_name(m.group(2))
            if mo:
                try:
                    end = date(default_year, mo, d)
                    return end.isoformat(), end.isoformat(), "services_until", 0.55
                except ValueError:
                    pass
    return "", "", "", 0


def extract_services(session, delay, year, max_pages=12):
    """Extrae publicaciones de /category/servicios/ mediante la REST API.

    Se busca dinámicamente la categoría 'servicios' y luego sus posts. Cada
    publicación se normaliza al mismo esquema de agenda, con la categoría
    'Servicios', para que la app la trate igual que un evento MEC.
    """
    events = []
    errors = []
    category_url = BASE + "/wp-json/wp/v2/categories"
    posts_url = BASE + "/wp-json/wp/v2/posts"

    try:
        r = session.get(category_url, params={"slug": "servicios", "per_page": 10}, timeout=25)
        r.raise_for_status()
        cats = r.json()
        category_id = next((c.get("id") for c in cats if c.get("slug") == "servicios"), None)
        if not category_id:
            return events, [{"stage": "services_category", "error": "No se encontró la categoría servicios"}]
    except Exception as exc:
        return events, [{"stage": "services_category", "error": repr(exc)}]

    for page in range(1, max_pages + 1):
        try:
            r = session.get(
                posts_url,
                params={
                    "categories": category_id,
                    "per_page": 100,
                    "page": page,
                    "_embed": 1,
                },
                timeout=25,
            )
            if r.status_code == 400:
                break
            r.raise_for_status()
            posts = r.json()
            if not posts:
                break
        except Exception as exc:
            errors.append({"stage": "services_posts", "page": page, "error": repr(exc)})
            break

        for post in posts:
            try:
                post_id = post.get("id")
                title = clean_text((post.get("title") or {}).get("rendered", ""))
                content_html = (post.get("content") or {}).get("rendered", "") or ""
                content_text = strip_html(content_html)
                url = post.get("link") or ""

                # Para SERVICIOS, las fechas suelen aparecer sin año.
                # Usamos el año de publicación del propio artículo como
                # referencia, en lugar del año actual del workflow. Esto evita
                # convertir automáticamente notas históricas en eventos futuros.
                published_year = year
                published_at = post.get("date") or post.get("modified") or ""
                published_match = re.match(r"^(\d{4})-", str(published_at))
                if published_match:
                    published_year = int(published_match.group(1))

                date_start, date_end, date_source, date_score = parse_wp_service_date(
                    title, content_text, published_year
                )
                if not date_start:
                    # Sin fecha verificable no se publica como evento: evita
                    # llenar la agenda con notas de servicios sin vigencia.
                    continue

                soup = BeautifulSoup(content_html, "html.parser")
                image = ""
                embedded = post.get("_embedded") or {}
                media = (embedded.get("wp:featuredmedia") or [{}])[0]
                image = media.get("source_url") or ""
                if not image:
                    og = soup.find("img", src=True)
                    image = og.get("src", "") if og else ""

                location, location_source, location_score = extract_labeled_location(content_text)
                if not location:
                    location, location_source, location_score = extract_narrative_location(content_text)
                address, address_source, address_score = extract_address(content_text)
                city = infer_city(content_text, location, address)
                price, currency = extract_price(content_text)
                is_free = explicit_free(content_text)
                map_search_url = build_map_search_url(location, address, city)

                occurrences = build_occurrences(date_start, date_end, "", "")
                tags = []
                for tag in (embedded.get("wp:term") or []):
                    if isinstance(tag, list):
                        tags.extend(t.get("name", "") for t in tag if t.get("taxonomy") == "post_tag")
                tags = uniq(tags)

                events.append({
                    "id": f"servicios-{post_id}",
                    "source": "SERVICIOS",
                    "title": title,
                    "url": url,
                    "date_start": date_start,
                    "date_end": date_end,
                    "time_start": "",
                    "time_end": "",
                    "start_datetime": occurrences[0]["start_datetime"] if occurrences else make_local_datetime(date_start, ""),
                    "end_datetime": occurrences[-1]["end_datetime"] if occurrences and occurrences[-1].get("end_datetime") else "",
                    "description": content_html,
                    "image": image,
                    "price": price,
                    "currency": currency,
                    "is_free": is_free,
                    "location": location,
                    "address": address,
                    "city": city,
                    "organizer": "",
                    "contact_email": [],
                    "contact_phone": [],
                    "categories": ["Servicios"],
                    "tags": tags,
                    "map_urls": [],
                    "map_search_url": map_search_url,
                    "registration_urls": [],
                    "external_urls": [url] if url else [],
                    "occurrences": occurrences,
                    "confidence": {
                        "date": {"source": date_source, "score": date_score},
                        "time": {"source": "none", "score": 0, "has_start": False, "has_end": False},
                        "location": {"source": location_source, "score": location_score},
                        "overall": round(min(1.0, date_score * 0.55 + location_score * 0.25 + (0.10 if image else 0) + 0.10), 2),
                    },
                    "_sources": {
                        "source_url": BASE + "/category/servicios/",
                        "post_id": post_id,
                        "date": date_source,
                    },
                })
            except Exception as exc:
                errors.append({"stage": "services_event", "post_id": post.get("id"), "error": repr(exc)})

        if len(posts) < 100:
            break
        time.sleep(delay)

    # Deduplicar por URL/ID.
    dedup = OrderedDict()
    for e in events:
        dedup[e["id"]] = e
    return list(dedup.values()), errors

def main():
    args = parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "ajax_raw").mkdir(exist_ok=True)
    (out / "eventos_html_raw").mkdir(exist_ok=True)

    session = requests.Session()
    session.headers.update(HEADERS)

    months = month_sequence(args.start_year, args.start_month, args.months)
    if args.lookback_months:
        # Incluye meses anteriores para no perder eventos que ya comenzaron
        # pero todavía siguen vigentes.
        first = date(args.start_year, args.start_month, 1)
        lookback_start = first
        for _ in range(args.lookback_months):
            lookback_start = (lookback_start.replace(day=1) - timedelta(days=1)).replace(day=1)
        lookback = month_sequence(lookback_start.year, lookback_start.month, args.lookback_months)
        months = lookback + months

    all_cards = []
    ajax_report = []
    errors = []

    # ---------------------------------------------------------
    # 1. MEC AJAX
    # ---------------------------------------------------------
    for year, month in months:
        html_or_none, status, raw = ajax_month(
            session, year, month, args.delay
        )

        raw_path = out / "ajax_raw" / f"{year:04d}-{month:02d}.json"
        if isinstance(raw, dict):
            raw_path.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            html = raw.get("month", "")
        else:
            raw_path.write_text(
                str(raw),
                encoding="utf-8"
            )
            html = ""

        cards = parse_cards(html, year, month) if html else []
        all_cards.extend(cards)

        ajax_report.append({
            "year": year,
            "month": month,
            "status": status,
            "cards": len(cards),
            "bytes": len(html.encode("utf-8")) if html else 0,
            "json": isinstance(raw, dict),
        })

        if status != 200:
            errors.append({
                "stage": "ajax",
                "year": year,
                "month": month,
                "status": status,
            })

    # ---------------------------------------------------------
    # 2. Deduplicar tarjetas por MEC ID
    # ---------------------------------------------------------
    unique_cards = OrderedDict()
    for card in all_cards:
        mid = card.get("mec_id")
        if not mid:
            continue

        # Si hay varias tarjetas del mismo evento, conservar:
        # - fecha de la primera aparición
        # - mejor hora disponible
        if mid not in unique_cards:
            unique_cards[mid] = card
        else:
            old = unique_cards[mid]
            if not old.get("display_time") and card.get("display_time"):
                old["display_time"] = card["display_time"]
            if not old.get("display_date") and card.get("display_date"):
                old["display_date"] = card["display_date"]

    # ---------------------------------------------------------
    # 3. Procesar páginas
    # ---------------------------------------------------------
    events = []
    page_report = []

    for idx, card in enumerate(unique_cards.values(), 1):
        try:
            ev = process_event(
                session,
                card,
                args.delay,
                args.start_year,
                args.start_month,
            )
            ev = clean_final_event(ev)
            events.append(ev)

            page_report.append({
                "id": card["mec_id"],
                "url": card["url"],
                "date_start": ev["date_start"],
                "status": ev["_sources"]["page_status"],
                "rest_status": ev["_sources"]["rest_status"],
                "jsonld_count": ev["_sources"]["jsonld_count"],
            })

            print(
                f"[{idx}/{len(unique_cards)}] "
                f"{card['mec_id']} | {ev['date_start']} | {ev['title']}"
            )

        except Exception as e:
            errors.append({
                "stage": "event",
                "id": card.get("mec_id"),
                "url": card.get("url"),
                "error": repr(e),
            })

    # ---------------------------------------------------------
    # 3b. SERVICIOS (WordPress category)
    # ---------------------------------------------------------
    service_events, service_errors = extract_services(
        session, args.delay, args.start_year
    )
    events.extend(service_events)
    errors.extend(service_errors)

    # La agenda publicada representa actualidad, no un archivo histórico.
    # Eliminamos eventos cuyo período ya terminó. Se conserva un evento que
    # termina hoy porque sigue siendo relevante durante el día.
    today_iso = datetime.now(ARGENTINA_TZ).date().isoformat()
    before_filter = len(events)
    events = [
        event for event in events
        if (event.get("date_end") or event.get("date_start") or "") >= today_iso
    ]
    removed_past = before_filter - len(events)
    if removed_past:
        print(f"[Filtro vigencia] Eliminados {removed_past} eventos vencidos antes de publicar.")

    events.sort(
        key=lambda x: (
            x.get("date_start") or "9999-99-99",
            x.get("time_start") or "99:99",
            x.get("title") or "",
        )
    )

    # ---------------------------------------------------------
    # 4. Cobertura
    # ---------------------------------------------------------
    fields = [
        "id", "title", "url", "date_start", "date_end",
        "time_start", "time_end", "description", "image",
        "price", "currency", "is_free", "location", "address",
        "city", "organizer", "categories", "tags", "map_urls",
        "map_search_url", "registration_urls", "occurrences",
    ]

    coverage = {}
    total = len(events)
    for field in fields:
        count = 0
        for e in events:
            value = e.get(field)
            if isinstance(value, list):
                ok = len(value) > 0
            else:
                ok = value not in ("", None)
            if ok:
                count += 1
        coverage[field] = {
            "count": count,
            "total": total,
            "percent": round((count / total * 100) if total else 0, 1),
        }

    # ---------------------------------------------------------
    # 5. Guardar JSON
    # ---------------------------------------------------------
    (out / "agenda_eventos.json").write_text(
        json.dumps(events, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # CSV compacto
    csv_fields = [
        "id", "title", "url", "date_start", "date_end",
        "time_start", "time_end", "start_datetime", "end_datetime",
        "location", "address", "city", "price", "currency",
        "is_free", "categories", "tags", "registration_urls",
        "map_urls", "map_search_url", "image"
    ]

    with open(out / "agenda_eventos.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=csv_fields)
        w.writeheader()
        for e in events:
            row = dict(e)
            for k in ("categories", "tags", "registration_urls", "map_urls"):
                row[k] = " | ".join(row.get(k) or [])
            w.writerow({k: row.get(k, "") for k in csv_fields})

    (out / "cobertura_campos.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    (out / "ajax_report.json").write_text(
        json.dumps(ajax_report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    (out / "page_report.json").write_text(
        json.dumps(page_report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    (out / "errores.json").write_text(
        json.dumps(errors, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # cards finales
    (out / "cards_mec.json").write_text(
        json.dumps(list(unique_cards.values()), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # ---------------------------------------------------------
    # 6. Informe
    # ---------------------------------------------------------
    lines = [
        "AGENDA TUCUMÁN - EXTRACCIÓN MEC V11.2",
        "=" * 78,
        f"Generado: {datetime.now(ARGENTINA_TZ).isoformat()}",
        f"Fuente: {EVENTOS_URL}",
        f"Meses consultados: {args.months}",
        f"Tarjetas MEC encontradas: {len(all_cards)}",
        f"Eventos únicos: {len(events)}",
        f"Eventos MEC: {sum(1 for e in events if e.get('source') == 'MEC')}",
        f"Servicios: {sum(1 for e in events if e.get('source') == 'SERVICIOS')}",
        f"Errores: {len(errors)}",
        "",
        "CRITERIOS V11.2",
        "-" * 78,
        "• MEC es la fuente primaria de fecha/hora visibles.",
        "• La hora de la tarjeta MEC tiene prioridad sobre JSON-LD.",
        "• El contenido editorial completa el horario cuando aporta información adicional.",
        "• Las fechas explícitas del título tienen prioridad.",
        "• Los eventos de varios días generan una ocurrencia por día.",
        "• Las tarjetas repetidas entre meses se deduplican por MEC ID.",
        "• Datetimes se construyen directamente en hora local -03:00.",
        "• Google Calendar y redes sociales no se consideran inscripción.",
        "• Las publicaciones de /category/servicios/ se normalizan como eventos con categoría Servicios.",
        "• El bloque editorial 'Datos destacados' tiene prioridad para Lugar/Dirección cuando está presente.",
        "• 'Dirección' se valida para evitar confundir al director artístico con una dirección física.",
        "• Sin 'Datos destacados', se conservan los extractores narrativos y de etiquetas anteriores.",
        "• Servicios sin fecha verificable no se publican como eventos.",
        "• El precio sólo se registra con evidencia textual explícita.",
        "• Gratis sólo con evidencia textual explícita.",
        "",
        "EVENTOS",
        "-" * 78,
    ]

    for e in events:
        lines.append(
            f"{e['id']} | {e['date_start']} -> {e['date_end']} | "
            f"{e['time_start']} -> {e['time_end']} | {e['title']}"
        )
        lines.append(
            f"  Lugar: {e['location']} | Dirección: {e['address']} | "
            f"Ciudad: {e['city']}"
        )
        lines.append(
            f"  Categorías: {', '.join(e['categories'])} | "
            f"Gratis: {e['is_free']} | "
            f"Ocurrencias: {len(e['occurrences'])} | "
            f"Confianza: {e['confidence']['overall']}"
        )

    (out / "informe.txt").write_text(
        "\n".join(lines),
        encoding="utf-8"
    )

    print()
    print("=" * 78)
    print("EXTRACCIÓN V11.2 FINALIZADA")
    print("=" * 78)
    print(f"Tarjetas MEC: {len(all_cards)}")
    print(f"Eventos únicos: {len(events)}")
    print(f"Errores: {len(errors)}")
    print(f"Salida: {out.resolve()}")
    print()
    print("Cobertura:")
    for k, v in coverage.items():
        print(f"  {k:20} {v['count']:4}/{v['total']:<4} {v['percent']:6.1f}%")


if __name__ == "__main__":
    main()
