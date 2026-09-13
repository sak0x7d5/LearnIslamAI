from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pytest
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

import core.embedding_manager as embedding_module
from core.coordinator import CorpusProcessingError, RAGCoordinator, SyncReport
from core.corpus_manifest import CorpusManifest, CorpusManifestError, validate_corpus
from core.embedding_manager import EmbeddingManager
from core.knowledge_base import (
    CorpusReleaseManager,
    KnowledgeBaseService,
    UpdateStatus,
)
from core.manifest_tracker import ManifestTracker
from parsers.quran_processor import QuranProcessor


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "src" / "data"
CORPUS_MANIFEST = DATA_ROOT / "corpus-manifest.json"


class IdentitySplitter:
    def split_documents(self, documents):
        return documents


def test_bundled_english_corpus_matches_immutable_manifest():
    manifest = CorpusManifest.load(CORPUS_MANIFEST)
    validate_corpus(DATA_ROOT, manifest)

    assert manifest.schema_version == 1
    assert len(manifest.assets_of_kind("quran")) == 1
    assert len(manifest.assets_of_kind("hadith")) == 10
    assert len(manifest.assets_of_kind("surah_names")) == 1
    assert sum(asset.record_count for asset in manifest.assets_of_kind("quran")) == 6_236
    assert sum(asset.record_count for asset in manifest.assets_of_kind("hadith")) == 36_512
    assert (
        sum(asset.indexable_record_count for asset in manifest.assets_of_kind("hadith")) == 36_097
    )
    assert manifest.assets_of_kind("surah_names")[0].record_count == 114
    assert manifest.has_unresolved_rights is True

    assert sorted(path.name for path in (DATA_ROOT / "hadith").iterdir()) == ["english"]
    assert sorted(path.name for path in (DATA_ROOT / "quran").iterdir()) == ["english", "metadata"]


def test_corpus_assets_are_exempt_from_line_ending_conversion():
    """Hash-verified assets must reach every checkout byte-for-byte.

    Git for Windows defaults to core.autocrlf=true, which rewrites LF to CRLF on
    checkout and breaks the SHA-256 validation of pretty-printed assets such as
    the Surah-name lookup.
    """

    attributes = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
    rules = [line.split() for line in attributes if line.strip() and not line.startswith("#")]
    assert ["src/data/**", "-text"] in rules

    manifest = CorpusManifest.load(CORPUS_MANIFEST)
    for asset in manifest.assets:
        assert bytes([13]) not in (DATA_ROOT / asset.path).read_bytes(), asset.path


def test_quran_processor_reads_compact_schema_and_surah_names(tmp_path):
    quran_dir = tmp_path / "quran" / "english"
    metadata_dir = tmp_path / "quran" / "metadata"
    quran_dir.mkdir(parents=True)
    metadata_dir.mkdir(parents=True)
    source = quran_dir / "translation.json"
    source.write_text(
        json.dumps({"1:1": {"t": "First verse"}, "2:255": {"t": "Ayat al-Kursi"}}),
        encoding="utf-8",
    )
    (metadata_dir / "surah.json").write_text(
        json.dumps({"1": {"name": "Al-Fatihah"}, "2": {"name": "Al-Baqarah"}}),
        encoding="utf-8",
    )

    documents = QuranProcessor(source).to_chunks(IdentitySplitter())

    assert [doc.page_content for doc in documents] == ["First verse", "Ayat al-Kursi"]
    assert documents[0].metadata["surah_number"] == 1
    assert documents[0].metadata["ayah_number"] == 1
    assert documents[0].metadata["surah_name"] == "Al-Fatihah"
    assert documents[1].metadata["json_key"] == "2:255"
    assert documents[1].metadata["source_id"] == "quran/english/translation.json"


@pytest.mark.parametrize("payload", [{}, [], {"1:1": {"t": ""}}, {"bad": {"t": "text"}}])
def test_quran_processor_rejects_empty_or_malformed_sources(tmp_path, payload):
    source = tmp_path / "quran.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    assert QuranProcessor(source).to_chunks(IdentitySplitter()) == []


