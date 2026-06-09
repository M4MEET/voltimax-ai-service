"""Dynamic card builder — generates universal card schemas from Shopware data."""
from __future__ import annotations

import hashlib
import time


def get_real_delivery_label(product: dict) -> str:
    """Compute actual delivery label based on stock, availability, and restockTime.

    - In stock + available → shipping time (e.g. "1-2 Tage")
    - Out of stock + available (backorder) → restockTime + shipping time
    - Out of stock + unavailable → "Nicht verfügbar" or restock estimate
    """
    stock = product.get("stock") or 0
    available = product.get("available", stock > 0)
    restock_days = product.get("restockTime") or 0

    delivery = product.get("deliveryTime")
    shipping_label = ""
    if delivery and isinstance(delivery, dict):
        shipping_label = delivery.get("name") or delivery.get("translated", {}).get("name", "")

    if stock > 0 and available:
        # In stock — use the configured shipping time
        return shipping_label or "Sofort lieferbar"

    if available and stock <= 0:
        # Backorder — customer can order but needs to wait for restock + shipping
        if restock_days:
            return f"~{restock_days} Tage (Nachbestellung)"
        return "Lieferzeit auf Anfrage"

    # Not available
    if restock_days:
        return f"Nicht verfügbar (~{restock_days} Tage)"
    return "Nicht verfügbar"


def _tracking_url(product_id: str, session_id: str = "") -> str:
    """Build a product URL with chat attribution that doesn't override UTM params.

    Uses custom `groot_*` parameters so Google Ads / other UTM attribution
    is preserved. Analytics can track both: which ad brought the customer
    AND that Groot recommended the product.
    """
    raw = f"{session_id}:{int(time.time())}"
    track_code = hashlib.sha256(raw.encode()).hexdigest()[:8]
    base = f"https://voltimax.de/detail/{product_id}"
    params = (
        f"?groot_ref=chat"
        f"&groot_session={track_code}"
        f"&groot_campaign=product_recommendation"
    )
    return base + params


