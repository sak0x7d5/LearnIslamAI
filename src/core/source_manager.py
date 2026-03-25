import json
from pathlib import Path
from typing import Any, Dict, Optional
from functools import lru_cache
from core.config import logger

class SourceManager:
    """
    Manages loading of source JSON files to provide full-text
    content for search results (hydration) using direct index lookup.
    """
    def __init__(self):
        pass

    @staticmethod
    @lru_cache(maxsize=10)
    def _read_json(file_path: str) -> Optional[Dict[str, Any]]:
        """
        Reads and parses a JSON file, caching recent reads to avoid 
        repeated disk I/O for consecutive queries to the same file.
        Uses path string to be hashable for lru_cache.
        """
        path = Path(file_path)
        logger.info(f"Loading source file: {path.name} (Direct JSON Read)")
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read {path.name}: {e}")
            return None

    def get_full_text(self, metadata: Dict[str, Any]) -> Optional[str]:
        """
        Resolves the full text from the source JSON based on document metadata directly
        using the stored indices.
        """
        source_path = metadata.get("source_file")
        if not source_path:
            logger.warning('No source path found in metadata')
            return None

        # we use string for lru_cache compatibility
        if not Path(source_path).exists():
            logger.warning('Source path does not exist')
            return None

        data = self._read_json(str(source_path))
        if not data:
            return None

        m_type = metadata.get("type")

        try:
            if m_type == "hadith":
                idx = metadata.get("array_index")
                if idx is not None and "hadiths" in data:
                    return data["hadiths"][idx]["text"]

            elif m_type == "quran":
                jkey = metadata.get("json_key")
                if jkey is not None:
                    verses_list = data if isinstance(data, list) else data.get("quran", {}).get("en.sahih", {})
                    if isinstance(verses_list, dict) and jkey in verses_list:
                        return verses_list[jkey].get("verse", "")
        except (IndexError, KeyError, TypeError) as e:
            logger.error(f"Error accessing direct value in {Path(source_path).name}: {e}")
        
        return None