def test_processing_state_requires_positive_documents(tmp_path):
    source_root = tmp_path / "corpus"
    source_root.mkdir()
    source = source_root / "source.json"
    source.write_text("{}", encoding="utf-8")
    tracker = ManifestTracker(tmp_path / "state.json", source_root=source_root)

    with pytest.raises(ValueError, match="producing documents"):
        tracker.mark_processed(source, 0)
    assert tracker.is_processed(source) is False

    tracker.mark_processed(source, 1)
    assert tracker.is_processed(source) is True
    source.write_text('{"changed": true}', encoding="utf-8")
    assert tracker.is_processed(source) is False


def test_embedding_fingerprint_covers_index_compatibility_settings(tmp_path):
    first = EmbeddingManager(cache_dir=tmp_path / "cache-one").get_index_fingerprint()
    same = EmbeddingManager(cache_dir=tmp_path / "cache-two").get_index_fingerprint()
    changed = EmbeddingManager(
        cache_dir=tmp_path / "cache-three", splitter_chunk_size=256
    ).get_index_fingerprint()

    assert first == same
    assert first["model_id"] == "BAAI/bge-small-en-v1.5"
    assert first["model_revision"] == "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
    assert first["dimension"] == 384
    assert first["normalize_embeddings"] is True
    assert first["query_instruction"]
    assert len(first["digest"]) == 64
    assert first["digest"] != changed["digest"]


def test_splitter_uses_pinned_model_and_token_safe_configuration(tmp_path, monkeypatch):
    captured = {}

    class CapturingSplitter:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        embedding_module, "SentenceTransformersTokenTextSplitter", CapturingSplitter
    )
    manager = EmbeddingManager(cache_dir=tmp_path / "cache")

    manager.get_text_splitter()

    assert captured["model_name"] == manager.model_name
    assert captured["tokens_per_chunk"] == 384
    assert captured["chunk_overlap"] == 32
    assert captured["model_kwargs"]["revision"] == manager.model_revision
    assert captured["model_kwargs"]["device"] == "cpu"
    assert captured["model_kwargs"]["cache_folder"] == str(tmp_path / "cache")


class FakeEmbeddingManager:
    def get_index_fingerprint(self):
        return {"digest": "test"}

    def get_text_splitter(self):
        return IdentitySplitter()


class FakeStore:
    def __init__(self, index_path: Path):
        self.index_path = str(index_path)
        self.documents = []

    def clear_index(self):
        self.documents.clear()

    def add_documents(self, documents):
        self.documents.extend(documents)
        index = Path(self.index_path)
        index.mkdir(parents=True, exist_ok=True)
        (index / "marker").write_text("built", encoding="utf-8")


def test_coordinator_does_not_mark_empty_source_successful(tmp_path):
    quran_dir = tmp_path / "data" / "quran" / "english"
    hadith_dir = tmp_path / "data" / "hadith" / "english"
    quran_dir.mkdir(parents=True)
    hadith_dir.mkdir(parents=True)
    empty_quran = quran_dir / "empty.json"
    empty_quran.write_text("{}", encoding="utf-8")
    hadith_source = hadith_dir / "one.json"
    hadith_source.write_text(
        json.dumps(
            {
                "metadata": {"name": "Test", "sections": {"1": "Section"}},
                "hadiths": [{"text": "A narration", "hadithnumber": 1, "reference": {"book": 1}}],
            }
        ),
        encoding="utf-8",
    )
    tracker = ManifestTracker(tmp_path / "runtime.json", source_root=tmp_path / "data")
    coordinator = RAGCoordinator(
        embedding_manager=FakeEmbeddingManager(),
        manifest_tracker=tracker,
        stores={
            "quran": FakeStore(tmp_path / "indexes" / "quran"),
            "hadith": FakeStore(tmp_path / "indexes" / "hadith"),
        },
        quran_dir=quran_dir,
        hadith_dir=hadith_dir,
    )

    with pytest.raises(CorpusProcessingError) as error:
        coordinator.sync_documents()

    assert empty_quran.as_posix() in error.value.report.failed_files
    assert tracker.is_processed(empty_quran) is False
    assert tracker.is_processed(hadith_source) is True

    empty_quran.write_text(json.dumps({"1:1": {"t": "A valid verse"}}), encoding="utf-8")
    retry_report = coordinator.sync_documents()

    assert retry_report.failed_files == ()
    assert tracker.is_processed(empty_quran) is True


