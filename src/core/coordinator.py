"""Quran and Hadith indexing coordinator."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from core.config import HADITH_ENG_DIR, HADITH_INDEX_PATH, QURAN_ENG_DIR, QURAN_INDEX_PATH, logger
from core.embedding_manager import EmbeddingManager
from core.manifest_tracker import ManifestTracker
from core.vector_store import VectorStoreManager
from parsers.base import BaseProcessor
from parsers.hadith_processor import HadithProcessor
from parsers.quran_processor import QuranProcessor


ProgressCallback = Callable[[str, int, int, str], None]


@dataclass(frozen=True)
class SyncReport:
    processed_files: int = 0
    skipped_files: int = 0
    document_count: int = 0
    failed_files: tuple[str, ...] = field(default_factory=tuple)


class CorpusProcessingError(RuntimeError):
    def __init__(self, report: SyncReport):
        self.report = report
        names = ", ".join(report.failed_files)
        super().__init__(f"Corpus indexing failed for: {names}")


class RAGCoordinator:
    """Tie token-aware embeddings, processing state, and FAISS stores together."""

    def __init__(
        self,
        *,
        embedding_manager: EmbeddingManager | None = None,
        manifest_tracker: ManifestTracker | None = None,
        stores: dict[str, VectorStoreManager] | None = None,
        quran_dir: Path | None = None,
        hadith_dir: Path | None = None,
    ) -> None:
        self.embedding_manager = embedding_manager or EmbeddingManager()
        self.manifest_tracker = manifest_tracker or ManifestTracker()
        self.quran_dir = Path(quran_dir or QURAN_ENG_DIR)
        self.hadith_dir = Path(hadith_dir or HADITH_ENG_DIR)
        self.stores = stores or {
            "quran": VectorStoreManager(self.embedding_manager, index_path=str(QURAN_INDEX_PATH)),
            "hadith": VectorStoreManager(self.embedding_manager, index_path=str(HADITH_INDEX_PATH)),
        }

    def process_data_source(self, processor: BaseProcessor, store: VectorStoreManager) -> int:
        """Index one source and return the number of documents actually added."""

        documents = processor.to_chunks(self.embedding_manager.get_text_splitter())
        if not documents:
            logger.warning(
                "No documents were produced by %s for %s",
                processor.__class__.__name__,
                processor.file_path.name,
            )
            return 0
        logger.info(
            "Adding %s documents from %s to %s",
            len(documents),
            processor.file_path.name,
            store.index_path,
        )
        store.add_documents(documents)
        return len(documents)

    @staticmethod
    def _index_exists(store: VectorStoreManager) -> bool:
        index_path = Path(store.index_path)
        return index_path.is_dir() and any(index_path.iterdir())

    def _groups(self) -> tuple[tuple[str, Path, type[BaseProcessor]], ...]:
        return (
            ("quran", self.quran_dir, QuranProcessor),
            ("hadith", self.hadith_dir, HadithProcessor),
        )

    def sync_documents(self, progress_callback: ProgressCallback | None = None) -> SyncReport:
        """Build each index atomically enough to retry safely after an interruption.

        FAISS cannot replace all chunks from one changed source safely in-place. If any
        source in a store changes, the complete store is rebuilt, preventing duplicates.
        """

        fingerprint_changed = self.manifest_tracker.check_and_update_fingerprint(
            self.embedding_manager.get_index_fingerprint()
        )
        if fingerprint_changed:
            for store in self.stores.values():
                store.clear_index()

        processed = 0
        skipped = 0
        document_count = 0
        failed: list[str] = []

        for kind, source_dir, processor_class in self._groups():
            if not source_dir.is_dir():
                failed.append(source_dir.as_posix())
                continue
            source_files = sorted(path for path in source_dir.glob("*.json") if path.is_file())
            if not source_files:
                failed.append(source_dir.as_posix())
                continue

            store = self.stores[kind]
            requires_rebuild = (
                fingerprint_changed
                or not self._index_exists(store)
                or any(not self.manifest_tracker.is_processed(path) for path in source_files)
            )
            if not requires_rebuild:
                skipped += len(source_files)
                continue

            store.clear_index()
            self.manifest_tracker.clear_processed(source_files)
            total = len(source_files)
            for current, file_path in enumerate(source_files, start=1):
                if progress_callback:
                    progress_callback(f"index_{kind}", current, total, file_path.name)
                try:
                    processor = processor_class(file_path)
                    added = self.process_data_source(processor, store)
                    if added <= 0:
                        failed.append(file_path.as_posix())
                        continue
                    self.manifest_tracker.mark_processed(file_path, added)
                    processed += 1
                    document_count += added
                except Exception as exc:  # one bad edition must not hide the others
                    logger.exception("Failed to index %s: %s", file_path, exc)
                    failed.append(file_path.as_posix())

        report = SyncReport(
            processed_files=processed,
            skipped_files=skipped,
            document_count=document_count,
            failed_files=tuple(failed),
        )
        if failed:
            raise CorpusProcessingError(report)
        logger.info(
            "Sync complete: processed=%s skipped=%s documents=%s",
            processed,
            skipped,
            document_count,
        )
        return report

    def ask(
        self,
        query: str,
        top_k: int = 5,
        filter_type: Literal["quran", "hadith"] | None = None,
    ):
        if filter_type in self.stores:
            return self.stores[filter_type].search(query, top_k=top_k)
        logger.warning("Unknown filter_type %s; defaulting to Quran", filter_type)
        return self.stores["quran"].search(query, top_k=top_k)
