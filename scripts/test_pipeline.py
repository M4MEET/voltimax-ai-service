#!/usr/bin/env python3
"""Classifier golden-set regression test.

Feeds a curated set of real customer messages through the unified classifier
and asserts the resulting `action`. Run this before/after any classifier
prompt change to catch regressions before customers hit them.

Usage:
    cd voltimax-ai-service
    venv/bin/python scripts/test_pipeline.py            # run all cases
    venv/bin/python scripts/test_pipeline.py -v         # show full result dicts

Each case is (label, message, context, expected_action). `context` carries the
classifier state that matters: has_verified_order, topic, and prior `history`
(so "follow-up" cases reflect what the customer already saw).

To grow the suite: every time the classifier misfires in production, add the
offending message here with its correct action. The set then guards that exact
bug forever.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

# History snippet representing "the order-lookup card was already shown once".
_AFTER_ORDER_CARD = [
    {"role": "user", "content": "Ich brauche meine Bestellnummer und Rechnungssummen"},
    {"role": "assistant", "content": "Um dir zu helfen, brauche ich deine Bestelldaten. Bitte gib sie hier ein: [Bestellung suchen]"},
]

# (label, message, context, expected_action)
CASES = [
    # ── #2BC03187 regression: customer can't find order number → must NOT loop ──
    ("cant-find-numbers",   "Ich finde die Nummern nicht",
        {"history": _AFTER_ORDER_CARD, "topic": "order_status"}, "order_lookup"),
    ("no-order-number",     "Ich habe keine Bestellnummer, ich habe mit s.montalbano@web.de bestellt",
        {"history": _AFTER_ORDER_CARD, "topic": "order_status"}, "order_lookup"),
    ("truly-no-order",      "Ich habe keine Bestellung",
        {"history": _AFTER_ORDER_CARD, "topic": "order_status"}, "no_order"),

    # ── core sanity / past regressions ──
    ("order-status",        "Wo ist meine Bestellung?",            {}, "order_lookup"),
    ("escalation",          "Ich möchte mit einem Mitarbeiter sprechen", {}, "escalation_ticket"),
    ("batteriepfand",       "Wie funktioniert der Batteriepfand?", {}, "batteriepfand"),
    ("compatibility-moto",  "Welche Batterie passt für meine Honda CBR 600?", {}, "compatibility_check"),
    ("account-info",        "Wie ändere ich meine Adresse im Kundenkonto?", {}, "account_info"),
    ("kundendienst-not-account", "Wie erreiche ich den Kundendienst?", {}, "none"),
    ("greeting",            "Hallo",                                {}, "none"),
    ("return-policy-rag",   "Wie funktioniert die Rückgabe?",       {}, "none"),
]


async def run_case(label, message, context, expected):
    from app.ai.unified_classifier import classify_message
    result = await classify_message(
        message=message,
        has_verified_order=context.get("has_verified_order", False),
        order_number=context.get("order_number", ""),
        topic=context.get("topic", "general"),
        has_cached_data=context.get("has_cached_data", False),
        history=context.get("history"),
    )
    got = result.get("action", "")
    return got == expected, got, result


async def main(verbose: bool = False):
    from app.db.mongodb import connect_db
    await connect_db()  # classifier prompt rendering / providers expect app wiring

    print(f"\nClassifier golden set — {len(CASES)} cases\n" + "=" * 64)
    passed = 0
    failures = []
    for label, message, context, expected in CASES:
        try:
            ok, got, result = await run_case(label, message, context, expected)
        except Exception as e:
            ok, got, result = False, f"ERROR: {e}", {}
        mark = "✅" if ok else "❌"
        print(f"{mark} {label:24s} expected={expected:18s} got={got}")
        if verbose:
            print(f"     {result}")
        if ok:
            passed += 1
        else:
            failures.append((label, message, expected, got))

    print("=" * 64)
    print(f"{passed}/{len(CASES)} passed")
    if failures:
        print("\nFailures:")
        for label, message, expected, got in failures:
            print(f"  • {label}: {message!r}\n      expected {expected}, got {got}")
    return 0 if not failures else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true", help="print full classifier result dicts")
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.verbose)))