def build_product_card(
    products: list[dict],
    session_id: str = "",
    from_compatibility: bool = False,
    listing_url: str = "",
    total_in_shop: int = 0,
    cheaper_alternative: dict | None = None,
    cheaper_alternatives: dict | None = None,
) -> dict | None:
    """Product recommendation card with 'Go to product' links and conversion tracking."""
    if not products:
        return None

    total_count = total_in_shop if total_in_shop > len(products) else len(products)
    links = []

    for p in products[:6]:
        name = p.get("name", "Unknown")[:55]
        product_id = p.get("id", "")
        stock = p.get("stock") or 0

        # Price
        calculated = p.get("calculatedPrice")
        if calculated and isinstance(calculated, dict):
            price = f"\u20ac{calculated.get('totalPrice', 0):.2f}"
        elif p.get("price") is not None:
            price = f"\u20ac{p['price']:.2f}"
        else:
            price = "\u2014"

        is_available = p.get("available", stock > 0)
        avail = "\u2705" if is_available else "\u274c"

        # Real delivery time based on stock + availability
        delivery_label = get_real_delivery_label(p)

        # Essential properties — pick the most useful 3-4
        props = p.get("properties", {})
        spec_parts = []
        if props and isinstance(props, dict):
            for k, v in list(props.items())[:4]:
                spec_parts.append(f"{v}")

        specs_line = " \u2022 ".join(spec_parts) if spec_parts else ""

        # Build detail: price + availability + delivery + specs
        detail = f"{price} {avail}"
        if delivery_label:
            detail += f" \u2022 \U0001F69A {delivery_label}"
        if specs_line:
            detail += f"\n{specs_line}"

        # Extract numeric price for GA4 ecommerce
        calculated = p.get("calculatedPrice")
        if calculated and isinstance(calculated, dict):
            _numeric_price = calculated.get("totalPrice", 0)
        elif p.get("price") is not None:
            _numeric_price = p["price"]
        else:
            _numeric_price = 0

        url = _tracking_url(product_id, session_id) if product_id else ""
        links.append({
            "label": name,
            "url": url,
            "detail": detail,
            "product_id": product_id,
            "product_price": round(_numeric_price, 2),
            "product_number": p.get("productNumber", ""),
        })

        # Per-product cheaper alternative (from cheaper_alternatives dict)
        _alts = cheaper_alternatives or {}
        if product_id and product_id in _alts:
            _alt = _alts[product_id]
            _alt_name = _alt.get("name", "Alternative")[:45]
            _alt_price = _alt.get("price", 0)
            _alt_savings = _alt.get("savings", 0)
            _alt_id = _alt.get("id", "")
            _alt_avail = "\u2705" if _alt.get("available", True) else "\u274c"
            _alt_delivery = _alt.get("deliveryTime", "")
            _alt_detail = f"\u20ac{_alt_price:.2f} {_alt_avail} \u2022 \U0001F4B0 {_alt_savings:.0f}% g\u00fcnstiger!"
            if _alt_delivery:
                _alt_detail += f" \u2022 \U0001F69A {_alt_delivery}"
            _alt_url = _tracking_url(_alt_id, session_id) if _alt_id else ""
            links.append({
                "label": f"\u2B50 G\u00fcnstigere Alternative: {_alt_name}",
                "url": _alt_url,
                "detail": _alt_detail,
                "style": "alternative",
                "product_id": _alt_id,
                "product_price": round(_alt_price, 2),
            })

    shown = len([l for l in links if l.get("style") != "alternative"])
    if total_count == 1:
        title = "Produktempfehlung"
    elif total_count <= 6:
        title = f"{total_count} passende Produkte"
    else:
        title = f"{total_count} passende Produkte (Top {shown})"

    description = "Klicke auf ein Produkt, um es im Shop anzusehen und zu bestellen."

    if from_compatibility:
        description = (
            "\u26a0\ufe0f Wichtiger Hinweis!\n"
            "Um Ihrem Fahrzeug die passende Batterie zuordnen zu k\u00f6nnen, "
            "greifen wir auf umfangreiche Daten der Batteriehersteller zur\u00fcck. "
            "Aufgrund der unz\u00e4hligen Batterie- und Fahrzeugmodelle sind Fehler "
            "aber nie v\u00f6llig auszuschlie\u00dfen.\n\n"
            "Bitte vergleichen Sie zur Sicherheit folgende Punkte mit Ihrer alten Batterie:\n"
            "\u2713 Abmessungen\n"
            "\u2713 Polanordnung\n"
            "\u2713 Batterietechnologie\n"
            "\u2713 Bodenbefestigungsleiste"
        )

    # Add "view all on shop" link when listing URL is available
    if listing_url:
        if total_count > shown:
            links.append({
                "label": f"\U0001F4CB Alle {total_count} Produkte im Shop anzeigen \u2192",
                "url": listing_url,
            })
        else:
            links.append({
                "label": "\U0001F4CB Alle Ergebnisse im Shop anzeigen \u2192",
                "url": listing_url,
            })

    return {
        "card_type": "dynamic",
        "style": "amber" if from_compatibility else "blue",
        "icon": "\U0001F50D",
        "title": title,
        "rows": [],
        "links": links,
        "description": description,
        "actions": [
            "Versandkosten & Lieferzeit",
            "Anderes Fahrzeug pr\u00fcfen",
            "Wie ist das R\u00fcckgaberecht?",
            "Support kontaktieren",
        ] if from_compatibility else [
            "Fahrzeug-Kompatibilit\u00e4tscheck",
            "Versandkosten & Lieferzeit",
            "Wie ist das R\u00fcckgaberecht?",
            "Support kontaktieren",
        ],
    }


def build_compatibility_card(level1_options: list[dict] | None = None) -> dict:
    """Vehicle compatibility check card with cascading dropdowns."""
    fields = [
        {"name": "level1", "label": "Fahrzeugtyp", "type": "select", "options": level1_options or [], "placeholder": "W\u00e4hlen..."},
        {"name": "level2", "label": "Hersteller", "type": "select", "options": [], "placeholder": "Zuerst Fahrzeugtyp w\u00e4hlen", "depends_on": "level1"},
        {"name": "level3", "label": "Modell", "type": "select", "options": [], "placeholder": "Zuerst Hersteller w\u00e4hlen", "depends_on": "level2"},
        {"name": "level4", "label": "Motor / Baujahr", "type": "select", "options": [], "placeholder": "Zuerst Modell w\u00e4hlen", "depends_on": "level3"},
    ]
    return {
        "card_type": "dynamic",
        "style": "blue",
        "icon": "\U0001F697",
        "title": "Fahrzeug-Kompatibilit\u00e4tscheck",
        "description": "W\u00e4hle dein Fahrzeug, um passende Batterien zu finden.",
        "form": {
            "field": "compatibility_check",
            "fields": fields,
            "action": "check_compatibility",
            "submit_label": "Passende Batterie finden \u2192",
            "cascade_url": "/api/compatibility/children",
        },
        "rows": [],
    }


