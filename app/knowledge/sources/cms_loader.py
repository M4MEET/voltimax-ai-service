from __future__ import annotations

from app.shopware.client import get_shopware_client


async def load_cms_content(sales_channel_id: str | None = None) -> list[dict]:
    """Load CMS content from Server A for knowledge base indexing."""
    client = get_shopware_client()
    content: list[dict] = []

    pages = await client.get_cms_pages(sales_channel_id)
    for page in pages:
        if page.get("content"):
            content.append({
                "id": page["id"],
                "title": page.get("name", ""),
                "text": page["content"],
                "type": "cms_page",
            })

    categories = await client.get_cms_categories(sales_channel_id)
    for cat in categories:
        if cat.get("description"):
            content.append({
                "id": cat["id"],
                "title": cat.get("name", ""),
                "text": cat["description"],
                "type": "category",
            })

    products = await client.get_cms_products(sales_channel_id)
    for prod in products:
        if prod.get("description"):
            content.append({
                "id": prod["id"],
                "title": prod.get("name", ""),
                "text": f"{prod.get('name', '')}\n{prod['description']}",
                "type": "product",
            })

    return content
