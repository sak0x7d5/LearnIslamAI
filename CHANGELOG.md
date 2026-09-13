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
- Structured, path-free Quran/Hadith tool records with deterministic references.
- Safe green Quran and blue Hadith quotation cards with trusted collection,
  locator, and grading footers when the excerpt matches a current search result.
- A compact per-answer search activity that groups repeated and mixed retrieval calls.
- Normal partial quotations no longer depend on brittle machine-only citation markers;
  missing or invalid display references never reject an answer.
- Open-source project documentation, contribution policy, security policy,
  conduct policy, third-party notices, and a Windows CI definition.

### Changed

- Mutable models, indexes, history, and update state now live under
  `%LOCALAPPDATA%\IslamAI` by default.
- Gemini defaults to the stable `gemini-3.1-flash-lite` model and graph creation
  is deferred until a validated API key is available.
- Repeated search tool calls render as ordered entries inside one collapsed,
  correctly parented activity step above the final answer.
- The Windows launcher now accepts an already-correct default-port origin
  allowlist while still generating exact origins for custom ports.
- Source-card CSS is carried by the trusted `AnswerView` component and mirrored
  in a versioned global stylesheet, so either cached asset can be stale safely.

### Fixed

- Corpus manifest hashes are now computed from the canonical LF bytes Git stores,
  and `.gitattributes` exempts `src/data/` from end-of-line conversion. Previously
  eleven hashes matched only a Windows checkout with `core.autocrlf=true`, and the
  Surah-name lookup matched only an LF checkout, so first-run corpus validation
  failed on every platform. Corpus version `2026.09.13.1` (release sequence 2)
  carries the corrected manifest; the corpus bytes are unchanged.

### Security

- Disabled raw HTML, arbitrary uploads, wildcard origins, and full
  chain-of-thought display.
- Source-card styling and classes are owned by an allowlisted React component;
  Gemini cannot supply executable HTML, CSS classes, URLs, or trusted footer text.
- Kept the server loopback-bound and API secrets out of session and database
  metadata.

### Known publication blocker

- Redistribution rights for the underlying bundled English Quran and Hadith
  translations remain unresolved. The project must not be publicly released
  until the corpus rights gate in `THIRD_PARTY_NOTICES.md` is closed.
