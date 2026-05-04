"""LangSmith integration utilities -- feedback, evaluators, run tracking."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def is_langsmith_enabled() -> bool:
    return bool(os.getenv("LANGCHAIN_API_KEY"))


async def send_feedback_to_langsmith(run_id: str, feedback: str, comment: str = "") -> bool:
    """Send thumbs up/down feedback to LangSmith linked to a specific run."""
    if not is_langsmith_enabled() or not run_id:
        return False

    try:
        from langsmith import Client
        client = Client()
        score = 1.0 if feedback == "up" else 0.0
        client.create_feedback(
            run_id=run_id,
            key="user-feedback",
            score=score,
            value=feedback,
            comment=comment or f"User gave {feedback} feedback",
        )
        logger.info(f"LangSmith feedback sent: run={run_id} feedback={feedback}")
        return True
    except Exception as e:
        logger.error(f"Failed to send LangSmith feedback: {e}")
        return False


async def send_rating_to_langsmith(run_id: str, rating: int) -> bool:
    """Send star rating (1-5) to LangSmith."""
    if not is_langsmith_enabled() or not run_id:
        return False

    try:
        from langsmith import Client
        client = Client()
        client.create_feedback(
            run_id=run_id,
            key="user-rating",
            score=rating / 5.0,  # Normalize to 0-1
            value=str(rating),
            comment=f"User rated {rating}/5 stars",
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send LangSmith rating: {e}")
        return False


async def run_auto_evaluators(run_id: str, user_message: str, ai_response: str, language_hint: str = "") -> dict:
    """Run automatic quality evaluators on an AI response."""
    if not is_langsmith_enabled() or not run_id:
        return {}

    results = {}
    try:
        from langsmith import Client
        client = Client()

        resp_lower = ai_response.lower()
        user_lower = user_message.lower()
        word_count = len(ai_response.split())

        # 1. Conciseness — under 150 words is ideal, under 200 is ok
        concise_score = 1.0 if word_count <= 150 else (0.7 if word_count <= 200 else 0.3)
        client.create_feedback(
            run_id=run_id,
            key="auto-conciseness",
            score=concise_score,
            value=f"{word_count} words",
            comment=f"{'Concise' if word_count <= 150 else 'Verbose'} ({word_count} words)",
        )
        results["conciseness"] = concise_score

        # 2. Hallucination — check for fabricated data patterns
        hallucination_patterns = [
            "xxxxx", "#00000", "example.com", "placeholder", "lorem ipsum",
            "[number]", "[url]", "order #xxxxx",
        ]
        has_hallucination = any(p in resp_lower for p in hallucination_patterns)
        client.create_feedback(
            run_id=run_id,
            key="auto-hallucination-check",
            score=0.0 if has_hallucination else 1.0,
            value="flagged" if has_hallucination else "clean",
        )
        results["hallucination_free"] = not has_hallucination

        # 3. Language consistency
        german_words = ["ich", "ihr", "mein", "bestellung", "möchte", "bitte", "danke", "gerne", "helfen"]
        english_words = ["my", "order", "please", "thank", "help", "want", "need", "would"]
        de_score = sum(1 for w in german_words if f" {w} " in f" {user_lower} ")
        en_score = sum(1 for w in english_words if f" {w} " in f" {user_lower} ")
        user_is_german = de_score > en_score

        resp_de = sum(1 for w in german_words if f" {w} " in f" {resp_lower} ")
        resp_en = sum(1 for w in english_words if f" {w} " in f" {resp_lower} ")
        resp_is_german = resp_de > resp_en

        # Skip language check for very short messages (greetings etc.)
        if len(user_message.split()) < 3:
            lang_match = True
        else:
            lang_match = user_is_german == resp_is_german

        client.create_feedback(
            run_id=run_id,
            key="auto-language-match",
            score=1.0 if lang_match else 0.0,
            value="matched" if lang_match else "mismatch",
        )
        results["language_match"] = lang_match

        # 4. Identity — only check on first responses (short history = greeting expected)
        # Don't penalize follow-up messages that don't say "Groot"
        is_likely_greeting = len(user_message.split()) <= 5 and not any(
            w in user_lower for w in ["order", "track", "return", "battery", "product"]
        )
        if is_likely_greeting:
            identity_ok = "groot" in resp_lower
            client.create_feedback(
                run_id=run_id,
                key="auto-identity-check",
                score=1.0 if identity_ok else 0.3,
                value="ok" if identity_ok else "missing-in-greeting",
            )
        else:
            # Follow-up: always pass — no need to say Groot every time
            identity_ok = True
            client.create_feedback(
                run_id=run_id,
                key="auto-identity-check",
                score=1.0,
                value="ok-followup",
            )
        results["identity_ok"] = identity_ok

    except Exception as e:
        logger.error(f"Auto-evaluators failed: {e}")

    return results
