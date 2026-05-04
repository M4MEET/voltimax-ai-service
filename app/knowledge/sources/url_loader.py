from __future__ import annotations

from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


async def crawl_url(
    base_url: str, max_depth: int = 2, max_pages: int = 100
) -> list[dict]:
    """Crawl a URL and extract text content from pages."""
    visited: set[str] = set()
    pages: list[dict] = []

    async def _crawl(url: str, depth: int) -> None:
        if depth > max_depth or len(pages) >= max_pages or url in visited:
            return

        visited.add(url)
        parsed = urlparse(url)
        base_domain = urlparse(base_url).netloc

        if parsed.netloc != base_domain:
            return

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url, follow_redirects=True)
                if response.status_code != 200:
                    return
                if "text/html" not in response.headers.get("content-type", ""):
                    return

                soup = BeautifulSoup(response.text, "html.parser")

                # Remove script, style, and navigation elements
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()

                text = soup.get_text(separator="\n", strip=True)
                title = soup.title.string if soup.title else url

                if text.strip():
                    pages.append({
                        "url": url,
                        "title": title,
                        "text": text,
                    })

                # Find links to crawl recursively
                if depth < max_depth:
                    for link in soup.find_all("a", href=True):
                        next_url = urljoin(url, link["href"])
                        next_url = next_url.split("#")[0].split("?")[0]
                        if next_url not in visited:
                            await _crawl(next_url, depth + 1)

        except Exception:
            pass

    await _crawl(base_url, 0)
    return pages
