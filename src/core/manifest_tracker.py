import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from core.config import logger, DEFAULT_MANIFEST

class ManifestTracker:
    """
    Reusable class for tracking processed files (e.g., for embedding).
    Keeps track of which books/files in 'data/' have already been completely embedded.
    Prevents duplicate operations on subsequent script initializations.
    """
    def __init__(self, manifest_path: Path | None = None, initial_data: Dict[str, Any] | None = None):
        self.manifest_path = Path(manifest_path or DEFAULT_MANIFEST)
        # We track embedded files in a 'files' dictionary.
        self.initial_data = initial_data or {"files": {}}  
        self._ensure_manifest()

    def _ensure_manifest(self) -> None:
        """
        Ensures that the directory and the manifest.json file exist.
        If the file doesn't exist, it is created with the `initial_data` schema.
        """
        if not self.manifest_path.parent.exists():
            self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            logger.info(f"Creating manifest at {self.manifest_path}")
            self.save_manifest(self.initial_data)

    def load_manifest(self) -> Dict[str, Any]:
        """
        Retrieves the manifest contents from disk.
        """
        try:
            with open(self.manifest_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Manifest load failed ({e}). Re-initializing.")
            self._ensure_manifest()
            return self.initial_data

    def save_manifest(self, data: Dict[str, Any]) -> None:
        """
        Overwrites the manifest.json with updated data.
        """
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def is_processed(self, file_path: Path) -> bool:
        """
        Check if a particular file has already been embedded and remains unchanged.
        Validates exactness using Modification Time (mtime) and file size.
        """
        manifest = self.load_manifest()
        
        # Determine the relative path of the file from the 'data' folder
        try:
            rel_path = str(file_path.relative_to(self.manifest_path.parent))
        except ValueError:
            # Fallback if the file is not inside the data folder
            rel_path = str(file_path.absolute())
            
        file_info = manifest.get("files", {}).get(rel_path)
        
        if not file_info:
            return False

        current_mtime = os.path.getmtime(file_path)
        current_size = os.path.getsize(file_path)

        # Return True only if neither modification time nor file size changes
        return (current_mtime == file_info.get("mtime") and current_size == file_info.get("size"))

    def mark_processed(self, file_path: Path) -> None:
        """
        Updates manifest after successfully embedding the file's text chunks.
        """
        manifest = self.load_manifest()
        
        # Ensure schema structure exists
        if "files" not in manifest:
            manifest["files"] = {}
            
        try:
            rel_path = str(file_path.relative_to(self.manifest_path.parent))
        except ValueError:
            rel_path = str(file_path.absolute())
            
        manifest["files"][rel_path] = {
            "mtime": os.path.getmtime(file_path),
            "size": os.path.getsize(file_path),
            "embedded_at": os.path.getctime(file_path)  # Timestamp record
        }
        self.save_manifest(manifest)
        logger.info(f"Marked {file_path} as processed in manifest.")