def build_document_card(documents: list[dict], title: str = "Dokumente", server_b_url: str = "") -> dict | None:
    """Document download card with links to Shopware media files."""
    if not documents:
        return None

    links = []
    for doc in documents[:6]:
        name = doc.get("title") or doc.get("fileName", "Dokument")
        url = doc.get("url") or doc.get("download_url", "")
        # Replace internal Docker URL with proxy through Server B
        if url and "shopware." in url:
            from urllib.parse import quote
            url = f"{server_b_url}/api/media/download?url={quote(url, safe='')}"
        size = doc.get("fileSize", 0)
        size_label = f" ({size // 1024}KB)" if size else ""

        links.append({
            "label": f"\U0001F4C4 {name}{size_label}",
            "url": url,
        })

    return {
        "card_type": "dynamic",
        "style": "purple",
        "icon": "\U0001F4C1",
        "title": title,
        "rows": [],
        "links": links,
        "description": "Klicke auf ein Dokument zum Herunterladen.",
    }


def build_order_verified_card(order: dict, order_number: str) -> dict:
    """Simple verified card with action buttons."""
    status = order.get("statusLabel") or order.get("status", "Unknown")
    items = len(order.get("lineItems", []))
    total = order.get("amountTotal") or order.get("totalAmount") or 0
    date = str(order.get("orderDate", order.get("orderDateTime", "")))[:10]

    return {
        "card_type": "dynamic",
        "style": "green",
        "icon": "\u2713",
        "title": f"Bestellung #{order_number} \u2014 Verifiziert",
        "rows": [
            {"label": "Status", "value": status},
            {"label": "Artikel", "value": str(items)},
            {"label": "Gesamtbetrag", "value": f"\u20ac{total:.2f}" if total else "\u2014"},
            {"label": "Bestelldatum", "value": date},
        ],
        "actions": [
            "Sendung verfolgen",
            "Zahlungsstatus",
            "Rechnung anfordern",
            "Retoure starten",
            "Garantie pr\u00fcfen",
            "Problem melden",
            "An Support eskalieren",
        ],
        "meta_actions": ["Andere Bestellung pr\u00fcfen"],
    }


