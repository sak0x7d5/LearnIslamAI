"""Single-flight corpus bootstrap and opt-in update activation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import inspect
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any, Awaitable, Callable, Mapping, Protocol
import urllib.request
from uuid import uuid4

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from core.config import (
    APP_HOME,
    CORPUS_MANIFEST_PATH,
    DATA_DIR,
    DEFAULT_CACHE_DIR,
    DEFAULT_INDEX_DIR,
)
from core.coordinator import RAGCoordinator, SyncReport
from core.corpus_manifest import CorpusAsset, CorpusManifest, CorpusManifestError, validate_corpus
from core.embedding_manager import EmbeddingManager
from core.manifest_tracker import ManifestTracker
from core.vector_store import VectorStoreManager


@dataclass(frozen=True)
class ProgressEvent:
    phase: str
    current_item: int
    total_items: int
    detail: str = ""


ProgressHandler = Callable[[ProgressEvent], Awaitable[None] | None]
IndexBuilder = Callable[[Path, Path, ProgressHandler | None], Awaitable[None] | None]


class CorpusUpdateClient(Protocol):
    async def fetch_manifest(self) -> Mapping[str, Any]: ...

    async def download_asset(self, asset: CorpusAsset, destination: Path) -> None: ...


class HttpCorpusUpdateClient:
    """Small HTTPS client used only after the user approves an update check."""

    def __init__(
        self,
        manifest_url: str,
        *,
        timeout_seconds: float = 30,
        max_manifest_bytes: int = 1024 * 1024,
        max_asset_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        if not manifest_url.startswith("https://"):
            raise ValueError("Corpus manifest URL must use HTTPS")
        self.manifest_url = manifest_url
        self.timeout_seconds = timeout_seconds
        self.max_manifest_bytes = max_manifest_bytes
        self.max_asset_bytes = max_asset_bytes

    @staticmethod
    def _request(url: str) -> urllib.request.Request:
        return urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "IslamAI/0.1 corpus-updater"},
        )

    def _fetch_manifest_sync(self) -> Mapping[str, Any]:
        with urllib.request.urlopen(
            self._request(self.manifest_url), timeout=self.timeout_seconds
        ) as response:
            if not response.geturl().startswith("https://"):
                raise CorpusManifestError("Corpus manifest redirect must remain on HTTPS")
            payload = response.read(self.max_manifest_bytes + 1)
        if len(payload) > self.max_manifest_bytes:
            raise CorpusManifestError("Corpus manifest exceeds the download limit")
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CorpusManifestError(f"Downloaded corpus manifest is invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise CorpusManifestError("Downloaded corpus manifest must be an object")
        return value

    async def fetch_manifest(self) -> Mapping[str, Any]:
        return await asyncio.to_thread(self._fetch_manifest_sync)

    def _download_asset_sync(self, asset: CorpusAsset, destination: Path) -> None:
        if not asset.download_url:
            raise CorpusManifestError(f"Update asset has no download_url: {asset.path}")
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.part")
        bytes_written = 0
        try:
            with (
                urllib.request.urlopen(
                    self._request(asset.download_url), timeout=self.timeout_seconds
                ) as response,
                temporary.open("wb") as handle,
            ):
                if not response.geturl().startswith("https://"):
                    raise CorpusManifestError(f"Asset redirect must remain on HTTPS: {asset.path}")
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    bytes_written += len(block)
                    if bytes_written > self.max_asset_bytes:
                        raise CorpusManifestError(f"Asset exceeds the download limit: {asset.path}")
                    handle.write(block)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    async def download_asset(self, asset: CorpusAsset, destination: Path) -> None:
        await asyncio.to_thread(self._download_asset_sync, asset, destination)


class UpdateStatus(str, Enum):
    DECLINED = "declined"
    UP_TO_DATE = "up_to_date"
    INSTALLED = "installed"


@dataclass(frozen=True)
class UpdateResult:
    status: UpdateStatus
    active_version: str
    previous_version: str | None = None


@dataclass(frozen=True)
class ActiveCorpus:
    version: str
    data_dir: Path
    manifest_path: Path
    index_dir: Path
    bundled: bool


class _IndexValidationEmbeddings(Embeddings):
    """Non-network placeholder used only while loading locally built index metadata."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("Index validation must not embed documents")

    def embed_query(self, text: str) -> list[float]:
        raise RuntimeError("Index validation must not embed queries")


