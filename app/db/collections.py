from app.db.mongodb import get_db


def sessions_collection():
    return get_db()["chat_sessions"]


def messages_collection():
    return get_db()["chat_messages"]


def knowledge_sources_collection():
    return get_db()["knowledge_sources"]


def knowledge_vectors_collection():
    return get_db()["knowledge_vectors"]


def analytics_events_collection():
    return get_db()["analytics_events"]


def qa_pairs_collection():
    return get_db()["qa_pairs"]


def admin_config_collection():
    return get_db()["admin_config"]


def logs_collection():
    return get_db()["logs"]
