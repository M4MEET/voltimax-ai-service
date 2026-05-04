from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import get_config


def get_text_splitter() -> RecursiveCharacterTextSplitter:
    config = get_config()
    return RecursiveCharacterTextSplitter(
        chunk_size=config.knowledge_base.chunk_size,
        chunk_overlap=config.knowledge_base.chunk_overlap,
        length_function=len,
    )


def chunk_text(text: str) -> list[str]:
    splitter = get_text_splitter()
    return splitter.split_text(text)