def build_tracking_card(order: dict, order_number: str) -> dict:
    """Tracking/delivery status card with carrier links."""
    deliveries = order.get("deliveries", [])
    delivery = deliveries[0] if deliveries else {}

    delivery_status = delivery.get("deliveryStatus", "")
    carrier = delivery.get("shippingMethod", "")
    tracking_codes = delivery.get("trackingCodes", [])
    ship_date = delivery.get("shippingDate", "")

    style_map = {
        "shipped": "green",
        "shipped_partially": "amber",
        "open": "blue",
        "returned": "red",
        "returned_partially": "red",
        "cancelled": "gray",
    }
    icon_map = {
        "shipped": "\U0001f4e6",
        "shipped_partially": "\U0001f4e6",
        "open": "\u23f3",
        "returned": "\u21a9\ufe0f",
        "returned_partially": "\u21a9\ufe0f",
        "cancelled": "\u274c",
    }
    status_labels = {
        "shipped": "Versendet",
        "shipped_partially": "Teilweise versendet",
        "open": "In Vorbereitung",
        "returned": "Retourniert",
        "returned_partially": "Teilweise retourniert",
        "cancelled": "Storniert",
    }
    status_descs = {
        "shipped": "Deine Bestellung wurde versendet und ist unterwegs.",
        "shipped_partially": "Ein Teil der Bestellung wurde versendet. Der Rest wird vorbereitet.",
        "open": "Deine Bestellung wird vorbereitet. Die Sendungsverfolgung ist verf\u00fcgbar, sobald die Lieferung versendet wurde.",
        "returned": "Deine Retoure ist eingegangen. Die R\u00fcckerstattung wird bearbeitet.",
        "returned_partially": "Ein Teil wurde retourniert. Die teilweise R\u00fcckerstattung wird bearbeitet.",
        "cancelled": "Diese Lieferung wurde storniert.",
    }

    style = style_map.get(delivery_status, "blue")
    icon = icon_map.get(delivery_status, "\U0001f4e6")
    label = status_labels.get(delivery_status, delivery.get("deliveryStatusLabel", "Unknown"))

    rows = [
        {
            "label": "Lieferstatus",
            "value": label,
            "style": "success" if delivery_status and "shipped" in delivery_status else "default",
        },
        {
            "label": "Bestellstatus",
            "value": order.get("statusLabel") or order.get("status", "Unbekannt"),
        },
    ]
    if carrier:
        rows.append({"label": "Versanddienstleister", "value": carrier})
    if ship_date:
        rows.append({"label": "Versanddatum", "value": ship_date})

    links = []
    for code in tracking_codes:
        carrier_lower = carrier.lower() if carrier else ""
        if "dhl" in carrier_lower:
            url = f"https://www.dhl.de/de/privatkunden/pakete-empfangen/verfolgen.html?lang=de&idc={code}"
        elif "dpd" in carrier_lower:
            url = f"https://tracking.dpd.de/status/de_DE/parcel/{code}"
        elif "ups" in carrier_lower:
            url = f"https://www.ups.com/track?tracknum={code}"
        elif "gls" in carrier_lower:
            url = f"https://gls-group.com/track/{code}"
        elif "hermes" in carrier_lower:
            url = f"https://www.myhermes.de/empfangen/sendungsverfolgung/sendungsinformation/#{code}"
        else:
            url = ""
        links.append({"label": f"\U0001f517 {code}", "url": url, "copy": code})

    # Context-aware follow-ups based on delivery status
    actions = []
    if delivery_status in ("shipped", "shipped_partially"):
        actions = [
            "Zahlungsstatus",
            "Rechnung anfordern",
            "Problem melden",
            "Retoure starten",
            "Andere Bestellung pr\u00fcfen",
        ]
    elif delivery_status == "open":
        actions = [
            "Wann wird es versendet?",
            "Bestellung stornieren",
            "Zahlungsstatus",
            "Rechnung anfordern",
            "Problem melden",
        ]
    elif delivery_status in ("returned", "returned_partially"):
        actions = [
            "Erstattungsstatus",
            "Zahlungsstatus",
            "Neue Bestellung aufgeben",
            "Support kontaktieren",
        ]
    elif delivery_status == "cancelled":
        actions = [
            "Warum wurde storniert?",
            "Erstattungsstatus",
            "Neue Bestellung aufgeben",
            "Support kontaktieren",
        ]
    else:
        actions = [
            "Zahlungsstatus",
            "Rechnung anfordern",
            "Problem melden",
            "Support kontaktieren",
        ]

    return {
        "card_type": "dynamic",
        "style": style,
        "icon": icon,
        "title": f"Order #{order_number} \u2014 {label}",
        "rows": rows,
        "links": links,
        "description": status_descs.get(delivery_status, ""),
        "actions": actions,
        "meta_actions": ["Andere Bestellung pr\u00fcfen"],
    }


