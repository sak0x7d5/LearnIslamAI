# Changelog

All notable changes to IslamAI will be documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project intends to use [Semantic Versioning](https://semver.org/) after its
first public release.

## [Unreleased]

### Added

- Reproducible Windows bootstrap using pinned `uv`, Python 3.12, CPU PyTorch,
  SentenceTransformers, and CPU FAISS.
- Validated English corpus manifest, first-run indexing progress, staged updates,
  atomic activation, and rollback support.
- Structured, path-free Quran/Hadith tool records and safe Markdown source attribution.
- Normal partial quotations no longer depend on brittle machine-only citation markers.
- Open-source project documentation, contribution policy, security policy,
  conduct policy, third-party notices, and a Windows CI definition.

### Changed

- Mutable models, indexes, history, and update state now live under
  `%LOCALAPPDATA%\IslamAI` by default.
- Gemini defaults to the stable `gemini-3.1-flash-lite` model and graph creation
  is deferred until a validated API key is available.
- Repeated search tool calls render as independent top-level steps.

### Security

- Disabled raw HTML, arbitrary uploads, wildcard origins, and full
  chain-of-thought display.
- Kept the server loopback-bound and API secrets out of session and database
  metadata.

### Known publication blocker

- Redistribution rights for the underlying bundled English Quran and Hadith
  translations remain unresolved. The project must not be publicly released
  until the corpus rights gate in `THIRD_PARTY_NOTICES.md` is closed.