class FakeCoordinator:
    def __init__(self):
        self.calls = 0

    def sync_documents(self, progress_callback):
        self.calls += 1
        progress_callback("index_quran", 1, 1, "quran.json")
        time.sleep(0.02)
        return SyncReport(processed_files=1, document_count=1)


@pytest.mark.asyncio
async def test_ensure_ready_is_single_flight(tmp_path):
    release_manager = CorpusReleaseManager(
        bundled_data_dir=DATA_ROOT,
        bundled_manifest_path=CORPUS_MANIFEST,
        bundled_index_dir=tmp_path / "indexes",
        runtime_root=tmp_path / "runtime",
    )
    fake = FakeCoordinator()
    factory_calls = 0

    def factory(_active):
        nonlocal factory_calls
        factory_calls += 1
        return fake

    tracker = ManifestTracker(tmp_path / "state.json", source_root=DATA_ROOT)
    service = KnowledgeBaseService(
        release_manager=release_manager,
        manifest_tracker=tracker,
        coordinator_factory=factory,
    )
    events = []

    await asyncio.gather(*(service.ensure_ready(events.append) for _ in range(8)))

    assert factory_calls == 1
    assert fake.calls == 1
    assert service.coordinator is fake
    assert any(event.phase == "ready" for event in events)


def _asset_bytes() -> dict[str, bytes]:
    assets = {
        "quran/english/quran.json": json.dumps({"1:1": {"t": "Verse"}}).encode(),
        "quran/metadata/surah.json": json.dumps({"1": {"name": "Al-Fatihah"}}).encode(),
    }
    for number in range(10):
        assets[f"hadith/english/book-{number}.json"] = json.dumps(
            {
                "metadata": {"name": f"Book {number}", "sections": {}},
                "hadiths": [{"text": "Narration", "hadithnumber": 1, "reference": {}}],
            }
        ).encode()
    return assets


def _manifest(version: str, assets: dict[str, bytes], *, release_sequence: int = 2) -> dict:
    entries = []
    for path, payload in assets.items():
        value = json.loads(payload)
        if path.startswith("quran/english"):
            kind = "quran"
            record_count = len(value)
            indexable_record_count = len(value)
        elif path.startswith("quran/metadata"):
            kind = "surah_names"
            record_count = len(value)
            indexable_record_count = len(value)
        else:
            kind = "hadith"
            record_count = len(value["hadiths"])
            indexable_record_count = sum(
                1
                for record in value["hadiths"]
                if isinstance(record.get("text"), str) and record["text"].strip()
            )
        entries.append(
            {
                "path": path,
                "kind": kind,
                "language": "en",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "record_count": record_count,
                "indexable_record_count": indexable_record_count,
                "download_url": f"https://example.invalid/{path}",
                "source": {
                    "repository": "https://example.invalid/repository",
                    "revision": version,
                    "attribution": "Test corpus",
                },
                "redistribution": {"status": "verified", "note": "Test fixture"},
            }
        )
    return {
        "schema_version": 1,
        "corpus_version": version,
        "release_sequence": release_sequence,
        "generated_at": "2026-07-18T00:00:00+00:00",
        "language": "en",
        "assets": entries,
    }