def build_payment_card(order: dict, order_number: str) -> dict:
    """Payment status card."""
    payment = order.get("paymentStatus", "unknown")
    total = order.get("amountTotal") or order.get("totalAmount") or 0
    date = str(order.get("orderDate", ""))[:10]

    payment_info = {
        "paid": {"label": "\u2705 Bezahlt", "style": "green", "icon": "\u2705"},
        "authorized": {"label": "\u2705 Autorisiert", "style": "green", "icon": "\u2705"},
        "open": {"label": "\u23f3 Zahlung ausstehend", "style": "blue", "icon": "\u23f3"},
        "refunded": {"label": "\u21a9\ufe0f Vollst\u00e4ndig erstattet", "style": "red", "icon": "\u21a9\ufe0f"},
        "refunded_partially": {"label": "\u21a9\ufe0f Teilweise erstattet", "style": "amber", "icon": "\u21a9\ufe0f"},
        "paid_partially": {"label": "\u26a0\ufe0f Teilweise bezahlt", "style": "amber", "icon": "\u26a0\ufe0f"},
        "failed": {"label": "\u274c Zahlung fehlgeschlagen", "style": "red", "icon": "\u274c"},
        "cancelled": {"label": "\u274c Zahlung storniert", "style": "gray", "icon": "\u274c"},
        "reminded": {"label": "\U0001f4e7 Zahlungserinnerung gesendet", "style": "amber", "icon": "\U0001f4e7"},
        "chargeback": {"label": "\u26a0\ufe0f R\u00fcckbuchung", "style": "red", "icon": "\u26a0\ufe0f"},
    }
    info = payment_info.get(payment, {"label": payment, "style": "gray", "icon": "\u2753"})

    # Context-aware follow-ups based on payment status
    if payment in ("paid", "authorized"):
        actions = [
            "Sendung verfolgen",
            "Rechnung anfordern",
            "Retoure starten",
            "Garantie pr\u00fcfen",
            "Andere Bestellung pr\u00fcfen",
        ]
    elif payment in ("open", "paid_partially", "reminded"):
        actions = [
            "Wie kann ich bezahlen?",
            "Zahlungsmethode \u00e4ndern",
            "Sendung verfolgen",
            "Problem melden",
            "Support kontaktieren",
        ]
    elif payment in ("refunded", "refunded_partially"):
        actions = [
            "Wann kommt die Erstattung?",
            "Sendung verfolgen",
            "Neue Bestellung aufgeben",
            "Support kontaktieren",
        ]
    elif payment in ("failed", "cancelled", "chargeback"):
        actions = [
            "Warum ist die Zahlung fehlgeschlagen?",
            "Erneut bezahlen",
            "Zahlungsmethode \u00e4ndern",
            "Problem melden",
            "Support kontaktieren",
        ]
    else:
        actions = [
            "Sendung verfolgen",
            "Rechnung anfordern",
            "Problem melden",
            "Support kontaktieren",
        ]

    return {
        "card_type": "dynamic",
        "style": info["style"],
        "icon": info["icon"],
        "title": f"Zahlung \u2014 Bestellung #{order_number}",
        "rows": [
            {"label": "Zahlungsstatus", "value": info["label"], "style": "success" if payment == "paid" else "default"},
            {"label": "Gesamtbetrag", "value": f"\u20ac{total:.2f}" if total else "\u2014"},
            {"label": "Bestelldatum", "value": date},
        ],
        "actions": actions,
        "meta_actions": ["Andere Bestellung pr\u00fcfen"],
    }


def build_invoice_card(order_number: str, docs: list) -> dict:
    """Invoice/documents list card."""
    links = []
    rows = []
    for doc in docs:
        rows.append({"label": doc.get("type", "Document"), "value": doc.get("name", ""), "style": "default"})
        if doc.get("url"):
            links.append({"label": f"\U0001f4c4 {doc['name']} \u2014 Download", "url": doc["url"]})

    return {
        "card_type": "dynamic",
        "style": "purple",
        "icon": "\U0001f9fe",
        "title": f"Documents \u2014 Order #{order_number}",
        "rows": rows if not links else [],
        "links": links,
        "description": f"{len(docs)} document(s) available for download." if docs else "No documents available yet.",
        "actions": [
            "Sendung verfolgen",
            "Zahlungsstatus",
            "Retoure starten",
            "Garantie pr\u00fcfen",
            "Problem melden",
            "Andere Bestellung pr\u00fcfen",
        ],
    }


def build_order_failed_card(order_number: str) -> dict:
    """Order verification failed card."""
    return {
        "card_type": "dynamic",
        "style": "red",
        "icon": "\u2717",
        "title": f"Bestellung #{order_number} \u2014 Verifizierung fehlgeschlagen",
        "rows": [],
        "description": (
            "Wir konnten diese Bestellung mit den angegebenen Daten nicht finden. "
            "Bitte \u00fcberpr\u00fcfe deine Bestellnummer und Rechnungs-PLZ.\n\n"
            "\u2022 Pr\u00fcfe die Best\u00e4tigungs-E-Mail f\u00fcr die richtige Bestellnummer\n"
            "\u2022 Verwende die PLZ der Rechnungsadresse, nicht der Lieferadresse\n"
            "\u2022 Achte auf Leerzeichen oder Tippfehler"
        ),
        "actions": [
            "Erneut versuchen",
            "Ticket-Status pr\u00fcfen",
            "Produktfrage",
        ],
        "meta_actions": ["Support kontaktieren"],
    }


def build_warranty_card(order: dict, order_number: str) -> dict:
    """Warranty information card based on order items."""
    items = order.get("lineItems", [])
    rows = []
    for item in items[:5]:
        label = item.get("label", "Unknown")
        if "batterie" in label.lower() or "battery" in label.lower():
            rows.append({"label": label[:40], "value": "2\u20134 Jahre Garantie", "style": "success"})
        elif "solar" in label.lower() or "panel" in label.lower():
            rows.append({"label": label[:40], "value": "10\u201325 Jahre Garantie", "style": "success"})
        elif "pfand" not in label.lower():
            rows.append({"label": label[:40], "value": "2 years (legal)", "style": "default"})

    return {
        "card_type": "dynamic",
        "style": "blue",
        "icon": "\U0001f6e1\ufe0f",
        "title": f"Warranty \u2014 Order #{order_number}",
        "rows": rows,
        "description": "Warranty periods vary by product and manufacturer. Contact us for warranty claims.",
        "actions": [
            "Problem melden",
            "Retoure starten",
            "Rechnung anfordern",
            "Sendung verfolgen",
            "Support kontaktieren",
        ],
    }


