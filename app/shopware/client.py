from __future__ import annotations

from typing import Any

import httpx

from app.config import get_config


class ShopwareClient:
    """HTTP client for calling Server A (Shopware plugin) REST API."""

    def __init__(self):
        config = get_config()
        self.base_url = config.shopware.server_a_url.rstrip("/")
        self.api_key = config.shopware.api_key
        self.timeout = config.shopware.timeout
        self._client: httpx.AsyncClient | None = None
        self._store_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            config = get_config()
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"X-Voltimax-Api-Key": self.api_key},
                timeout=self.timeout,
                verify=config.shopware.verify_ssl,
            )
        return self._client

    async def _get_store_client(self) -> httpx.AsyncClient:
        """Lazy-init Store API client. Read-only — never used for cart/checkout/account writes."""
        if self._store_client is None or self._store_client.is_closed:
            config = get_config()
            self._store_client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"sw-access-key": config.shopware.store_api_key},
                timeout=self.timeout,
                verify=config.shopware.verify_ssl,
            )
        return self._store_client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        if self._store_client and not self._store_client.is_closed:
            await self._store_client.aclose()

    async def _get(self, path: str, params: dict | None = None) -> dict | list | None:
        client = await self._get_client()
        try:
            response = await client.get(path, params=params)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Server A returned {e.response.status_code}", "detail": str(e)}
        except httpx.RequestError as e:
            return {"error": "Failed to connect to Server A", "detail": str(e)}

    # ---- OAuth2 (Shopware Admin API) ----

    async def get_oauth_token(self) -> str | None:
        """Get a short-lived OAuth2 bearer token using the Integration credentials.

        Use this to call the Shopware Admin API directly (/api/...) when the
        Voltimax plugin endpoints don't cover what you need.

        Token lifetime: ~10 minutes. Cache and reuse rather than requesting one per call.
        """
        config = get_config()
        if not config.shopware.integration_secret:
            return None
        client = await self._get_client()
        try:
            response = await client.post(
                "/api/oauth/token",
                json={
                    "grant_type": "client_credentials",
                    "client_id": config.shopware.api_key,
                    "client_secret": config.shopware.integration_secret,
                },
            )
            response.raise_for_status()
            return response.json().get("access_token")
        except httpx.RequestError as e:
            return None
        except httpx.HTTPStatusError:
            return None

    async def admin_get(self, path: str, params: dict | None = None) -> dict | list | None:
        """Make an authenticated GET request to the Shopware Admin API (/api/...).

        Fetches a fresh OAuth2 token on each call. For high-frequency use,
        add token caching with expiry tracking.
        """
        token = await self.get_oauth_token()
        if not token:
            return {"error": "OAuth2 token unavailable — check integration_secret in config"}
        client = await self._get_client()
        try:
            response = await client.get(
                path,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Admin API returned {e.response.status_code}"}
        except httpx.RequestError as e:
            return {"error": "Failed to connect to Admin API", "detail": str(e)}

    async def get_order_documents(self, order_number: str) -> list:
        """Fetch invoices/documents for an order via Admin API."""
        token = await self.get_oauth_token()
        if not token:
            return []
        client = await self._get_client()
        try:
            # Step 1: Get order ID from order number
            resp = await client.post(
                "/api/search/order",
                json={"limit": 1, "filter": [{"type": "equals", "field": "orderNumber", "value": order_number}]},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            order_data = resp.json()
            if not order_data.get("data"):
                return []
            order_id = order_data["data"][0]["id"]

            # Step 2: Get documents by orderId
            resp2 = await client.post(
                "/api/search/document",
                json={
                    "limit": 20,
                    "filter": [{"type": "equals", "field": "orderId", "value": order_id}],
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            resp2.raise_for_status()
            data = resp2.json()

            cfg = get_config()
            base_url = cfg.shopware.server_a_url.rstrip("/")

            docs = []
            for d in data.get("data", []):
                attrs = d.get("attributes", {})
                deep_link = attrs.get("deepLinkCode", "")
                doc_config = attrs.get("config", {})
                doc_number = doc_config.get("documentNumber", "")

                # Determine document type from number prefix
                doc_type = "Document"
                if doc_number.startswith("RE"):
                    doc_type = "Invoice (Rechnung)"
                elif doc_number.startswith("LS"):
                    doc_type = "Delivery Note (Lieferschein)"
                elif doc_number.startswith("ST"):
                    doc_type = "Cancellation (Storno)"
                elif doc_number.startswith("GS"):
                    doc_type = "Credit Note (Gutschrift)"

                doc_id = d.get("id", "")
                # Proxy through Server B so customer doesn't need Shopware login
                server_b = f"http://localhost:{cfg.server.port}"
                download_url = f"{server_b}/chat/document/{doc_id}/{deep_link}" if deep_link and doc_id else ""

                if doc_number:  # Skip documents without a number
                    docs.append({
                        "name": doc_number,
                        "type": doc_type,
                        "url": download_url,
                        "date": str(attrs.get("createdAt", ""))[:10],
                    })
            return docs
        except Exception:
            return []

    # ---- Media Documents ----

    async def get_media_documents(self, keywords: list[str] | None = None, limit: int = 50) -> list[dict]:
        """Fetch PDF documents from Shopware media library via Admin API."""
        try:
            config = get_config()
            async with httpx.AsyncClient(timeout=30, verify=config.shopware.verify_ssl) as admin:
                auth_r = await admin.post(
                    f"{self.base_url}/api/oauth/token",
                    json={
                        "grant_type": "client_credentials",
                        "client_id": config.shopware.api_key,
                        "client_secret": config.shopware.integration_secret,
                    },
                )
                if auth_r.status_code != 200:
                    return []
                token = auth_r.json().get("access_token", "")
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

                filters: list[dict] = [{"type": "equals", "field": "mimeType", "value": "application/pdf"}]
                if keywords:
                    keyword_filters = []
                    for kw in keywords:
                        keyword_filters.append({"type": "contains", "field": "fileName", "value": kw})
                    filters.append({"type": "multi", "operator": "or", "queries": keyword_filters})

                r = await admin.post(
                    f"{self.base_url}/api/search/media",
                    headers=headers,
                    json={
                        "filter": filters,
                        "limit": limit,
                        "includes": {"media": ["id", "fileName", "fileExtension", "title", "url", "fileSize"]},
                    },
                )
                if r.status_code != 200:
                    return []

                docs = []
                for d in r.json().get("data", []):
                    a = d.get("attributes", {})
                    docs.append({
                        "id": d.get("id", ""),
                        "fileName": a.get("fileName", ""),
                        "title": a.get("title") or a.get("fileName", ""),
                        "url": a.get("url", ""),
                        "fileSize": a.get("fileSize", 0),
                    })
                return docs
        except Exception:
            return []

    async def get_product_documents(self, product_id: str) -> list[dict]:
        """Get download documents linked to a product via MillProductDownloadsTab custom field."""
        try:
            config = get_config()
            async with httpx.AsyncClient(timeout=15, verify=config.shopware.verify_ssl) as admin:
                auth_r = await admin.post(
                    f"{self.base_url}/api/oauth/token",
                    json={
                        "grant_type": "client_credentials",
                        "client_id": config.shopware.api_key,
                        "client_secret": config.shopware.integration_secret,
                    },
                )
                if auth_r.status_code != 200:
                    return []
                token = auth_r.json().get("access_token", "")
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

                # Get product custom fields
                r = await admin.post(
                    f"{self.base_url}/api/search/product",
                    headers=headers,
                    json={
                        "ids": [product_id],
                        "includes": {"product": ["customFields"]},
                        "limit": 1,
                    },
                )
                if r.status_code != 200:
                    return []

                products = r.json().get("data", [])
                if not products:
                    return []

                cf = products[0].get("attributes", {}).get("customFields") or {}
                media_ids = []
                for key, val in cf.items():
                    if "download" in key.lower() and val:
                        if isinstance(val, str):
                            media_ids.append(val)
                        elif isinstance(val, list):
                            media_ids.extend(val)

                if not media_ids:
                    return []

                # Fetch media details
                r2 = await admin.post(
                    f"{self.base_url}/api/search/media",
                    headers=headers,
                    json={
                        "ids": media_ids,
                        "includes": {"media": ["id", "fileName", "title", "url", "fileSize"]},
                    },
                )
                if r2.status_code != 200:
                    return []

                docs = []
                for d in r2.json().get("data", []):
                    a = d.get("attributes", {})
                    docs.append({
                        "id": d.get("id", ""),
                        "fileName": a.get("fileName", ""),
                        "title": a.get("title") or a.get("fileName", ""),
                        "url": a.get("url", ""),
                        "fileSize": a.get("fileSize", 0),
                    })
                return docs
        except Exception:
            return []

    async def download_media_content(self, url: str) -> bytes | None:
        """Download a media file's content."""
        try:
            config = get_config()
            async with httpx.AsyncClient(timeout=30, verify=config.shopware.verify_ssl) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    return r.content
        except Exception:
            pass
        return None

    # ---- Config ----

    async def get_config(self, sales_channel_id: str | None = None) -> dict:
        params = {"salesChannelId": sales_channel_id} if sales_channel_id else None
        result = await self._get("/voltimax/api/config", params)
        return result or {}

    # ---- Orders ----

    async def get_order(self, order_number: str, sales_channel_id: str | None = None, customer_email: str | None = None) -> dict | None:
        params: dict = {"orderNumber": order_number}
        if sales_channel_id:
            params["salesChannelId"] = sales_channel_id
        if customer_email:
            params["customerEmail"] = customer_email
        return await self._get("/voltimax/api/orders", params)

    async def get_customer_orders(self, email: str, sales_channel_id: str | None = None) -> list:
        # Orders are indexed by customerId, so look up the customer first
        customer = await self.get_customer(email, sales_channel_id)
        if not customer or isinstance(customer, dict) and customer.get("error"):
            return []
        customer_id = customer.get("id")
        if not customer_id:
            return []
        params: dict = {"customerId": customer_id, "limit": "10"}
        if sales_channel_id:
            params["salesChannelId"] = sales_channel_id
        result = await self._get("/voltimax/api/orders", params)
        return result if isinstance(result, list) else []

    async def get_return_status(self, order_number: str, sales_channel_id: str | None = None) -> dict | None:
        params = {"salesChannelId": sales_channel_id} if sales_channel_id else None
        return await self._get(f"/voltimax/api/returns/{order_number}", params)

    # ---- Products ----

    async def get_product(self, product_number: str, sales_channel_id: str | None = None) -> dict | None:
        params: dict = {"productNumber": product_number}
        if sales_channel_id:
            params["salesChannelId"] = sales_channel_id
        return await self._get("/voltimax/api/products", params)

    async def search_products(self, query: str, sales_channel_id: str | None = None) -> list:
        params: dict = {"search": query}
        if sales_channel_id:
            params["salesChannelId"] = sales_channel_id
        result = await self._get("/voltimax/api/products", params)
        return result if isinstance(result, list) else []

    # ---- Customers ----

    async def get_customer(self, email: str, sales_channel_id: str | None = None) -> dict | None:
        params = {"salesChannelId": sales_channel_id} if sales_channel_id else None
        return await self._get(f"/voltimax/api/customer/{email}", params)

    async def get_customer_addresses(self, email: str, sales_channel_id: str | None = None) -> list:
        params = {"salesChannelId": sales_channel_id} if sales_channel_id else None
        result = await self._get(f"/voltimax/api/customer/{email}/addresses", params)
        return result if isinstance(result, list) else []

    # ---- CMS (for knowledge base sync) ----

    async def get_cms_pages(self, sales_channel_id: str | None = None) -> list:
        params: dict = {"type": "pages"}
        if sales_channel_id:
            params["salesChannelId"] = sales_channel_id
        result = await self._get("/voltimax/api/cms", params)
        return result if isinstance(result, list) else []

    async def get_cms_categories(self, sales_channel_id: str | None = None) -> list:
        params: dict = {"type": "categories"}
        if sales_channel_id:
            params["salesChannelId"] = sales_channel_id
        result = await self._get("/voltimax/api/cms", params)
        return result if isinstance(result, list) else []

    async def get_cms_products(self, sales_channel_id: str | None = None) -> list:
        params = {"salesChannelId": sales_channel_id} if sales_channel_id else None
        result = await self._get("/voltimax/api/cms/products", params)
        return result if isinstance(result, list) else []

    # ---- B2B ----

    async def get_b2b_quotes(self, email: str, sales_channel_id: str | None = None) -> dict:
        params = {"salesChannelId": sales_channel_id} if sales_channel_id else None
        result = await self._get(f"/voltimax/api/b2b/{email}/quotes", params)
        return result or {}

    async def get_b2b_employees(self, email: str, sales_channel_id: str | None = None) -> dict:
        params = {"salesChannelId": sales_channel_id} if sales_channel_id else None
        result = await self._get(f"/voltimax/api/b2b/{email}/employees", params)
        return result or {}

    # ---- Store API (read-only) ----
    # Only GET and search POST (filter criteria) are exposed here.
    # Cart, checkout, account writes are intentionally omitted.

    async def _store_get(self, path: str, params: dict | None = None) -> dict | list | None:
        """Read-only GET against /store-api/..."""
        if not get_config().shopware.store_api_key:
            return {"error": "store_api_key not configured"}
        client = await self._get_store_client()
        try:
            response = await client.get(path, params=params)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Store API returned {e.response.status_code}", "detail": str(e)}
        except httpx.RequestError as e:
            return {"error": "Failed to connect to Store API", "detail": str(e)}

    async def _store_post_search(self, path: str, body: dict) -> dict | list | None:
        """Read-only POST against /store-api/... — search/listing criteria only, never mutations."""
        if not get_config().shopware.store_api_key:
            return {"error": "store_api_key not configured"}
        client = await self._get_store_client()
        try:
            response = await client.post(path, json=body)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Store API returned {e.response.status_code}", "detail": str(e)}
        except httpx.RequestError as e:
            return {"error": "Failed to connect to Store API", "detail": str(e)}

    async def store_search_products(self, query: str, limit: int = 10) -> tuple[list, int]:
        """Full-text product search via Store API. Returns (elements, total_count)."""
        result = await self._store_post_search(
            "/store-api/search",
            {
                "search": query,
                "limit": limit,
                "associations": {
                    "properties": {"associations": {"group": {}}},
                },
            },
        )
        if not result or isinstance(result, dict) and result.get("error"):
            return [], 0
        if isinstance(result, dict):
            elements = result.get("elements", [])
            total = result.get("total", len(elements))
        else:
            elements = result if isinstance(result, list) else []
            total = len(elements)
        return (elements if isinstance(elements, list) else []), total

    async def store_get_product(self, product_id: str) -> dict | None:
        """Fetch a single product by ID via Store API. Price includes VAT and channel rules."""
        return await self._store_get(f"/store-api/product/{product_id}")

    async def get_cheaper_alternative(self, product_id: str) -> dict | None:
        """Fetch the cheapest alternative for a product via CheaperAd Store API."""
        result = await self._store_get(f"/store-api/cheaper-ad/{product_id}")
        if result and isinstance(result, dict) and result.get("found"):
            return result.get("alternative")
        return None

    # ---- Vehicle Compatibility (OncoCompatibilityFilter) ----

    async def compatibility_get_children(self, parent_id: str | None = None) -> list[dict]:
        """Get child options for a compatibility level. No parent_id = root (Level 1)."""
        try:
            client = await self._get_store_client()
            params = {}
            if parent_id:
                params["id"] = parent_id
            response = await client.get("/onco-compatibility-get-children", params=params)
            if response.status_code == 200:
                data = response.json()
                return data.get("children", [])
        except Exception:
            pass
        return []

    async def compatibility_get_result(self, object_id: str) -> str | None:
        """Get the redirect URL (product listing) for a selected compatibility object."""
        try:
            client = await self._get_store_client()
            response = await client.get("/onco-compatibility-get-children", params={"id": object_id})
            if response.status_code == 200:
                data = response.json()
                url = data.get("url", "")
                if url:
                    return url
                children = data.get("children", [])
                if not children:
                    return object_id
        except Exception:
            pass
        return None

    async def compatibility_get_products(self, object_id: str) -> list:
        """Get compatible products for a vehicle via Admin API link table + Store API."""
        try:
            config = get_config()
            async with httpx.AsyncClient(timeout=15, verify=config.shopware.verify_ssl) as admin_client:
                auth_r = await admin_client.post(
                    f"{self.base_url}/api/oauth/token",
                    json={
                        "grant_type": "client_credentials",
                        "client_id": config.shopware.api_key,
                        "client_secret": config.shopware.integration_secret,
                    },
                )
                if auth_r.status_code != 200:
                    return []
                token = auth_r.json().get("access_token", "")

                links_r = await admin_client.post(
                    f"{self.base_url}/api/search/onco-compatibility-filter-link",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json={
                        "filter": [{"type": "equals", "field": "objectId", "value": object_id}],
                        "limit": 20,
                    },
                )
                if links_r.status_code != 200:
                    return []

                product_ids = []
                for e in links_r.json().get("data", []):
                    pid = e.get("attributes", {}).get("productId") or e.get("productId")
                    if pid:
                        product_ids.append(pid)

                if not product_ids:
                    return []

            store_client = await self._get_store_client()
            r = await store_client.post(
                "/store-api/product",
                json={
                    "ids": product_ids,
                    "associations": {"properties": {"associations": {"group": {}}}},
                },
            )
            if r.status_code == 200:
                items = r.json().get("elements", [])
                # Normalize properties
                for item in items:
                    sorted_props = item.get("sortedProperties")
                    if sorted_props and isinstance(sorted_props, list):
                        essential = {}
                        for sp in sorted_props:
                            group_name = sp.get("name", "")
                            options = sp.get("options", [])
                            if group_name and options:
                                essential[group_name] = options[0].get("name", "") if isinstance(options[0], dict) else str(options[0])
                        item["properties"] = essential
                return items
        except Exception:
            pass
        return []

    async def store_list_products(self, limit: int = 10, manufacturer: str | None = None) -> list:
        """List products via Store API with optional manufacturer filter."""
        body: dict[str, Any] = {"limit": limit}
        if manufacturer:
            body["filter"] = [{"type": "equals", "field": "manufacturer.name", "value": manufacturer}]
        result = await self._store_post_search("/store-api/product", body)
        if not result or isinstance(result, dict) and result.get("error"):
            return []
        elements = result.get("elements", []) if isinstance(result, dict) else result
        return elements if isinstance(elements, list) else []


# Singleton
_shopware_client: ShopwareClient | None = None


def get_shopware_client() -> ShopwareClient:
    global _shopware_client
    if _shopware_client is None:
        _shopware_client = ShopwareClient()
    return _shopware_client
