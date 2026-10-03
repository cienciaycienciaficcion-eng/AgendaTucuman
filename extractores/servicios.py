#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extractor determinista de la categoría Servicios de Agenda Tucumán.

Descarga TODAS las páginas disponibles de /category/servicios/ y cada artículo,
normalizando título, fechas de publicación, contenido, imagen, categorías,
etiquetas, autor y URL. No usa IA.

Salida: datos/servicios_raw.json
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
OUT = Path("datos/servicios_raw.json")
HEADERS = {"User-Agent": "AgendaTucuman/servicios-extractor (+https://agendatucuman.com.ar/)"}
TIMEOUT = 25


def clean(text: str) -> str:
    text = unescape(text or "")
    return re.sub(r"\s+", " ", text).strip()


def iso_date(value: str) -> str:
    m = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", value or "")
    if not m:
        return ""
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def fetch(session, url):
    r = session.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def article_links(html):
    soup = BeautifulSoup(html, "html.parser")
    links = []
    seen = set()
    for a in soup.select("a[href]"):
        href = urljoin(BASE, a.get("href", "")).split("#", 1)[0]
        text = clean(a.get_text(" ", strip=True))
        if "/eventos/" in href or "/category/" in href or "/author/" in href:
            continue
        if href.startswith(BASE) and href.rstrip("/") != CATEGORY.rstrip("/") and text and href not in seen:
            # Solo enlaces que parecen artículos de WordPress.
            if re.search(r"/(?:20\d{2}/)?[a-z0-9-]+/$", href, re.I):
                seen.add(href)
                links.append(href)
    return links


def parse_listing(html):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen = set()
    for article in soup.select("article, .post, .nv-blog-post, .blog-entry"):
        a = article.select_one("h2 a[href], h3 a[href], h4 a[href], a[href]")
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
        excerpt = clean(excerpt_el.get_text(" ", strip=True) if excerpt_el else "")
        img = article.select_one("img[src], img[data-src]")
        image = urljoin(BASE, img.get("data-src") or img.get("src")) if img else ""
        items.append({"url": url, "title": title, "published": date, "excerpt": excerpt, "image": image})
    # Fallback if the theme structure changes.
    if not items:
        for url in article_links(html):
            items.append({"url": url, "title": "", "published": "", "excerpt": "", "image": ""})
    return items


def parse_article(session, item):
    html = fetch(session, item["url"])
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("main, article, .entry-content") or soup
    title = clean((soup.select_one("h1") or soup.select_one("title")).get_text(" ", strip=True))
    # El título de <title> suele incluir el nombre del sitio; priorizar h1.
    if " - Agenda Tucumán" in title:
        title = title.split(" - Agenda Tucumán", 1)[0].strip()

    meta_desc = soup.select_one('meta[name="description"]')
    description = clean(meta_desc.get("content", "") if meta_desc else "")
    paragraphs = [clean(p.get_text(" ", strip=True)) for p in main.select("p")]
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

    tags = [clean(x.get_text(" ", strip=True)) for x in soup.select('.tags-links a, a[rel="tag"]')]
    categories = [clean(x.get_text(" ", strip=True)) for x in soup.select('.cat-links a, .category a')]

    links = []
    for a in main.select("a[href]"):
        href = urljoin(item["url"], a.get("href", ""))
        if href.startswith("http") and href not in links:
            links.append(href)

    return {
        "id": re.sub(r"[^a-z0-9]+", "-", item["url"].rstrip("/").split("/")[-1].lower()).strip("-") or item["url"],
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


def main():
    session = requests.Session()
    session.headers.update(HEADERS)
    all_items = {}
    page = 1
    while True:
        url = CATEGORY if page == 1 else f"{CATEGORY}page/{page}/"
        print(f"Página {page}: {url}")
        html = fetch(session, url)
        listing = parse_listing(html)
        if not listing:
            print("No hay más artículos.")
            break
        before = len(all_items)
        for item in listing:
            all_items[item["url"]] = item
        print(f"  artículos: {len(listing)} | acumulados: {len(all_items)}")
        if len(all_items) == before:
            break
        page += 1
        if page > 200:
            break
        time.sleep(0.15)

    articles = []
    for i, item in enumerate(all_items.values(), 1):
        try:
            articles.append(parse_article(session, item))
            print(f"Artículo {i}/{len(all_items)} OK")
        except Exception as exc:
            print(f"Artículo {i}/{len(all_items)} ERROR: {item['url']} -> {exc}")
            # No perder el artículo si la página individual falla.
            articles.append({**item, "id": re.sub(r"[^a-z0-9]+", "-", item["url"].rstrip("/").split("/")[-1].lower()).strip("-")})

    output = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": CATEGORY,
        "count": len(articles),
        "articles": articles,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generado {OUT}: {len(articles)} artículos")


if __name__ == "__main__":
    main()