def _write_corpus(root: Path, manifest_value: dict, assets: dict[str, bytes]) -> Path:
    root.mkdir(parents=True)
    for relative, payload in assets.items():
        destination = root / Path(*relative.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    manifest_path = root / "corpus-manifest.json"
    manifest_path.write_text(json.dumps(manifest_value), encoding="utf-8")
    return manifest_path


class FakeUpdateClient:
    def __init__(self, manifest_value, assets, *, corrupt_path=None):
        self.manifest_value = manifest_value
        self.assets = assets
        self.corrupt_path = corrupt_path
        self.manifest_calls = 0
        self.asset_calls = 0

    async def fetch_manifest(self):
        self.manifest_calls += 1
        return self.manifest_value

    async def download_asset(self, asset, destination):
        self.asset_calls += 1
        payload = self.assets[asset.path]
        destination.write_bytes(b"corrupt" if asset.path == self.corrupt_path else payload)


async def _marker_index_builder(_data_dir, index_dir, _progress):
    fingerprint = EmbeddingManager(cache_dir=index_dir / "model-cache").get_index_fingerprint()
    source_paths = ["quran/english/quran.json"] + [
        f"hadith/english/book-{number}.json" for number in range(10)
    ]
    embedding_info = {}
    for source_path in source_paths:
        stat = (_data_dir / Path(*source_path.split("/"))).stat()
        embedding_info[source_path] = {
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
            "document_count": 1,
        }
    (index_dir / "processing-state.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "embedding_fingerprint": fingerprint,
                "embedding_info": embedding_info,
            }
        ),
        encoding="utf-8",
    )

    class DeterministicEmbeddings(Embeddings):
        def embed_documents(self, texts):
            return [self.embed_query(text) for text in texts]

        def embed_query(self, text):
            vector = np.zeros(384, dtype=np.float32)
            vector[abs(hash(text)) % 384] = 1.0
            return vector.tolist()

    for kind, vector_count in (("quran", 1), ("hadith", 10)):
        store_dir = index_dir / kind
        documents = [
            Document(page_content=f"{kind} fixture {number}", metadata={"kind": kind})
            for number in range(vector_count)
        ]
        store = FAISS.from_documents(documents, DeterministicEmbeddings())
        store.save_local(str(store_dir))


def _update_service(tmp_path):
    assets = _asset_bytes()
    old_manifest = _manifest("old", assets, release_sequence=1)
    bundled_root = tmp_path / "bundled"
    bundled_manifest = _write_corpus(bundled_root, old_manifest, assets)
    manager = CorpusReleaseManager(
        bundled_data_dir=bundled_root,
        bundled_manifest_path=bundled_manifest,
        bundled_index_dir=tmp_path / "bundled-indexes",
        runtime_root=tmp_path / "runtime",
    )
    tracker = ManifestTracker(tmp_path / "runtime-state.json", source_root=bundled_root)
    return KnowledgeBaseService(release_manager=manager, manifest_tracker=tracker), assets


@pytest.mark.asyncio
async def test_declining_update_performs_no_client_calls(tmp_path):
    service, assets = _update_service(tmp_path)
    client = FakeUpdateClient(_manifest("new", assets), assets)
    now = datetime(2026, 7, 18, tzinfo=timezone.utc)

    result = await service.check_for_updates(
        approved=False,
        client=client,
        index_builder=_marker_index_builder,
        now=now,
    )

    assert result.status is UpdateStatus.DECLINED
    assert client.manifest_calls == 0
    assert client.asset_calls == 0
    assert service.update_prompt_due(now + timedelta(hours=23, minutes=59)) is False
    assert service.update_prompt_due(now + timedelta(hours=24)) is True


@pytest.mark.asyncio
async def test_equal_update_is_reported_up_to_date_without_asset_downloads(tmp_path):
    service, assets = _update_service(tmp_path)
    client = FakeUpdateClient(_manifest("old", assets, release_sequence=1), assets)

    result = await service.check_for_updates(
        approved=True,
        client=client,
        index_builder=_marker_index_builder,
    )

    assert result.status is UpdateStatus.UP_TO_DATE
    assert client.manifest_calls == 1
    assert client.asset_calls == 0


@pytest.mark.asyncio
async def test_downgrade_manifest_is_rejected_without_asset_downloads(tmp_path):
    service, assets = _update_service(tmp_path)
    client = FakeUpdateClient(_manifest("different-old", assets, release_sequence=1), assets)

    with pytest.raises(CorpusManifestError, match="must be newer"):
        await service.check_for_updates(
            approved=True,
            client=client,
            index_builder=_marker_index_builder,
        )

    assert client.asset_calls == 0
    assert service.release_manager.active().version == "old"


@pytest.mark.asyncio
async def test_update_activation_and_rollback_are_atomic(tmp_path):
    service, assets = _update_service(tmp_path)
    client = FakeUpdateClient(_manifest("new", assets), assets)

    result = await service.check_for_updates(
        approved=True,
        client=client,
        index_builder=_marker_index_builder,
    )

    assert result.status is UpdateStatus.INSTALLED
    assert result.active_version == "new"
    assert result.previous_version == "old"
    assert service.release_manager.active().version == "new"
    assert client.asset_calls == 12
    report = await service.ensure_ready()
    assert report.processed_files == 0
    assert report.skipped_files == 11
    assert service.coordinator.manifest_tracker.manifest_path == (
        service.release_manager.active().index_dir / "processing-state.json"
    )
    assert service.rollback_update().version == "old"
    assert service.release_manager.active().bundled is True


