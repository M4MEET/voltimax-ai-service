from __future__ import annotations

import re

from langsmith import traceable

from app.ai.graph.state import ChatState
from app.config import get_config
from app.shopware.client import get_shopware_client


def _extract_order_number(text: str) -> str | None:
    """Extract an order number from free text. Shopware order numbers are typically numeric."""
    patterns = [
        r'\b(?:order|bestellung|order#|bestellung#|#)\s*([A-Z0-9]{5,20})\b',
        r'\b([0-9]{5,12})\b',  # plain numeric order numbers
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


@traceable(name="groot-product-search")
async def search_products(search_term: str, sales_channel_id: str | None = None) -> tuple[list[dict], int]:
    """Search Shopware for products and normalize properties.

    Returns (products, total_count) where total_count is the full Shopware
    match count (may be higher than len(products) due to API page limit).

    Reusable by both data_fetcher (inside LangGraph) and connection handler
    (pre-fetch before streaming).
    """
    client = get_shopware_client()
    total_count = 0
    if get_config().shopware.store_api_key:
        results, total_count = await client.store_search_products(search_term, limit=20)
    else:
        results = await client.search_products(search_term, sales_channel_id)

    if not results or (isinstance(results, dict) and results.get("error")):
        return [], 0

    items = results if isinstance(results, list) else []
    if not total_count:
        total_count = len(items)

    # Normalize Store API properties for the AI and product card
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
        else:
            props = item.get("properties")
            if props and isinstance(props, list):
                normalized = {}
                for prop in props:
                    group = prop.get("group", {})
                    if not isinstance(group, dict):
                        continue
                    if not group.get("visibleOnProductDetailPage", True):
                        continue
                    group_name = group.get("name", "")
                    prop_name = prop.get("name", "")
                    if group_name and prop_name:
                        normalized[group_name] = prop_name
                item["properties"] = normalized

    # Prefer available products; return all matches (up to API limit of 20).
    # Card builder caps display at 6 and shows a "view all" link for the rest.
    # AI context (_build_card_context / _format_shopware_data) also caps independently.
    available = [p for p in items if p.get("available", (p.get("stock") or 0) > 0)]
    unavailable = [p for p in items if not p.get("available", (p.get("stock") or 0) > 0)]
    return available + unavailable, total_count


def _build_card_context(data: dict, intent: str) -> str:
    """Build the card_context string describing what cards the customer will see."""
    card_parts = []
    if data.get("search_results"):
        products = data["search_results"]
        if intent == "product_doc_query":
            product_details = []
            for p in products[:3]:
                product_details.append(p.get("name", "")[:50])
            card_parts.append(
                f"DOCUMENT DOWNLOAD CARD shown with PDFs for: {', '.join(product_details)}.\n"
                "Customer can download directly from the card."
            )
        else:
            product_details = []
            for p in products[:6]:
                name = p.get("name", "")[:45]
                calc = p.get("calculatedPrice", {})
                price = f"\u20ac{calc.get('totalPrice', 0):.2f}" if isinstance(calc, dict) and calc.get("totalPrice") else (f"\u20ac{p.get('price', 0):.2f}" if p.get("price") else "")
                stock = p.get("stock") or 0
                is_available = p.get("available", stock > 0)
                avail = "available" if is_available else "out of stock"
                props = p.get("properties", {})
                specs = ", ".join(f"{v}" for k, v in list(props.items())[:3]) if isinstance(props, dict) else ""
                from app.ai.card_builder import get_real_delivery_label
                dt_name = get_real_delivery_label(p)
                line = f"- {name} | {price} | {avail}"
                if dt_name:
                    line += f" | {dt_name}"
                if specs:
                    line += f" | {specs}"
                product_details.append(line)
            card_parts.append(
                "PRODUCT CARD shown with:\n" + "\n".join(product_details) + "\n"
                "Each product has a 'Zum Produkt' link. The card shows all details — keep your response short."
            )
    if data.get("cheaper_alternatives"):
        alt_count = len(data["cheaper_alternatives"])
        card_parts.append(
            f"{alt_count} product(s) have cheaper alternatives shown as green cards below them. "
            "Mention this briefly — the card shows the details."
        )
    if data.get("order"):
        order = data["order"]
        deliveries = order.get("deliveries", [])
        delivery_info = ""
        if deliveries:
            d = deliveries[0]
            delivery_info = f", delivery: {d.get('deliveryStatus', '?')}"
            codes = d.get("trackingCodes", [])
            if codes:
                delivery_info += f", tracking: {', '.join(codes)}"
        items = [item.get("label", "")[:30] for item in order.get("lineItems", [])[:3]]
        card_parts.append(
            f"ORDER CARD shown: #{order.get('orderNumber', '?')} | "
            f"status: {order.get('statusLabel', '?')} | payment: {order.get('paymentStatus', '?')}{delivery_info}\n"
            f"Items: {', '.join(items)}\n"
            "The card shows full order details — keep your response brief."
        )
    return "\n".join(card_parts)


@traceable(name="groot-data-fetcher")
async def fetch_shopware_data(state: ChatState) -> ChatState:
    """Fetch relevant data from Server A based on intent."""
    # If data was pre-fetched (by connection handler), skip fetch but build card_context
    if state.data_pre_fetched and state.shopware_data:
        state.card_context = _build_card_context(state.shopware_data, state.intent)
        return state

    if not state.needs_shopware_data:
        return state

    client = get_shopware_client()
    # Use the verified order email if available (may differ from JWT login email)
    email = state.session.get("order_email") or state.user_claims.get("email", "")
    sales_channel_id = state.user_claims.get("sales_channel_id")

    # Use extracted search_query (which contains the order number for order_queries),
    # then try extracting from the raw message, then fall back to JWT claim
    order_number = (
        state.search_query
        or _extract_order_number(state.user_message)
        or state.user_claims.get("order_number")
    )

    data: dict = {}

    # Always inject cached order data if available — covers all query types
    cached_order = state.session.get("cached_order_data")
    if cached_order:
        data["order"] = cached_order

    if state.data_type == "order":
        # Use cached order data if available (cached after verification)
        if cached_order:
            pass  # Already injected above
        else:
            # No cached data — check for verified order number
            verified_order = state.session.get("order_number")
            if not verified_order:
                state.needs_shopware_data = False
                return state
            order_number = verified_order
            order = await client.get_order(order_number, sales_channel_id, customer_email=email)
            if order and not (isinstance(order, dict) and order.get("error")):
                data["order"] = order
            else:
                data["order_not_owned"] = order_number

    elif state.data_type == "return":
        # Use cached order data if available (cached after verification)
        cached = state.session.get("cached_order_data")
        if cached:
            data["order"] = cached
            # Still need to fetch return-specific status
            verified_order = state.session.get("order_number")
            if verified_order:
                ret = await client.get_return_status(verified_order, sales_channel_id)
                if ret and not (isinstance(ret, dict) and ret.get("error")):
                    data["return_status"] = ret
        else:
            verified_order = state.session.get("order_number")
            if not verified_order:
                state.needs_shopware_data = False
                return state
            order_number = verified_order
            order = await client.get_order(order_number, sales_channel_id, customer_email=email)
            if order and not (isinstance(order, dict) and order.get("error")):
                data["order"] = order
                ret = await client.get_return_status(order_number, sales_channel_id)
                if ret and not (isinstance(ret, dict) and ret.get("error")):
                    data["return_status"] = ret
            else:
                data["order_not_owned"] = order_number

    elif state.data_type == "product":
        # Extract specific product number if mentioned
        product_number = _extract_order_number(state.user_message)  # same pattern works
        if product_number:
            product = await client.get_product(product_number=product_number, sales_channel_id=sales_channel_id)
            if product and not (isinstance(product, dict) and product.get("error")):
                data["product"] = product

        search_term = state.search_query or state.user_message
        products, _total = await search_products(search_term, sales_channel_id)
        if products:
            data["search_results"] = products

    elif state.data_type == "customer":
        customer = await client.get_customer(email, sales_channel_id)
        if customer and not (isinstance(customer, dict) and customer.get("error")):
            data["customer"] = customer
        addresses = await client.get_customer_addresses(email, sales_channel_id)
        if addresses and not (isinstance(addresses, dict) and addresses.get("error")):
            data["addresses"] = addresses if isinstance(addresses, list) else []

    elif state.data_type == "b2b":
        quotes = await client.get_b2b_quotes(email, sales_channel_id)
        if quotes and not (isinstance(quotes, dict) and quotes.get("error")):
            data["quotes"] = quotes
        employees = await client.get_b2b_employees(email, sales_channel_id)
        if employees and not (isinstance(employees, dict) and employees.get("error")):
            data["employees"] = employees

    state.shopware_data = data if data else None
    state.card_context = _build_card_context(data, state.intent)
    return state
