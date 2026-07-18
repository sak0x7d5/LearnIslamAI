from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.config import APP_HOME, BUNDLED_DATA_DIR, logger


class SourceManager:
    """Hydrate exact source text while constraining reads to corpus directories."""

    def __init__(
        self,
        bundled_data_dir: Path = BUNDLED_DATA_DIR,
        surah_metadata_path: Path | None = None,
        allowed_roots: tuple[Path, ...] | None = None,
    ):
        self.bundled_data_dir = Path(bundled_data_dir).resolve()
        self.surah_metadata_path = Path(
            surah_metadata_path or (self.bundled_data_dir / "quran" / "metadata" / "surah.json")
        )
        roots = allowed_roots or (
            self.bundled_data_dir,
            (APP_HOME / "corpus").resolve(),
        )
        self.allowed_roots = tuple(Path(root).resolve() for root in roots)

    @staticmethod
    @lru_cache(maxsize=16)
    def _read_json(file_path: str) -> Any | None:
        path = Path(file_path)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to read corpus source %s: %s", path.name, exc)
            return None

    def _resolve_source(self, source_value: str) -> Path | None:
        candidate = Path(source_value)
        if not candidate.is_absolute():
            candidate = self.bundled_data_dir / candidate
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            return None
        if not any(resolved == root or root in resolved.parents for root in self.allowed_roots):
            logger.warning("Rejected corpus source outside allowed roots: %s", resolved.name)
            return None
        return resolved

    @lru_cache(maxsize=1)
    def _surah_names(self) -> dict[str, str]:
        data = self._read_json(str(self.surah_metadata_path.resolve()))
        if not isinstance(data, dict):
            return {}
        names: dict[str, str] = {}
        for key, value in data.items():
            if isinstance(value, str):
                names[str(key)] = value
            elif isinstance(value, dict):
                name = value.get("name_simple") or value.get("name") or value.get("englishName")
                if isinstance(name, str):
                    names[str(key)] = name
        return names

    def get_full_text(self, metadata: dict[str, Any]) -> str | None:
        # Stable corpus-relative IDs survive staging-directory promotion. Absolute
        # source_file is retained only as a legacy fallback for old local indexes.
        source_path = None
        for source_value in (metadata.get("source_id"), metadata.get("source_file")):
            if isinstance(source_value, str) and source_value:
                source_path = self._resolve_source(source_value)
                if source_path is not None:
                    break
        if source_path is None:
            return None
        data = self._read_json(str(source_path))
        if data is None:
            return None

        try:
            if metadata.get("type") == "hadith":
                index = metadata.get("array_index")
                if isinstance(index, int) and isinstance(data, dict):
                    text = data["hadiths"][index]["text"]
                    return text if isinstance(text, str) and text.strip() else None

            if metadata.get("type") == "quran":
                key = metadata.get("json_key") or metadata.get("jkey")
                if key is None:
                    return None
                key = str(key)
                verses = data
                if isinstance(data, dict) and "quran" in data:
                    verses = data.get("quran", {}).get("en.sahih", {})
                if not isinstance(verses, dict) or key not in verses:
                    return None
                verse = verses[key]
                if not isinstance(verse, dict):
                    return None
                text = verse.get("t") or verse.get("verse")
                surah = str(metadata.get("surah_number") or key.split(":", 1)[0])
                if not metadata.get("surah_name"):
                    metadata["surah_name"] = self._surah_names().get(surah, "")
                return text if isinstance(text, str) and text.strip() else None
        except (IndexError, KeyError, TypeError):
            return None
        return None
