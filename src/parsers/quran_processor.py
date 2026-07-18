"""Quran corpus parser."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, List, Mapping

from langchain_core.documents import Document
from langchain_text_splitters import SentenceTransformersTokenTextSplitter

from core.config import logger
from parsers.base import BaseProcessor


VERSE_KEY = re.compile(r"^(?P<surah>\d+):(?P<ayah>\d+)$")


class QuranProcessor(BaseProcessor):
    """Convert the bundled compact Quran JSON into token-safe documents."""

    def __init__(self, file_path: Path, surah_names_path: Path | None = None):
        super().__init__(file_path)
        self.surah_names_path = (
            Path(surah_names_path) if surah_names_path else self._default_names_path()
        )

    def _default_names_path(self) -> Path:
        # <data>/quran/english/file.json -> <data>/quran/metadata/surah.json
        try:
            return self.file_path.parents[1] / "metadata" / "surah.json"
        except IndexError:
            return self.file_path.parent / "surah_names.json"

    def _load_surah_names(self) -> dict[str, str]:
        try:
            value = json.loads(self.surah_names_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load Surah names from %s: %s", self.surah_names_path, exc)
            return {}
        if not isinstance(value, dict):
            logger.warning("Surah names must be a JSON object: %s", self.surah_names_path)
            return {}

        names: dict[str, str] = {}
        for number, metadata in value.items():
            if isinstance(metadata, str):
                names[str(number)] = metadata
            elif isinstance(metadata, Mapping):
                name = metadata.get("name_simple") or metadata.get("name")
                if isinstance(name, str) and name.strip():
                    names[str(number)] = name.strip()
        return names

    @staticmethod
    def _compact_verses(data: Any) -> Mapping[str, Any]:
        if not isinstance(data, dict):
            return {}
        # Current release format: {"1:1": {"t": "..."}, ...}
        if data and all(isinstance(key, str) and VERSE_KEY.match(key) for key in data):
            return data
        # Compatibility with the older upstream envelope.
        nested = data.get("quran", {}).get("en.sahih", {})
        return nested if isinstance(nested, dict) else {}

    def to_chunks(self, verse_splitter: SentenceTransformersTokenTextSplitter) -> List[Document]:
        logger.info("Processing Quran dataset: %s", self.file_path.name)
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to read %s: %s", self.file_path, exc)
            return []

        verses = self._compact_verses(data)
        surah_names = self._load_surah_names()
        documents: list[Document] = []

        for json_key, verse_data in verses.items():
            if not isinstance(verse_data, dict):
                continue
            key_match = VERSE_KEY.match(str(json_key))
            if key_match:
                surah_number = int(key_match.group("surah"))
                ayah_number = int(key_match.group("ayah"))
            else:
                try:
                    surah_number = int(verse_data["surah"])
                    ayah_number = int(verse_data.get("ayah", json_key))
                except (KeyError, TypeError, ValueError):
                    continue

            text = verse_data.get("t") or verse_data.get("verse") or ""
            if not isinstance(text, str) or not text.strip():
                continue

            documents.append(
                Document(
                    page_content=text.strip(),
                    metadata={
                        "surah_number": surah_number,
                        "ayah_number": ayah_number,
                        "surah_name": surah_names.get(str(surah_number), ""),
                        "type": "quran",
                        "source_id": f"quran/english/{self.file_path.name}",
                        "json_key": str(json_key),
                    },
                )
            )

        if not documents:
            logger.warning("No valid verse found to embed in %s", self.file_path.name)
            return []

        logger.info("Chunking %s verses for %s", len(documents), self.file_path.name)
        return verse_splitter.split_documents(documents)
