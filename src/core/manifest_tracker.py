import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from core.config import logger, DEFAULT_MANIFEST, DEFAULT_MODEL_NAME

class ManifestTracker:
    """
    Unified class for tracking both synchronization (download) and processing (embedding).
    Keeps track of:
    1. sync_info: GitHub SHAs and download timestamps.
    2. embedding_info: Modification times and embedding timestamps.
    """
    def __init__(self, manifest_path: Path | None = None):
        self.manifest_path = Path(manifest_path or DEFAULT_MANIFEST)
        self._ensure_manifest()

    def _ensure_manifest(self) -> None:
        """
        Ensures that the directory and the manifest.json file exist.
        Migrates old formats if necessary.
        """
        if not self.manifest_path.parent.exists():
            self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        
        if not self.manifest_path.exists():
            logger.info(f"Creating new unified manifest at {self.manifest_path}")
            self.save_manifest(self.get_default_manifest())
        else:
            self._migrate_manifest()

    def get_default_manifest(self) -> Dict[str, Any]:
        return {
            "active_embedding_model": DEFAULT_MODEL_NAME,
            "sync_info": {
                "fetched_at": None,
                "files": {}
            },
            "embedding_info": {}
        }

    def _migrate_manifest(self) -> None:
        """
        Migrates older manifest versions to the unified format.
        """
        try:
            with open(self.manifest_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return

        migrated = False
        
        # Scenario A: Old Embedded Files format (direct "files" key as dict)
        if "files" in data and isinstance(data["files"], dict) and "embedding_info" not in data:
            logger.info("Migrating old embedding manifest to unified format...")
            data["embedding_info"] = data.pop("files")
            migrated = True

        # Scenario B: Old Data Manager format (direct "files" key as list)
        if "files" in data and isinstance(data["files"], list) and "sync_info" not in data:
            logger.info("Migrating old sync manifest to unified format...")
            files_dict = {f["name"]: f for f in data.pop("files")}
            data["sync_info"] = {
                "fetched_at": data.pop("fetched_at", None),
                "files": files_dict
            }
            migrated = True

        # Ensure base structure exists
        if "sync_info" not in data:
            data["sync_info"] = {"fetched_at": None, "files": {}}
            migrated = True
        if "embedding_info" not in data:
            data["embedding_info"] = {}
            migrated = True
        if "active_embedding_model" not in data:
            data["active_embedding_model"] = DEFAULT_MODEL_NAME
            migrated = True

        if migrated:
            self.save_manifest(data)

    def load_manifest(self) -> Dict[str, Any]:
        try:
            with open(self.manifest_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return self.get_default_manifest()

    def save_manifest(self, data: Dict[str, Any]) -> None:
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ─── SYNC METHODS ───────────────────────────────────────────────────────────

    def get_sync_info(self) -> Dict[str, Any]:
        return self.load_manifest().get("sync_info", {})

    def is_synced(self, file_name: str, sha: str) -> bool:
        sync_files = self.get_sync_info().get("files", {})
        file_info = sync_files.get(file_name)
        return file_info and file_info.get("sha") == sha

    def is_data_fresh(self, hours: float) -> bool:
        from datetime import datetime
        try:
            # We explicitly use UTC for all timestamps
            from datetime import timezone
            fetched_at = self.get_sync_info().get("fetched_at")
            if not fetched_at:
                return False
                
            last_sync = datetime.fromisoformat(fetched_at)
            diff = datetime.now(timezone.utc) - last_sync
            return diff.total_seconds() < (hours * 3600)
        except Exception as e:
            logger.warning(f"Failed to parse last sync time: {e}")
            return False

    def mark_file_synced(self, file_name: str, sha: str) -> None:
        manifest = self.load_manifest()
        if "sync_info" not in manifest:
            manifest["sync_info"] = {"fetched_at": None, "files": {}}
        if "files" not in manifest["sync_info"]:
            manifest["sync_info"]["files"] = {}
            
        manifest["sync_info"]["files"][file_name] = {"sha": sha}
        self.save_manifest(manifest)
        
    def update_last_sync(self, timestamp: str | None = None) -> None:
        from datetime import datetime, timezone
        manifest = self.load_manifest()
        if "sync_info" not in manifest:
            manifest["sync_info"] = {"fetched_at": None, "files": {}}
        manifest["sync_info"]["fetched_at"] = timestamp or datetime.now(timezone.utc).isoformat()
        self.save_manifest(manifest)

    def mark_synced(self, fetched_at: str, files_list: Dict[str, Any]) -> None:
        manifest = self.load_manifest()
        manifest["sync_info"] = {
            "fetched_at": fetched_at,
            "files": files_list
        }
        self.save_manifest(manifest)

    # ─── EMBEDDING METHODS ──────────────────────────────────────────────────────

    def check_and_update_model(self) -> bool:
        manifest = self.load_manifest()
        stored_model = manifest.get("active_embedding_model")
        
        if stored_model != DEFAULT_MODEL_NAME:
            logger.warning(f"Embedding model changed. Resetting processing state.")
            manifest["active_embedding_model"] = DEFAULT_MODEL_NAME
            manifest["embedding_info"] = {}
            self.save_manifest(manifest)
            return True
        return False

    def is_processed(self, file_path: Path) -> bool:
        manifest = self.load_manifest()
        
        try:
            rel_path = str(file_path.relative_to(self.manifest_path.parent))
        except ValueError:
            rel_path = str(file_path.absolute())
            
        file_info = manifest.get("embedding_info", {}).get(rel_path)
        
        if not file_info:
            return False

        if not file_path.exists():
            return False

        current_mtime = os.path.getmtime(file_path)
        current_size = os.path.getsize(file_path)

        return (current_mtime == file_info.get("mtime") and current_size == file_info.get("size"))

    def mark_processed(self, file_path: Path) -> None:
        manifest = self.load_manifest()
        
        try:
            rel_path = str(file_path.relative_to(self.manifest_path.parent))
        except ValueError:
            rel_path = str(file_path.absolute())
            
        manifest["embedding_info"][rel_path] = {
            "mtime": os.path.getmtime(file_path),
            "size": os.path.getsize(file_path),
            "embedded_at": os.path.getctime(file_path)
        }
        self.save_manifest(manifest)
        logger.info(f"Marked {file_path.name} as processed in manifest.")