def build_ticket_created_card(ticket_id: str, topic: str = "", summary: str = "") -> dict:
    """Ticket confirmation card with copy button for ticket ID."""
    rows = [
        {"label": "Ticket ID", "value": f"#{ticket_id}", "style": "success"},
    ]
    if topic:
        rows.append({"label": "Topic", "value": topic, "style": "default"})
    rows.append({"label": "Status", "value": "Offen \u2014 wird bearbeitet", "style": "default"})

    return {
        "card_type": "dynamic",
        "style": "green",
        "icon": "\u2705",
        "title": "Support Ticket Created",
        "rows": rows,
        "links": [
            {"label": f"\U0001F4CB Ticket #{ticket_id}", "url": "", "copy": ticket_id},
        ],
        "description": summary[:200] if summary else "Our support team will review your request and follow up shortly.",
        "actions": [
            "Ticket-Status pr\u00fcfen",
            "Weitere Frage stellen",
            "Bestellung pr\u00fcfen",
            "Produktfrage",
        ],
    }


def build_ticket_lookup_card() -> dict:
    """Ticket lookup form card — enter ticket # + email to check status."""
    return {
        "card_type": "dynamic",
        "style": "blue",
        "icon": "\U0001F50D",
        "title": "Ticket-Status pr\u00fcfen",
        "description": "Gib deine Ticketnummer und E-Mail-Adresse ein, um den Status deiner Supportanfrage zu pr\u00fcfen.",
        "form": {
            "field": "ticket_verify",
            "fields": [
                {"name": "ticket_id", "label": "Ticketnummer", "placeholder": "#...", "type": "text"},
                {"name": "email", "label": "E-Mail", "placeholder": "deine@email.com", "type": "text"},
            ],
            "action": "check_ticket",
            "submit_label": "Status pr\u00fcfen \u2192",
        },
    }


def build_ticket_status_card(ticket: dict) -> dict:
    """Ticket status card with details and optional urgent button."""
    status = ticket.get("status", "unknown")
    priority = ticket.get("priority", "normal")

    style_map = {
        "new": "blue", "open": "amber", "pending": "amber",
        "hold": "gray", "solved": "green", "closed": "gray",
    }
    icon_map = {
        "new": "\U0001F4E9", "open": "\U0001F4CB", "pending": "\u23F3",
        "hold": "\u270B", "solved": "\u2705", "closed": "\u2611\uFE0F",
    }
    status_labels = {
        "new": "New", "open": "Open", "pending": "Pending",
        "hold": "On Hold", "solved": "Solved", "closed": "Closed",
    }

    rows = [
        {"label": "Status", "value": status_labels.get(status, status.title()), "style": "success" if status == "solved" else "default"},
        {"label": "Priorit\u00e4t", "value": priority.title(), "style": "default"},
        {"label": "Betreff", "value": ticket.get("subject", "")[:60], "style": "default"},
        {"label": "Erstellt", "value": ticket.get("created_at", ""), "style": "default"},
        {"label": "Aktualisiert", "value": ticket.get("updated_at", ""), "style": "default"},
    ]

    links = [
        {"label": f"\U0001F4CB Ticket #{ticket['id']}", "url": "", "copy": ticket["id"]},
    ]

    card = {
        "card_type": "dynamic",
        "style": style_map.get(status, "gray"),
        "icon": icon_map.get(status, "\U0001F4CB"),
        "title": f"Ticket #{ticket['id']} \u2014 {status_labels.get(status, status.title())}",
        "rows": rows,
        "links": links,
    }

    last_comment = ticket.get("last_comment", "")
    if last_comment:
        card["description"] = last_comment[:200]

    # Context-aware follow-ups based on ticket status
    actions = []
    if status in ("new", "open", "pending"):
        if priority != "urgent":
            actions.append("\U0001F6A8 Mark as Urgent")
        actions.extend([
            "Bestellung pr\u00fcfen",
            "Weitere Frage stellen",
            "Produktfrage",
        ])
    elif status == "solved":
        actions = [
            "Bestellung pr\u00fcfen",
            "Neues Ticket erstellen",
            "Produktfrage",
            "Weitere Frage stellen",
        ]
    elif status == "closed":
        actions = [
            "Neues Ticket erstellen",
            "Bestellung pr\u00fcfen",
            "Produktfrage",
        ]
    elif status == "hold":
        actions = [
            "Bestellung pr\u00fcfen",
            "Weitere Frage stellen",
            "Produktfrage",
        ]
    card["actions"] = actions

    return card