@pytest.mark.asyncio
async def test_invalid_update_never_replaces_active_release(tmp_path):
    service, assets = _update_service(tmp_path)
    manifest_value = _manifest("bad", assets)
    corrupt_path = next(iter(assets))
    client = FakeUpdateClient(manifest_value, assets, corrupt_path=corrupt_path)

    with pytest.raises(CorpusManifestError, match="SHA-256 mismatch"):
        await service.check_for_updates(
            approved=True,
            client=client,
            index_builder=_marker_index_builder,
        )

    assert service.release_manager.active().version == "old"
    staging = service.release_manager.staging_dir
    assert not staging.exists() or list(staging.iterdir()) == []


@pytest.mark.asyncio
async def test_partially_malformed_corpus_never_replaces_active_release(tmp_path):
    service, assets = _update_service(tmp_path)
    malformed_path = "hadith/english/book-0.json"
    assets[malformed_path] = json.dumps(
        {
            "metadata": {"name": "Book 0", "sections": {}},
            "hadiths": [{"text": "", "hadithnumber": 1, "reference": {}}],
        }
    ).encode()
    manifest_value = _manifest("malformed", assets)
    next(entry for entry in manifest_value["assets"] if entry["path"] == malformed_path)[
        "indexable_record_count"
    ] = 1
    client = FakeUpdateClient(manifest_value, assets)

    with pytest.raises(CorpusManifestError, match="Indexable-record-count mismatch"):
        await service.check_for_updates(
            approved=True,
            client=client,
            index_builder=_marker_index_builder,
        )

    assert service.release_manager.active().version == "old"


@pytest.mark.asyncio
async def test_incomplete_staged_indexes_never_replace_active_release(tmp_path):
    service, assets = _update_service(tmp_path)
    client = FakeUpdateClient(_manifest("incomplete", assets), assets)

    async def incomplete_builder(_data_dir, index_dir, _progress):
        (index_dir / "quran").mkdir(parents=True)
        (index_dir / "quran" / "index.faiss").write_bytes(b"not-an-index")

    with pytest.raises(CorpusManifestError, match="valid index state"):
        await service.check_for_updates(
            approved=True,
            client=client,
            index_builder=incomplete_builder,
        )

    assert service.release_manager.active().version == "old"


@pytest.mark.asyncio
async def test_mismatched_staged_fingerprint_never_replaces_active_release(tmp_path):
    service, assets = _update_service(tmp_path)
    client = FakeUpdateClient(_manifest("wrong-fingerprint", assets), assets)

    async def wrong_fingerprint_builder(data_dir, index_dir, progress):
        await _marker_index_builder(data_dir, index_dir, progress)
        state_path = index_dir / "processing-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["embedding_fingerprint"]["dimension"] = 768
        state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(CorpusManifestError, match="fingerprint"):
        await service.check_for_updates(
            approved=True,
            client=client,
            index_builder=wrong_fingerprint_builder,
        )

    assert service.release_manager.active().version == "old"


@pytest.mark.asyncio
async def test_partial_staged_index_never_replaces_active_release(tmp_path):
    service, assets = _update_service(tmp_path)
    source_path = "hadith/english/book-0.json"
    assets[source_path] = json.dumps(
        {
            "metadata": {"name": "Book 0", "sections": {}},
            "hadiths": [
                {"text": "Narration one", "hadithnumber": 1, "reference": {}},
                {"text": "Narration two", "hadithnumber": 2, "reference": {}},
            ],
        }
    ).encode()
    client = FakeUpdateClient(_manifest("partial-index", assets), assets)

    with pytest.raises(CorpusManifestError, match="fewer documents"):
        await service.check_for_updates(
            approved=True,
            client=client,
            index_builder=_marker_index_builder,
        )

    assert service.release_manager.active().version == "old"


def test_manifest_rejects_path_traversal():
    assets = _asset_bytes()
    manifest_value = _manifest("unsafe", assets)
    manifest_value["assets"][0]["path"] = "../escape.json"
    with pytest.raises(CorpusManifestError, match="stay inside"):
        CorpusManifest.from_mapping(manifest_value)
