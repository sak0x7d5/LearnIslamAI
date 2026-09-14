"""Immutable corpus manifest parsing and validation.

The bundled manifest describes files shipped with IslamAI. Mutable processing and
update state belongs under the user's application-data directory instead.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse


CORPUS_MANIFEST_SCHEMA_VERSION = 1
ALLOWED_ASSET_KINDS = {"quran", "hadith", "surah_names"}


class CorpusManifestError(ValueError):
    """Raised when a corpus manifest or one of its declared assets is invalid."""


@dataclass(frozen=True)
class CorpusSource:
    repository: str
    revision: str
    attribution: str


@dataclass(frozen=True)
class RedistributionStatus:
    status: str
    note: str


@dataclass(frozen=True)
class CorpusAsset:
    path: str
    kind: str
    language: str
    sha256: str
    record_count: int
    indexable_record_count: int
    download_url: str | None
    source: CorpusSource
    redistribution: RedistributionStatus

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CorpusAsset":
        try:
            source_value = value["source"]
            rights_value = value["redistribution"]
            asset = cls(
                path=str(value["path"]),
                kind=str(value["kind"]),
                language=str(value["language"]),
                sha256=str(value["sha256"]).lower(),
                record_count=int(value["record_count"]),
                indexable_record_count=int(value["indexable_record_count"]),
                download_url=(str(value["download_url"]) if value.get("download_url") else None),
                source=CorpusSource(
                    repository=str(source_value["repository"]),
                    revision=str(source_value["revision"]),
                    attribution=str(source_value["attribution"]),
                ),
                redistribution=RedistributionStatus(
                    status=str(rights_value["status"]),
                    note=str(rights_value["note"]),
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CorpusManifestError(f"Invalid corpus asset entry: {exc}") from exc

        asset.validate_metadata()
        return asset

    def validate_metadata(self) -> None:
        relative_path = PurePosixPath(self.path)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise CorpusManifestError(f"Asset path must stay inside the corpus: {self.path}")
        if not self.path or "\\" in self.path:
            raise CorpusManifestError(f"Asset path must be non-empty POSIX syntax: {self.path}")
        if self.kind not in ALLOWED_ASSET_KINDS:
            raise CorpusManifestError(f"Unsupported corpus asset kind: {self.kind}")
        if self.language != "en":
            raise CorpusManifestError(f"v0.1 only accepts English assets: {self.path}")
        if len(self.sha256) != 64 or any(c not in "0123456789abcdef" for c in self.sha256):
            raise CorpusManifestError(f"Invalid SHA-256 for {self.path}")
        if self.record_count <= 0:
            raise CorpusManifestError(f"record_count must be positive for {self.path}")
        if not 0 < self.indexable_record_count <= self.record_count:
            raise CorpusManifestError(
                f"indexable_record_count must be positive and no greater than "
                f"record_count for {self.path}"
            )
        if self.download_url and urlparse(self.download_url).scheme != "https":
            raise CorpusManifestError(f"Asset download URL must use HTTPS: {self.path}")
        if not self.source.repository or not self.source.revision or not self.source.attribution:
            raise CorpusManifestError(f"Incomplete source provenance for {self.path}")
        if not self.redistribution.status or not self.redistribution.note:
            raise CorpusManifestError(f"Incomplete redistribution status for {self.path}")


@dataclass(frozen=True)
class CorpusManifest:
    schema_version: int
    corpus_version: str
    release_sequence: int
    generated_at: str
    language: str
    assets: tuple[CorpusAsset, ...]

    @classmethod
    def load(cls, manifest_path: Path) -> "CorpusManifest":
        try:
            value = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CorpusManifestError(f"Could not read corpus manifest: {exc}") from exc
        return cls.from_mapping(value)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CorpusManifest":
        try:
            assets_value = value["assets"]
            manifest = cls(
                schema_version=int(value["schema_version"]),
                corpus_version=str(value["corpus_version"]),
                release_sequence=int(value["release_sequence"]),
                generated_at=str(value["generated_at"]),
                language=str(value["language"]),
                assets=tuple(CorpusAsset.from_mapping(item) for item in assets_value),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CorpusManifestError(f"Invalid corpus manifest: {exc}") from exc
        manifest.validate_metadata()
        return manifest

    def validate_metadata(self) -> None:
        if self.schema_version != CORPUS_MANIFEST_SCHEMA_VERSION:
            raise CorpusManifestError(
                f"Unsupported corpus manifest schema {self.schema_version}; "
                f"expected {CORPUS_MANIFEST_SCHEMA_VERSION}"
            )
        if not self.corpus_version or not self.generated_at:
            raise CorpusManifestError("Corpus version and generation timestamp are required")
        if self.release_sequence <= 0:
            raise CorpusManifestError("Corpus release_sequence must be positive")
        if self.language != "en":
            raise CorpusManifestError("IslamAI v0.1 corpus language must be 'en'")
        if not self.assets:
            raise CorpusManifestError("Corpus manifest must declare at least one asset")

        paths = [asset.path for asset in self.assets]
        if len(paths) != len(set(paths)):
            raise CorpusManifestError("Corpus manifest contains duplicate asset paths")
        kinds = [asset.kind for asset in self.assets]
        if kinds.count("quran") != 1:
            raise CorpusManifestError("Corpus manifest must contain exactly one Quran asset")
        if kinds.count("hadith") != 10:
            raise CorpusManifestError("Corpus manifest must contain exactly ten Hadith assets")
        if kinds.count("surah_names") != 1:
            raise CorpusManifestError("Corpus manifest must contain exactly one Surah-name asset")

    def assets_of_kind(self, kind: str) -> tuple[CorpusAsset, ...]:
        return tuple(asset for asset in self.assets if asset.kind == kind)

    @property
    def has_unresolved_rights(self) -> bool:
        return any(asset.redistribution.status != "verified" for asset in self.assets)


_HASH_BLOCK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of a corpus asset with CRLF line endings normalized to LF.

    Assets are JSON, where a carriage return before a newline is insignificant
    whitespace, so a checkout or editor that converts line endings must not
    invalidate an otherwise identical file. Manifest hashes are recorded over
    the LF form, which is also what Git stores.
    """

    digest = hashlib.sha256()
    pending_cr = False
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(_HASH_BLOCK_SIZE), b""):
            if pending_cr:
                block = b"\r" + block
                pending_cr = False
            if block.endswith(b"\r"):
                # Hold a trailing CR back until we know whether an LF follows it.
                pending_cr = True
                block = block[:-1]
            digest.update(block.replace(b"\r\n", b"\n"))
    if pending_cr:
        digest.update(b"\r")
    return digest.hexdigest()