class CorpusReleaseManager:
    """Manage validated corpus releases with an atomic active pointer."""

    _SAFE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

    def __init__(
        self,
        *,
        bundled_data_dir: Path = DATA_DIR,
        bundled_manifest_path: Path = CORPUS_MANIFEST_PATH,
        bundled_index_dir: Path = DEFAULT_INDEX_DIR,
        runtime_root: Path = APP_HOME,
    ) -> None:
        self.bundled_data_dir = Path(bundled_data_dir)
        self.bundled_manifest_path = Path(bundled_manifest_path)
        self.bundled_index_dir = Path(bundled_index_dir)
        self.runtime_root = Path(runtime_root)
        self.releases_dir = self.runtime_root / "corpus" / "versions"
        self.staging_dir = self.runtime_root / "corpus" / "staging"
        self.pointer_path = self.runtime_root / "state" / "active-corpus.json"

    def _load_pointer(self) -> dict[str, str | None]:
        try:
            value = json.loads(self.pointer_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"active": None, "previous": None}
        if not isinstance(value, dict):
            return {"active": None, "previous": None}
        return {"active": value.get("active"), "previous": value.get("previous")}

    def _write_pointer(self, *, active: str, previous: str | None) -> None:
        self.pointer_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.pointer_path.with_name(f".{self.pointer_path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump({"active": active, "previous": previous}, handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.pointer_path)
        finally:
            temporary.unlink(missing_ok=True)

    def bundled(self) -> ActiveCorpus:
        manifest = CorpusManifest.load(self.bundled_manifest_path)
        return ActiveCorpus(
            version=manifest.corpus_version,
            data_dir=self.bundled_data_dir,
            manifest_path=self.bundled_manifest_path,
            index_dir=self.bundled_index_dir,
            bundled=True,
        )

    def active(self) -> ActiveCorpus:
        pointer = self._load_pointer()
        version = pointer.get("active")
        if not version:
            return self.bundled()
        release_dir = self.releases_dir / str(version)
        manifest_path = release_dir / "corpus-manifest.json"
        if not release_dir.is_dir() or not manifest_path.is_file():
            raise CorpusManifestError(f"Active corpus release is incomplete: {version}")
        return ActiveCorpus(
            version=str(version),
            data_dir=release_dir / "data",
            manifest_path=manifest_path,
            index_dir=release_dir / "indices",
            bundled=False,
        )

    def new_stage(self, version: str) -> Path:
        if not self._SAFE_VERSION.fullmatch(version):
            raise CorpusManifestError(f"Unsafe corpus version: {version!r}")
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        stage = self.staging_dir / f"{version}-{uuid4().hex}"
        stage.mkdir()
        return stage

    def validate_stage(self, stage: Path, manifest: CorpusManifest) -> None:
        self._assert_stage(stage)
        validate_corpus(Path(stage) / "data", manifest)
        index_dir = Path(stage) / "indices"
        state_path = index_dir / "processing-state.json"
        try:
            processing_state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CorpusManifestError("Staged update has no valid index state") from exc

        expected_fingerprint = EmbeddingManager(cache_dir=DEFAULT_CACHE_DIR).get_index_fingerprint()
        if processing_state.get("embedding_fingerprint") != expected_fingerprint:
            raise CorpusManifestError("Staged index fingerprint does not match this runtime")

        embedding_info = processing_state.get("embedding_info")
        if not isinstance(embedding_info, dict):
            raise CorpusManifestError("Staged index state has no processed sources")

        expected_documents: dict[str, int] = {"quran": 0, "hadith": 0}
        for asset in manifest.assets:
            if asset.kind not in expected_documents:
                continue
            source_state = embedding_info.get(asset.path)
            if not isinstance(source_state, dict):
                raise CorpusManifestError(f"Staged index omitted source: {asset.path}")
            try:
                document_count = int(source_state["document_count"])
            except (KeyError, TypeError, ValueError) as exc:
                raise CorpusManifestError(
                    f"Staged index has invalid source state: {asset.path}"
                ) from exc
            if document_count <= 0:
                raise CorpusManifestError(f"Staged index has no documents for: {asset.path}")
            if document_count < asset.indexable_record_count:
                raise CorpusManifestError(
                    f"Staged index contains fewer documents than indexable records for: "
                    f"{asset.path}"
                )
            expected_documents[asset.kind] += document_count

        expected_dimension = int(expected_fingerprint["dimension"])
        for kind, expected_count in expected_documents.items():
            store_dir = index_dir / kind
            faiss_path = store_dir / "index.faiss"
            metadata_path = store_dir / "index.pkl"
            if not faiss_path.is_file() or not metadata_path.is_file():
                raise CorpusManifestError(f"Staged {kind} index is incomplete")
            try:
                store = FAISS.load_local(
                    str(store_dir),
                    _IndexValidationEmbeddings(),
                    allow_dangerous_deserialization=True,
                )
            except Exception as exc:
                raise CorpusManifestError(f"Staged {kind} FAISS store is unreadable") from exc
            index = store.index
            if index.d != expected_dimension:
                raise CorpusManifestError(
                    f"Staged {kind} index dimension is {index.d}; expected {expected_dimension}"
                )
            if not index.is_trained or index.ntotal != expected_count:
                raise CorpusManifestError(
                    f"Staged {kind} index contains {index.ntotal} vectors; "
                    f"expected {expected_count}"
                )
            mapping = store.index_to_docstore_id
            if set(mapping) != set(range(expected_count)):
                raise CorpusManifestError(f"Staged {kind} index mapping is incomplete")
            if any(
                not isinstance(store.docstore.search(identifier), Document)
                for identifier in mapping.values()
            ):
                raise CorpusManifestError(f"Staged {kind} document store is incomplete")

    def activate(self, stage: Path, manifest: CorpusManifest) -> ActiveCorpus:
        stage = self._assert_stage(stage)
        self.validate_stage(stage, manifest)
        self.releases_dir.mkdir(parents=True, exist_ok=True)
        destination = self.releases_dir / manifest.corpus_version
        if destination.exists():
            raise CorpusManifestError(f"Corpus release already exists: {manifest.corpus_version}")
        previous = self.active().version
        os.replace(stage, destination)
        try:
            self._write_pointer(active=manifest.corpus_version, previous=previous)
        except Exception:
            # The old pointer remains valid; retain the built release for diagnosis.
            raise
        return self.active()

    def rollback(self) -> ActiveCorpus:
        pointer = self._load_pointer()
        previous = pointer.get("previous")
        active = pointer.get("active")
        if not previous:
            return self.bundled()

        bundled = self.bundled()
        if previous == bundled.version:
            # An absent active pointer means "use bundled" and is atomic too.
            self.pointer_path.unlink(missing_ok=True)
            return bundled

        release_dir = self.releases_dir / str(previous)
        if not release_dir.is_dir():
            raise CorpusManifestError(f"Previous corpus release is unavailable: {previous}")
        self._write_pointer(active=str(previous), previous=str(active) if active else None)
        return self.active()

    def discard_stage(self, stage: Path) -> None:
        stage = self._assert_stage(stage)
        if stage.exists():
            shutil.rmtree(stage)

    def _assert_stage(self, stage: Path) -> Path:
        resolved = Path(stage).resolve()
        staging_root = self.staging_dir.resolve()
        try:
            relative = resolved.relative_to(staging_root)
        except ValueError as exc:
            raise ValueError(f"Refusing operation outside staging: {resolved}") from exc
        if len(relative.parts) != 1:
            raise ValueError(f"Stage must be an immediate child of staging: {resolved}")
        return resolved


async def build_staged_indexes(
    data_dir: Path,
    index_dir: Path,
    progress: ProgressHandler | None = None,
) -> None:
    """Build both FAISS stores inside an update stage, never over active indexes."""

    embeddings = EmbeddingManager(cache_dir=DEFAULT_CACHE_DIR)
    tracker = ManifestTracker(index_dir / "processing-state.json", source_root=data_dir)
    coordinator = RAGCoordinator(
        embedding_manager=embeddings,
        manifest_tracker=tracker,
        stores={
            "quran": VectorStoreManager(embeddings, str(index_dir / "quran")),
            "hadith": VectorStoreManager(embeddings, str(index_dir / "hadith")),
        },
        quran_dir=data_dir / "quran" / "english",
        hadith_dir=data_dir / "hadith" / "english",
    )
    loop = asyncio.get_running_loop()

    def relay(phase: str, current: int, total: int, detail: str) -> None:
        if progress is None:
            return
        event = ProgressEvent(phase, current, total, detail)

        async def deliver() -> None:
            result = progress(event)
            if inspect.isawaitable(result):
                await result

        asyncio.run_coroutine_threadsafe(deliver(), loop).result()

    await asyncio.to_thread(coordinator.sync_documents, relay)


class KnowledgeBaseService:
    """Validate and initialize the active knowledge base exactly once per process."""

    def __init__(
        self,
        *,
        release_manager: CorpusReleaseManager | None = None,
        manifest_tracker: ManifestTracker | None = None,
        coordinator_factory: Callable[[ActiveCorpus], RAGCoordinator] | None = None,
    ) -> None:
        self.release_manager = release_manager or CorpusReleaseManager()
        self.manifest_tracker = manifest_tracker or ManifestTracker()
        self.coordinator_factory = coordinator_factory or self._default_coordinator
        self._ready_lock = asyncio.Lock()
        self._update_lock = asyncio.Lock()
        self._ready = False
        self._coordinator: RAGCoordinator | None = None
        self._last_report: SyncReport | None = None

    @property
    def coordinator(self) -> RAGCoordinator:
        if self._coordinator is None:
            raise RuntimeError("Knowledge base is not ready; call ensure_ready first")
        return self._coordinator

    def _default_coordinator(self, active: ActiveCorpus) -> RAGCoordinator:
        embeddings = EmbeddingManager()
        stores = {
            "quran": VectorStoreManager(embeddings, str(active.index_dir / "quran")),
            "hadith": VectorStoreManager(embeddings, str(active.index_dir / "hadith")),
        }
        # Updated releases carry the processing state produced alongside their
        # locally built indexes. Reusing it prevents a validated index from being
        # cleared and rebuilt immediately after atomic activation.
        tracker_path = (
            self.manifest_tracker.manifest_path
            if active.bundled
            else active.index_dir / "processing-state.json"
        )
        tracker = ManifestTracker(manifest_path=tracker_path, source_root=active.data_dir)
        return RAGCoordinator(
            embedding_manager=embeddings,
            manifest_tracker=tracker,
            stores=stores,
            quran_dir=active.data_dir / "quran" / "english",
            hadith_dir=active.data_dir / "hadith" / "english",
        )

    async def _emit(self, handler: ProgressHandler | None, event: ProgressEvent) -> None:
        if handler is None:
            return
        result = handler(event)
        if inspect.isawaitable(result):
            await result

    async def ensure_ready(self, progress: ProgressHandler | None = None) -> SyncReport:
        if self._ready and self._last_report is not None:
            return self._last_report
        async with self._ready_lock:
            if self._ready and self._last_report is not None:
                return self._last_report

            active = self.release_manager.active()
            await self._emit(progress, ProgressEvent("validating_corpus", 0, 1, active.version))
            manifest = await asyncio.to_thread(CorpusManifest.load, active.manifest_path)
            await asyncio.to_thread(validate_corpus, active.data_dir, manifest)
            await self._emit(progress, ProgressEvent("validating_corpus", 1, 1, active.version))

            self._coordinator = self.coordinator_factory(active)
            await self._emit(progress, ProgressEvent("loading_embeddings", 0, 1, "Embedding model"))
            loop = asyncio.get_running_loop()

            def relay(phase: str, current: int, total: int, detail: str) -> None:
                future = asyncio.run_coroutine_threadsafe(
                    self._emit(progress, ProgressEvent(phase, current, total, detail)), loop
                )
                future.result()

            report = await asyncio.to_thread(self._coordinator.sync_documents, relay)
            await self._emit(progress, ProgressEvent("ready", 1, 1, active.version))
            self._last_report = report
            self._ready = True
            return report

    def update_prompt_due(self, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        prompted_at = self.manifest_tracker.update_info().get("last_prompted_at")
        if not prompted_at:
            return True
        try:
            previous = datetime.fromisoformat(str(prompted_at))
            if previous.tzinfo is None:
                previous = previous.replace(tzinfo=timezone.utc)
        except ValueError:
            return True
        return current - previous >= timedelta(hours=24)

    async def check_for_updates(
        self,
        *,
        approved: bool,
        client: CorpusUpdateClient,
        index_builder: IndexBuilder,
        progress: ProgressHandler | None = None,
        now: datetime | None = None,
    ) -> UpdateResult:
        """Check only after opt-in, then stage, validate, index, and activate.

        Passing ``approved=False`` records the prompt decision and returns without
        invoking any client method, guaranteeing that "Later" performs no network I/O.
        """

        current_time = now or datetime.now(timezone.utc)
        self.manifest_tracker.record_update_prompt(current_time)
        if not approved:
            active_before = self.release_manager.active()
            return UpdateResult(UpdateStatus.DECLINED, active_before.version)

        async with self._update_lock:
            active_before = self.release_manager.active()
            await self._emit(progress, ProgressEvent("checking_update", 0, 1, "Corpus metadata"))
            manifest_value = await client.fetch_manifest()
            self.manifest_tracker.record_update_check(current_time)
            manifest = CorpusManifest.from_mapping(manifest_value)
            active_manifest = CorpusManifest.load(active_before.manifest_path)
            if (
                manifest.corpus_version == active_before.version
                and manifest.release_sequence == active_manifest.release_sequence
            ):
                await self._emit(progress, ProgressEvent("checking_update", 1, 1, "Up to date"))
                return UpdateResult(UpdateStatus.UP_TO_DATE, active_before.version)
            if manifest.release_sequence <= active_manifest.release_sequence:
                raise CorpusManifestError(
                    "Corpus update release_sequence must be newer than the active corpus"
                )

            stage = self.release_manager.new_stage(manifest.corpus_version)
            try:
                manifest_path = stage / "corpus-manifest.json"
                manifest_path.write_text(
                    json.dumps(manifest_value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                total = len(manifest.assets)
                for current, asset in enumerate(manifest.assets, start=1):
                    await self._emit(
                        progress,
                        ProgressEvent("downloading_corpus", current, total, Path(asset.path).name),
                    )
                    destination = stage / "data" / Path(*asset.path.split("/"))
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    await client.download_asset(asset, destination)

                await asyncio.to_thread(validate_corpus, stage / "data", manifest)
                await self._emit(
                    progress, ProgressEvent("building_indexes", 0, 1, manifest.corpus_version)
                )
                (stage / "indices").mkdir(parents=True, exist_ok=True)
                build_result = index_builder(stage / "data", stage / "indices", progress)
                if inspect.isawaitable(build_result):
                    await build_result
                self.release_manager.validate_stage(stage, manifest)
                active_after = self.release_manager.activate(stage, manifest)
            except BaseException:
                if stage.exists():
                    self.release_manager.discard_stage(stage)
                raise

            self.manifest_tracker.record_activation(active_after.version, active_before.version)
            self._ready = False
            self._coordinator = None
            self._last_report = None
            await self._emit(progress, ProgressEvent("update_ready", 1, 1, active_after.version))
            return UpdateResult(
                UpdateStatus.INSTALLED,
                active_after.version,
                previous_version=active_before.version,
            )

    def rollback_update(self) -> ActiveCorpus:
        active = self.release_manager.rollback()
        self._ready = False
        self._coordinator = None
        self._last_report = None
        return active
