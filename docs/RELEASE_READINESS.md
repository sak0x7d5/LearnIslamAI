# IslamAI v0.1 release-readiness report

Report date: 2026-07-19; status updated 2026-09-13

Candidate: `main` (the merged `codex/oss-v0.1-foundation` line)

Status: **PUBLIC SOURCE, NO TAGGED RELEASE; CORPUS RIGHTS STILL UNRESOLVED**

This is the evidence ledger for the v0.1 foundation. The repository is public
and `main` is pushed at the owner's direction; this report does not authorize
a version tag or a distributed release.

## Gates

| Gate | Status | Evidence |
| --- | --- | --- |
| Work isolation | Pass | All release work was performed in `C:\tmp\IslamAI-oss-v0.1`; the backup worktree remained untouched |
| Windows locked runtime | Pass | Clean and repeat installs, incompatible-environment replacement, path-with-spaces install, default-port idempotency, and warm launch passed |
| CPU-only dependency policy | Pass | Lock and installed-environment audits contain CPU PyTorch and `faiss-cpu`, with no CUDA runtime, `faiss-gpu`, `torchvision`, or `torchaudio` |
| Corpus integrity | Pass (re-verified 2026-09-13) | Manifest hashes and schemas validate 6,236 Quran verses, 36,512 raw Hadith records, 36,097 text-bearing Hadith records, and 114 Surah names. The 2026-07-19 hashes were computed on a CRLF working copy and did not match Git's canonical bytes; corpus version `2026.09.13.1` records LF hashes and `.gitattributes` prevents end-of-line conversion of `src/data/` |
| Retrieval and attribution | Pass | BGE instruction, 384-dimensional normalized embeddings, token limits, reviewed retrieval queries, path-free records, partial-excerpt matching, and permissive trusted card footers passed |
| Startup/update safety | Pass | Single-flight startup, failed-ingestion retry, decline-without-network, staged validation, atomic activation, failure preservation, and rollback passed |
| Secret and UI safety | Pass | Key validation/non-disclosure, escaped fallback Markdown, self-styled allowlisted React source cards, mixed-cache-compatible versioned CSS, one correctly parented search activity, loopback binding, and hardened Chainlit configuration passed |
| Documentation | Pass (local) | Installation, data, privacy, updates, troubleshooting, testing, cleanup, limitations, disclaimer, governance, and security are documented |
| Corpus redistribution rights | **Blocked** | Permission/license for each exact English translation and third-party grading text is unresolved |
| Public-operation authorization | Push directed by owner (2026-09-13) | Source publication was requested by the owner; tagging a release remains gated on the corpus rights item above |

## Verification record

The subsystem commits preceding this report are:

```text
67bfcaa build: add minimal Windows CPU runtime
20c995a feat: add validated English corpus bootstrap
0f6b01e feat: add grounded citations and safe local UI
be2c7be docs: complete open source readiness foundation
5a889bd fix: keep first-run progress in the active chat
4a7eb1c fix: restore normal grounded answers
6aac4cb fix: preserve Markdown blockquotes safely
69ce8e2 docs: finalize local readiness evidence
e05d2c7 fix: aggregate search activity by chat turn
e1d4e43 feat: render safe Quran and Hadith source cards
0adb0ea docs: record safe source-card readiness
```

The documentation commit is the commit containing this report. The ignored
`readiness-report.local.md` records the final candidate hash and the last complete
verification run.

Validated foundation evidence:

```text
uv: 0.11.29
Python: 3.12.13
locked install: pass; 189 installed packages are dependency-compatible
PyTorch: 2.11.0+cpu; torch.version.cuda is None; torch.cuda.is_available() is false
FAISS: 1.13.2 CPU; no forbidden GPU, vision, or audio distributions
LangGraph compatibility: langgraph-prebuilt 1.0.8 import pass
Ruff: check pass; 39 Python files formatted
pytest: 93 passed
application import: pass with lazy graph and API-key construction
launcher: default-port and custom-port origin generation; HTTP 200; IslamAI title; 127.0.0.1-only listener; clean shutdown
Windows bootstrap: clean, repeat, broken-.venv recovery, and path-with-spaces cases pass
corpus: Quran 6,236; Hadith 36,512 raw / 36,097 text-bearing; Surah names 114
full local index: 43,814 chunks; 384 dimensions; normalized vector norm 1.0
token audit: maximum persisted chunk 389 tokens against the 512-token model limit
reviewed retrieval: Quran 24:35, Quran 2:256, and Sahih al-Bukhari 1 returned at rank 1
warm offline bootstrap: 0 sources reprocessed; 11 sources reused
live answer UI: two Hadith searches grouped in one step above the answer; redundant component/global Hadith and Quran card styles, card copy, and full reload persistence passed
```

The original mandatory `[[cite:...]]` answer-marker gate was removed after live
testing because it rejected useful answers solely for formatting differences.
Gemini may now wrap a direct partial quotation in a compact Quran or Hadith tag
with an optional retrieved reference. The answer is always retained: only a
normalized same-kind current-run excerpt match adds trusted collection, locator, and
grading metadata. Missing, malformed, ambiguous, or mismatched references simply
omit that footer. All other model HTML remains escaped, and users must still
verify citations in a trusted edition as documented in the README.

The full matrix must be repeated after the documentation commit. Any later
failure invalidates the technical-candidate status until it is repaired and the
report is updated.

## Current publication blockers

1. The Sahih International-labeled Quran file has no recorded source edition,
   upstream URL, or redistribution grant.
2. The ten English Hadith files trace to an API repository licensed under the
   Unlicense, which does not establish rights to the underlying translations;
   translator/publisher terms are unresolved. (The upstream ref `1` was pinned
   to commit `df57907be352` on 2026-09-13 and all ten files verified
   byte-for-byte, so the provenance half of this item is closed.)
3. The Surah-name lookup is marked `review_required`; the source and
   redistribution basis of the project metadata it was adapted from still need
   evidence.
See `THIRD_PARTY_NOTICES.md` for the detailed provenance audit. The source is
public, but no version should be tagged or described as a release until
blockers 1-3 are resolved or the affected assets are removed from the bundle.