def build_ticket_urgent_card(ticket_id: str) -> dict:
    """Confirmation card after ticket is marked urgent."""
    return {
        "card_type": "dynamic",
        "style": "red",
        "icon": "\U0001F6A8",
        "title": f"Ticket #{ticket_id} \u2014 Marked as Urgent",
        "rows": [
            {"label": "Priorit\u00e4t", "value": "Dringend", "style": "default"},
            {"label": "Status", "value": "Offen \u2014 Team benachrichtigt", "style": "default"},
        ],
        "links": [
            {"label": f"\U0001F4CB Ticket #{ticket_id}", "url": "", "copy": ticket_id},
        ],
        "description": "Our team has been notified and will prioritize your request for faster response.",
        "actions": [
            "Ticket-Status pr\u00fcfen",
            "Bestellung pr\u00fcfen",
            "Weitere Frage stellen",
            "Produktfrage",
        ],
    }


def build_order_lookup_card() -> dict:
    """Order lookup form card — shown when verification is needed."""
    return {
        "card_type": "dynamic",
        "style": "blue",
        "icon": "\U0001F50D",
        "title": "Bestellung suchen",
        "description": "Gib deine Bestellnummer und Rechnungs-PLZ ein, um deine Bestellung aufzurufen.",
        "form": {
            "field": "order_verify",
            "fields": [
                {"name": "order_number", "label": "Bestellnummer", "placeholder": "z.B. 10324", "type": "text"},
                {"name": "postcode", "label": "Rechnungs-PLZ", "placeholder": "z.B. 81549", "type": "text"},
            ],
            "action": "verify_order",
            "submit_label": "Bestellung suchen \u2192",
        },
        "meta_actions": [
            "Ich habe keine Bestellung",
            "Ticket-Status pr\u00fcfen",
            "Produktfrage",
        ],
    }


def build_no_order_card() -> dict:
    """Card shown when user doesn't have an existing order — routes to pre-sales help."""
    return {
        "card_type": "dynamic",
        "style": "blue",
        "icon": "\U0001F4AC",
        "title": "Wie kann ich helfen?",
        "description": "Kein Problem! Ich kann dir trotzdem weiterhelfen:",
        "rows": [
            {"label": "\U0001F6CD\uFE0F Produkte", "value": "Batterie, Solarpanel oder Zubeh\u00f6r finden", "style": "default"},
            {"label": "\U0001F69B Versand", "value": "Lieferzeiten, Kosten und Express-Optionen", "style": "default"},
            {"label": "\u2753 Fragen", "value": "Kompatibilit\u00e4t, Technische Daten, Einbauanleitungen", "style": "default"},
            {"label": "\U0001F4B3 Zahlung", "value": "Zahlungsarten, Rechnungen, B2B-Preise", "style": "default"},
        ],
        "actions": [
            "Produktfrage",
            "Welche Batterie passt?",
            "Versandkosten",
            "Technische Beratung",
            "Solarpanel Beratung",
            "Support kontaktieren",
            "Ticket-Status pr\u00fcfen",
        ],
    }


