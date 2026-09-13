# IslamAI v0.1 release-readiness report

Report date: 2026-07-19

Candidate: `codex/oss-v0.1-foundation`

Status: **TECHNICAL RELEASE CANDIDATE; NOT READY FOR PUBLICATION**

This is the local evidence ledger for the v0.1 foundation. It does not authorize
a push, tag, public repository, or release.

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
| Public-operation authorization | **Blocked by policy** | Push, tag, publication, and remote changes were not requested or performed |

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
   translator/publisher terms and the immutable commit behind upstream ref `1`
   are unresolved.
3. The Surah-name lookup is marked `review_required`; the source and
   redistribution basis of the project metadata it was adapted from still need
   evidence.
4. Public Git activity is outside the authorization for this foundation run.

See `THIRD_PARTY_NOTICES.md` for the detailed provenance audit. The codebase may
be treated as a local technical release candidate, but it must not be described
or distributed as publication-ready until blockers 1-3 are resolved.