@dataclass(frozen=True)
class AssetRecordCounts:
    total: int
    indexable: int


QURAN_VERSE_KEY = re.compile(r"^[1-9][0-9]*:[1-9][0-9]*$")


def inspect_asset_records(path: Path, kind: str) -> AssetRecordCounts:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusManifestError(f"Invalid JSON asset {path}: {exc}") from exc

    if kind == "quran":
        if not isinstance(data, dict):
            raise CorpusManifestError(f"Quran asset must be an object: {path}")
        for key, record in data.items():
            if not isinstance(key, str) or not QURAN_VERSE_KEY.fullmatch(key):
                raise CorpusManifestError(f"Invalid Quran verse key {key!r}: {path}")
            if not isinstance(record, dict):
                raise CorpusManifestError(f"Quran verse {key} must be an object: {path}")
            text = record.get("t") or record.get("verse")
            if not isinstance(text, str) or not text.strip():
                raise CorpusManifestError(f"Quran verse {key} has no text: {path}")
        return AssetRecordCounts(len(data), len(data))
    if kind == "hadith":
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("metadata"), dict)
            or not isinstance(data.get("hadiths"), list)
        ):
            raise CorpusManifestError(f"Hadith asset must contain metadata and hadiths: {path}")
        indexable = 0
        for position, record in enumerate(data["hadiths"]):
            if not isinstance(record, dict):
                raise CorpusManifestError(f"Hadith record {position} must be an object: {path}")
            text = record.get("text")
            if not isinstance(text, str):
                raise CorpusManifestError(f"Hadith record {position} has invalid text: {path}")
            if text.strip():
                indexable += 1
        return AssetRecordCounts(len(data["hadiths"]), indexable)
    if kind == "surah_names":
        if not isinstance(data, dict):
            raise CorpusManifestError(f"Surah-name asset must be an object: {path}")
        for number, record in data.items():
            if not isinstance(number, str) or not number.isdigit():
                raise CorpusManifestError(f"Invalid Surah number {number!r}: {path}")
            if isinstance(record, str):
                name = record
            elif isinstance(record, dict):
                name = record.get("name_simple") or record.get("name")
            else:
                name = None
            if not isinstance(name, str) or not name.strip():
                raise CorpusManifestError(f"Surah {number} has no name: {path}")
        return AssetRecordCounts(len(data), len(data))
    raise CorpusManifestError(f"Unsupported corpus asset kind: {kind}")


def count_asset_records(path: Path, kind: str) -> int:
    """Compatibility helper returning the raw record count."""

    return inspect_asset_records(path, kind).total


def validate_corpus(corpus_root: Path, manifest: CorpusManifest) -> None:
    """Validate every declared asset before indexing or activation."""

    root = Path(corpus_root).resolve()
    for asset in manifest.assets:
        path = (root / Path(*PurePosixPath(asset.path).parts)).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise CorpusManifestError(f"Asset escapes corpus root: {asset.path}") from exc
        if not path.is_file():
            raise CorpusManifestError(f"Missing corpus asset: {asset.path}")
        actual_hash = sha256_file(path)
        if actual_hash != asset.sha256:
            raise CorpusManifestError(
                f"SHA-256 mismatch for {asset.path}: expected {asset.sha256}, got {actual_hash}. "
                "The bundled file differs from the corpus manifest; restore it with "
                "`git checkout -- src/data` from the project root or re-download the project."
            )
        counts = inspect_asset_records(path, asset.kind)
        if counts.total != asset.record_count:
            raise CorpusManifestError(
                f"Record-count mismatch for {asset.path}: "
                f"expected {asset.record_count}, got {counts.total}"
            )
        if counts.indexable != asset.indexable_record_count:
            raise CorpusManifestError(
                f"Indexable-record-count mismatch for {asset.path}: "
                f"expected {asset.indexable_record_count}, got {counts.indexable}"
            )


def declared_paths(manifest: CorpusManifest) -> set[str]:
    return {asset.path for asset in manifest.assets}


def total_records(assets: Iterable[CorpusAsset]) -> int:
    return sum(asset.record_count for asset in assets)