def build_batteriepfand_download_card(server_b_url: str = "") -> dict:
    """Card with Batteriepfand info, steps, and downloadable forms."""
    return {
        "card_type": "dynamic",
        "style": "green",
        "icon": "\u267b\ufe0f",
        "title": "Batteriepfand \u2014 Informationen & Formulare",
        "description": (
            "\u2139\ufe0f Informationen zum Batteriepfand\n"
            "Nach \u00a7 19 BattDG wird beim Kauf einer Starterbatterie ein Pfand von 7,50 \u20ac erhoben, "
            "wenn keine Altbatterie abgegeben wird. Ob Pfand erhoben wurde, steht auf Ihrer Rechnung.\n\n"
            "F\u00fcr die Erstattung gibt es zwei M\u00f6glichkeiten:\n"
            "\u2022 Altbatterie an uns zur\u00fccksenden (auf eigene Kosten) \u2014 nutzen Sie die \"Vorlage R\u00fccksendung\"\n"
            "\u2022 Altbatterie bei einer Abgabestelle entsorgen (Wertstoffhof, Schrotth\u00e4ndler) \u2014 "
            "lassen Sie sich die Entsorgung best\u00e4tigen und reichen Sie den \"Entsorgungsnachweis\" ein"
        ),
        "rows": [],
        "steps": [
            {
                "title": "Schritt 1: Entsorgungsbest\u00e4tigung herunterladen",
                "text": "Bitte laden Sie das Muster des Entsorgungsnachweises herunter und drucken Sie es aus. "
                        "Kein Drucker? Bitten Sie die Abgabestelle um eine schriftliche Best\u00e4tigung "
                        "oder lassen Sie es auf unserer Rechnung best\u00e4tigen.",
            },
            {
                "title": "Schritt 2: Entsorgung der Altbatterie",
                "text": "Entsorgen Sie Ihre Altbatterie bei einem Wertstoffhof, Schrotthandel, "
                        "einer Werkstatt oder bei jedem Vertrieb von Starterbatterien in Ihrer N\u00e4he. "
                        "Wichtig: Lassen Sie sich die Entsorgung unbedingt schriftlich auf dem Nachweis best\u00e4tigen. "
                        "Bitte achten Sie darauf, die Batterie aufrecht zu transportieren.",
            },
            {
                "title": "Schritt 3: Entsorgungsbest\u00e4tigung hochladen",
                "text": "Laden Sie den best\u00e4tigten Entsorgungsnachweis \u00fcber das Formular unten hoch. "
                        "Die Bearbeitungsdauer kann bis zu 30 Tagen dauern. "
                        "Die R\u00fcckzahlung erfolgt \u00fcber die gleiche Zahlungsart wie bei der Bestellung.",
            },
            {
                "title": "\u26a0\ufe0f Wichtige Fristen",
                "text": "Bitte reichen Sie den Entsorgungsnachweis innerhalb von 2 Wochen nach Entsorgung "
                        "und innerhalb von 30 Tagen nach Kauf der neuen Starterbatterie ein.",
                "style": "warning",
            },
        ],
        "links": [
            {
                "label": "\U0001F4C4 Vorlage Entsorgungsnachweis",
                "url": f"{server_b_url}/static/forms/Voltimax_Vorlage_Entsorgungsnachweis.pdf",
                "detail": "F\u00fcr Entsorgung bei Abgabestelle \u2014 PDF herunterladen",
            },
            {
                "label": "\U0001F4C4 Vorlage R\u00fccksendung Altbatterie",
                "url": f"{server_b_url}/static/forms/Voltimax_Vorlage_Ruecksendung_Altbatterie.pdf",
                "detail": "F\u00fcr R\u00fccksendung an Voltimax \u2014 PDF herunterladen",
            },
        ],
        "actions": [
            "Ich habe die Formulare ausgef\u00fcllt",
            "Noch Fragen zum Batteriepfand",
        ],
    }


def build_batteriepfand_upload_card() -> dict:
    """Card with selectable upload type for Batteriepfand submission."""
    return {
        "card_type": "batteriepfand_upload",
        "style": "green",
        "icon": "\U0001F4E4",
        "title": "Batteriepfand Formular hochladen",
        "description": "W\u00e4hle das Formular aus, das du einreichen m\u00f6chtest:",
        "upload_options": [
            {
                "key": "entsorgungsnachweis",
                "label": "Entsorgungsnachweis",
                "accept": ".pdf",
            },
            {
                "key": "ruecksendung",
                "label": "R\u00fccksendung Altbatterie",
                "accept": ".pdf",
            },
        ],
        "fields": [
            {"key": "customer_name", "label": "Name", "type": "text", "editable": True},
            {"key": "customer_email", "label": "E-Mail", "type": "text", "editable": True},
            {"key": "subject", "label": "Betreff", "type": "text", "editable": False, "value": "Groot Escalation \u2014 Batteriepfand"},
        ],
    }


def build_close_chat_card() -> dict:
    """Card shown when conversation seems complete — offers close or new chat."""
    return {
        "card_type": "close_chat",
        "style": "blue",
        "icon": "\U0001F44B",
        "title": "Kann ich noch etwas f\u00fcr dich tun?",
        "description": "Falls du keine weiteren Fragen hast, kannst du den Chat beenden. Wir freuen uns \u00fcber dein Feedback!",
    }
