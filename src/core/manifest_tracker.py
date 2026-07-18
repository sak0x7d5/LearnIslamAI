"""Mutable local state for corpus syncing and embedding progress."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
from typing import Any, Dict, Mapping
from uuid import uuid4

from core.config import DATA_DIR, STATE_DIR, logger


RUNTIME_STATE_SCHEMA_VERSION = 2


def default_state_dir() -> Path:
    return STATE_DIR.parent


class ManifestTracker:
    """Track mutable processing and update state outside the source tree."""

    def __init__(self, manifest_path: Path | None = None, source_root: Path | None = None):
        self.manifest_path = Path(manifest_path or (default_state_dir() / "state" / "runtime.json"))
        self.source_root = Path(source_root or DATA_DIR).resolve()
        self._write_lock = threading.RLock()
        self._ensure_manifest()

    def get_default_manifest(self) -> Dict[str, Any]:
        return {
            "schema_version": RUNTIME_STATE_SCHEMA_VERSION,
            "embedding_fingerprint": None,
            "sync_info": {"fetched_at": None, "files": {}},
            "embedding_info": {},
            "update_info": {
                "last_prompted_at": None,
                "last_checked_at": None,
                "active_corpus_version": None,
                "previous_corpus_version": None,
            },
        }

    def _ensure_manifest(self) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            self.save_manifest(self.get_default_manifest())
            return
        data = self.load_manifest()
        default = self.get_default_manifest()
        changed = False
        for key, value in default.items():
            if key not in data:
                data[key] = value
                changed = True
        if data.get("schema_version") != RUNTIME_STATE_SCHEMA_VERSION:
            data["schema_version"] = RUNTIME_STATE_SCHEMA_VERSION
            changed = True
        if changed:
            self.save_manifest(data)

    def load_manifest(self) -> Dict[str, Any]:
        try:
            value = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self.get_default_manifest()
        return value if isinstance(value, dict) else self.get_default_manifest()

    def save_manifest(self, data: Mapping[str, Any]) -> None:
        """Atomically persist state so interruption cannot truncate it."""

        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.manifest_path.with_name(f".{self.manifest_path.name}.{uuid4().hex}.tmp")
        with self._write_lock:
            try:
                with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                    json.dump(data, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.manifest_path)
            finally:
                temporary.unlink(missing_ok=True)

    def _file_key(self, file_path: Path) -> str:
        resolved = Path(file_path).resolve()
        try:
            return resolved.relative_to(self.source_root).as_posix()
        except ValueError:
            # Tests and imported corpora can live outside the bundled root. A stable
            # absolute key is acceptable in local state but never exposed as a citation.
            return resolved.as_posix()

    # Sync metadata retained for compatibility with the downloader.
    def get_sync_info(self) -> Dict[str, Any]:
        return self.load_manifest().get("sync_info", {})

    def is_synced(self, file_name: str, sha: str) -> bool:
        file_info = self.get_sync_info().get("files", {}).get(file_name)
        return bool(file_info and file_info.get("sha") == sha)

    def is_data_fresh(self, hours: float) -> bool:
        fetched_at = self.get_sync_info().get("fetched_at")
        if not fetched_at:
            return False
        try:
            last_sync = datetime.fromisoformat(fetched_at)
            if last_sync.tzinfo is None:
                last_sync = last_sync.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - last_sync).total_seconds() < hours * 3600
        except (TypeError, ValueError) as exc:
            logger.warning("Failed to parse last sync time: %s", exc)
            return False

    def mark_file_synced(self, file_name: str, sha: str) -> None:
        data = self.load_manifest()
        data.setdefault("sync_info", {"fetched_at": None, "files": {}})
        data["sync_info"].setdefault("files", {})[file_name] = {"sha": sha}
        self.save_manifest(data)

    def update_last_sync(self, timestamp: str | None = None) -> None:
        data = self.load_manifest()
        data.setdefault("sync_info", {"fetched_at": None, "files": {}})
        data["sync_info"]["fetched_at"] = timestamp or datetime.now(timezone.utc).isoformat()
        self.save_manifest(data)

    def mark_synced(self, fetched_at: str, files_list: Dict[str, Any]) -> None:
        data = self.load_manifest()
        data["sync_info"] = {"fetched_at": fetched_at, "files": files_list}
        self.save_manifest(data)

    # Embedding/index state.
    def check_and_update_fingerprint(self, fingerprint: Mapping[str, Any]) -> bool:
        data = self.load_manifest()
        stored = data.get("embedding_fingerprint")
        current = dict(fingerprint)
        if stored == current:
            return False
        logger.warning("Embedding/index fingerprint changed; invalidating processing state")
        data["embedding_fingerprint"] = current
        data["embedding_info"] = {}
        self.save_manifest(data)
        return True

    def check_and_update_model(self) -> bool:
        """Compatibility shim for old callers; the coordinator uses full fingerprints."""

        return False

    def is_processed(self, file_path: Path) -> bool:
        path = Path(file_path)
        if not path.is_file():
            return False
        file_info = self.load_manifest().get("embedding_info", {}).get(self._file_key(path))
        if not file_info:
            return False
        stat = path.stat()
        return (
            stat.st_mtime_ns == file_info.get("mtime_ns")
            and stat.st_size == file_info.get("size")
            and int(file_info.get("document_count", 0)) > 0
        )

    def mark_processed(self, file_path: Path, document_count: int | None = None) -> None:
        if document_count is None or document_count <= 0:
            raise ValueError("A source can only be marked processed after producing documents")
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        stat = path.stat()
        data = self.load_manifest()
        data.setdefault("embedding_info", {})[self._file_key(path)] = {
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
            "document_count": int(document_count),
            "embedded_at": datetime.now(timezone.utc).isoformat(),
        }
        self.save_manifest(data)
        logger.info("Marked %s as processed (%s documents)", path.name, document_count)

    def clear_processed(self, file_paths: list[Path] | None = None) -> None:
        data = self.load_manifest()
        if file_paths is None:
            data["embedding_info"] = {}
        else:
            processed = data.setdefault("embedding_info", {})
            for file_path in file_paths:
                processed.pop(self._file_key(file_path), None)
        self.save_manifest(data)

    # Update policy state.
    def update_info(self) -> Dict[str, Any]:
        return self.load_manifest().get("update_info", {})

    def record_update_prompt(self, timestamp: datetime | None = None) -> None:
        data = self.load_manifest()
        info = data.setdefault("update_info", {})
        info["last_prompted_at"] = (timestamp or datetime.now(timezone.utc)).isoformat()
        self.save_manifest(data)

    def record_update_check(self, timestamp: datetime | None = None) -> None:
        data = self.load_manifest()
        info = data.setdefault("update_info", {})
        info["last_checked_at"] = (timestamp or datetime.now(timezone.utc)).isoformat()
        self.save_manifest(data)

    def record_activation(self, active_version: str, previous_version: str | None) -> None:
        data = self.load_manifest()
        info = data.setdefault("update_info", {})
        info["active_corpus_version"] = active_version
        info["previous_corpus_version"] = previous_version
        self.save_manifest(data)
