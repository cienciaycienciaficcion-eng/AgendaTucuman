#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extractor de Servicios de Agenda Tucumán.

Usa primero la API REST de WordPress para evitar cientos de peticiones HTML
y reducir el riesgo de HTTP 429. Si la API REST no está disponible, utiliza
el extractor HTML como respaldo con reintentos y espera progresiva.

Salida:
    datos/servicios_raw.json
"""

import json
import re
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://agendatucuman.com.ar"
CATEGORY = f"{BASE}/category/servicios/"
REST = f"{BASE}/wp-json/wp/v2"
OUT = Path("datos/servicios_raw.json")

HEADERS = {
    "User-Agent": (
        "AgendaTucuman/servicios-extractor/2.0 "
        "(+https://agendatucuman.com.ar/)"
    ),
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
}

TIMEOUT = 30
MAX_RETRIES = 6
REST_PER_PAGE = 100
MAX_PAGES = 1
REQUEST_DELAY = 0.8


def clean(text: str) -> str:
    text = unescape(text or "")
    return re.sub(r"\s+", " ", text).strip()


def iso_date(value: str) -> str:
    m = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", value or "")
    if not m:
        return ""
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def request_with_retry(session, url, *, params=None, expected_json=False):
    """GET robusto frente a 429/5xx con backoff."""
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(
                url,
                params=params,
                timeout=TIMEOUT,
            )

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "")
                try:
                    wait = float(retry_after)
                except (TypeError, ValueError):
                    wait = min(60, 3 * (2 ** (attempt - 1)))

                print(
                    f"HTTP 429 en {url}. "
                    f"Esperando {wait:.1f}s "
                    f"(intento {attempt}/{MAX_RETRIES})"
                )
                time.sleep(wait)
                continue

            if response.status_code in (500, 502, 503, 504):
                wait = min(60, 2 * (2 ** (attempt - 1)))
                print(
                    f"HTTP {response.status_code} en {url}. "
                    f"Esperando {wait:.1f}s "
                    f"(intento {attempt}/{MAX_RETRIES})"
                )
                time.sleep(wait)
                continue

            response.raise_for_status()

            if expected_json:
                return response.json()

            return response.text

        except requests.RequestException as exc:
            last_error = exc
            if attempt >= MAX_RETRIES:
                break

            wait = min(60, 2 * (2 ** (attempt - 1)))
            print(
                f"Error de red en {url}: {exc}. "
                f"Reintentando en {wait:.1f}s "
                f"(intento {attempt}/{MAX_RETRIES})"
            )
            time.sleep(wait)

    if last_error:
        raise last_error

    raise RuntimeError(f"No se pudo obtener {url}")


def taxonomy_names(post, taxonomy_key, embedded_terms):
    result = []

    # Primero usamos los términos embebidos por REST.
    for group in embedded_terms:
        for term in group:
            if not isinstance(term, dict):
                continue
            if term.get("taxonomy") != taxonomy_key:
                continue
            name = clean(term.get("name", ""))
            if name and name not in result:
                result.append(name)

    return result


def find_service_category_id(session):
    """Busca la categoría 'servicios' en WordPress."""
    candidates = request_with_retry(
        session,
        f"{REST}/categories",
        params={
            "slug": "servicios",
            "per_page": 10,
        },
        expected_json=True,
    )

    for category in candidates:
        if str(category.get("slug", "")).lower() == "servicios":
            return int(category["id"])

    # Fallback por nombre.
    candidates = request_with_retry(
        session,
        f"{REST}/categories",
        params={
            "search": "servicios",
            "per_page": 20,
        },
        expected_json=True,
    )

    for category in candidates:
        if clean(category.get("name", "")).lower() == "servicios":
            return int(category["id"])

    return None


def parse_rest_post(post):
    embedded = post.get("_embedded", {})
    terms = embedded.get("wp:term", [])

    categories = taxonomy_names(post, "category", terms)
    tags = taxonomy_names(post, "post_tag", terms)

    featured = ""
    media = embedded.get("wp:featuredmedia", [])
    if media:
        featured = (
            media[0].get("source_url", "")
            or media[0].get("guid", {}).get("rendered", "")
        )

    title = clean(post.get("title", {}).get("rendered", ""))
    content_html = post.get("content", {}).get("rendered", "")
    excerpt_html = post.get("excerpt", {}).get("rendered", "")

    soup = BeautifulSoup(content_html, "html.parser")
    content = clean(soup.get_text(" ", strip=True))

    excerpt_soup = BeautifulSoup(excerpt_html, "html.parser")
    description = clean(excerpt_soup.get_text(" ", strip=True))

    if not description:
        description = content[:1000]

    pub = iso_date(post.get("date", ""))
    modified = post.get("modified", "")

    links = []
    for a in soup.select("a[href]"):
        href = urljoin(post.get("link", BASE), a.get("href", ""))
        if href.startswith("http") and href not in links:
            links.append(href)

    url = post.get("link", "")
    slug = post.get("slug", "")

    return {
        "id": (
            re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")
            or re.sub(r"[^a-z0-9]+", "-", url.rstrip("/").split("/")[-1].lower()).strip("-")
            or url
        ),
        "source": "Agenda Tucumán",
        "url": url,
        "title": title,
        "published": pub,
        "modified": modified,
        "description": description,
        "content": content,
        "image": featured,
        "author": "",
        "categories": categories,
        "tags": tags,
        "links": links,
    }


def extract_rest(session):
    """Extrae únicamente la primera página más recientes de Servicios."""
    category_id = find_service_category_id(session)
    if not category_id:
        print("No se encontró la categoría REST 'servicios'.")
        return None

    print(f"Categoría REST servicios: ID {category_id}")

    posts = []
    page = 1

    while page <= MAX_PAGES:
        print(f"REST página {page}...")

        batch = request_with_retry(
            session,
            f"{REST}/posts",
            params={
                "categories": category_id,
                "per_page": REST_PER_PAGE,
                "page": page,
                "orderby": "date",
                "order": "desc",
                "_embed": "1",
            },
            expected_json=True,
        )

        if not batch:
            break

        posts.extend(batch)
        print(f"  artículos: {len(batch)} | acumulados: {len(posts)}")

        if len(batch) < REST_PER_PAGE:
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    if not posts:
        print("REST no devolvió artículos.")
        return []

    # Deduplicación por URL/ID.
    unique = {}
    for post in posts:
        parsed = parse_rest_post(post)
        if parsed["url"]:
            unique[parsed["url"]] = parsed

    return list(unique.values())


def article_links(html):
    soup = BeautifulSoup(html, "html.parser")
    links = []
    seen = set()

    for a in soup.select("a[href]"):
        href = urljoin(BASE, a.get("href", "")).split("#", 1)[0]
        text = clean(a.get_text(" ", strip=True))

        if "/eventos/" in href or "/category/" in href or "/author/" in href:
            continue

        if (
            href.startswith(BASE)
            and href.rstrip("/") != CATEGORY.rstrip("/")
            and text
            and href not in seen
            and re.search(r"/(?:20\d{2}/)?[a-z0-9-]+/$", href, re.I)
        ):
            seen.add(href)
            links.append(href)

    return links


def parse_listing(html):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen = set()

    for article in soup.select("article, .post, .nv-blog-post, .blog-entry"):
        a = article.select_one(
            "h2 a[href], h3 a[href], h4 a[href], a[href]"
        )
        if not a:
            continue

        url = urljoin(BASE, a.get("href", "")).split("#", 1)[0]
        if url in seen or "/category/" in url or "/author/" in url:
            continue

        title = clean(a.get_text(" ", strip=True))
        if not title:
            continue

        seen.add(url)

        time_el = article.select_one("time[datetime], .entry-date, .posted-on")
        date = iso_date(time_el.get("datetime", "") if time_el else "")
        if not date and time_el:
            date = iso_date(time_el.get_text(" ", strip=True))

        excerpt_el = article.select_one(".entry-summary, .entry-content, p")
        excerpt = clean(
            excerpt_el.get_text(" ", strip=True) if excerpt_el else ""
        )

        img = article.select_one("img[src], img[data-src]")
        image = (
            urljoin(BASE, img.get("data-src") or img.get("src"))
            if img
            else ""
        )

        items.append(
            {
                "url": url,
                "title": title,
                "published": date,
                "excerpt": excerpt,
                "image": image,
            }
        )

    if not items:
        for url in article_links(html):
            items.append(
                {
                    "url": url,
                    "title": "",
                    "published": "",
                    "excerpt": "",
                    "image": "",
                }
            )

    return items


def parse_article(session, item):
    html = request_with_retry(session, item["url"])
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("main, article, .entry-content") or soup

    title_el = soup.select_one("h1") or soup.select_one("title")
    title = clean(title_el.get_text(" ", strip=True) if title_el else "")

    if " - Agenda Tucumán" in title:
        title = title.split(" - Agenda Tucumán", 1)[0].strip()

    meta_desc = soup.select_one('meta[name="description"]')
    description = clean(
        meta_desc.get("content", "") if meta_desc else ""
    )

    paragraphs = [
        clean(p.get_text(" ", strip=True))
        for p in main.select("p")
    ]
    content = " ".join(p for p in paragraphs if p)

    if not description:
        description = content[:1000]

    pub = item.get("published") or ""
    meta_date = soup.select_one('meta[property="article:published_time"]')
    if not pub and meta_date:
        pub = iso_date(meta_date.get("content", ""))

    modified = ""
    mod = soup.select_one('meta[property="article:modified_time"]')
    if mod:
        modified = mod.get("content", "")

    img = soup.select_one('meta[property="og:image"]')
    image = img.get("content", "") if img else item.get("image", "")

    author = ""
    author_meta = soup.select_one('meta[name="author"]')
    if author_meta:
        author = clean(author_meta.get("content", ""))

    tags = [
        clean(x.get_text(" ", strip=True))
        for x in soup.select(".tags-links a, a[rel='tag']")
    ]
    categories = [
        clean(x.get_text(" ", strip=True))
        for x in soup.select(".cat-links a, .category a")
    ]

    links = []
    for a in main.select("a[href]"):
        href = urljoin(item["url"], a.get("href", ""))
        if href.startswith("http") and href not in links:
            links.append(href)

    return {
        "id": re.sub(
            r"[^a-z0-9]+",
            "-",
            item["url"].rstrip("/").split("/")[-1].lower(),
        ).strip("-") or item["url"],
        "source": "Agenda Tucumán",
        "url": item["url"],
        "title": title or item["title"],
        "published": pub,
        "modified": modified,
        "description": description,
        "content": content,
        "image": image,
        "author": author,
        "categories": categories,
        "tags": tags,
        "links": links,
    }


def extract_html_fallback(session):
    """Respaldo HTML limitado a la primera página más recientes."""
    all_items = {}
    page = 1

    while True:
        url = CATEGORY if page == 1 else f"{CATEGORY}page/{page}/"
        print(f"HTML página {page}: {url}")

        html = request_with_retry(session, url)
        listing = parse_listing(html)

        if not listing:
            print("No hay más artículos.")
            break

        before = len(all_items)

        for item in listing:
            all_items[item["url"]] = item

        print(
            f"  artículos: {len(listing)} | "
            f"acumulados: {len(all_items)}"
        )

        if len(all_items) == before:
            break

        page += 1

        if page > MAX_PAGES:
            break

        # Mucho más conservador que el extractor anterior.
        time.sleep(REQUEST_DELAY)

    articles = []

    for i, item in enumerate(all_items.values(), 1):
        try:
            articles.append(parse_article(session, item))
            print(f"Artículo {i}/{len(all_items)} OK")
        except Exception as exc:
            print(
                f"Artículo {i}/{len(all_items)} ERROR: "
                f"{item['url']} -> {exc}"
            )
            articles.append(
                {
                    **item,
                    "id": re.sub(
                        r"[^a-z0-9]+",
                        "-",
                        item["url"]
                        .rstrip("/")
                        .split("/")[-1]
                        .lower(),
                    ).strip("-"),
                }
            )

    return articles


def write_output(articles):
    OUT.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "schema_version": "2.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": CATEGORY,
        "count": len(articles),
        "articles": articles,
    }

    OUT.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Generado {OUT}: {len(articles)} artículos")


def main():
    session = requests.Session()
    session.headers.update(HEADERS)

    print("=== Extractor Servicios Agenda Tucumán ===")
    print("Método preferido: WordPress REST API")
    print("Objetivo: revisar solo la primera página más recientes y evitar HTTP 429")

    try:
        articles = extract_rest(session)

        if articles is not None:
            write_output(articles)
            return

        print("REST no disponible. Activando respaldo HTML.")
        articles = extract_html_fallback(session)
        write_output(articles)

    except Exception as exc:
        print(f"ERROR FATAL DEL EXTRACTOR: {exc}")
        print(
            "No se reemplaza servicios_raw.json para conservar "
            "el último resultado válido."
        )
        raise


if __name__ == "__main__":
    main()
