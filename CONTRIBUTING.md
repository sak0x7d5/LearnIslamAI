# Contributing to IslamAI

Thank you for helping make IslamAI safer and more useful. v0.1 is deliberately
narrow: Windows, English sources, localhost, CPU retrieval, and hosted
generation through one configured provider. Discuss broad scope changes before implementing them.

## Before opening a change

- Search existing issues and keep each change focused on one problem.
- Never include API keys, `.env`, chat databases, model caches, or generated
  indexes.
- For user-visible behavior, describe the expected result and how it was
  verified.
- For religious-source corrections, provide the edition, stable source,
  locator, provenance, and redistribution permission. Do not paste or upload an
  entire copyrighted edition in an issue or pull request.

## Development setup

Use Windows and Python 3.12 for the v0.1 support target:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_windows.ps1 -Dev
```

The bootstrap uses its pinned managed `uv` executable without adding it to
`PATH`.

Run the quality gate before submitting:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check src tests
```

Do not update `uv.lock` incidentally. If dependencies must change, explain why,
regenerate the lock deliberately, and verify that CUDA packages, `faiss-gpu`,
`torchvision`, and `torchaudio` were not introduced.

## Change guidelines

- Keep retrieval and citation output grounded in the bundled sources.
- Treat model output as untrusted text; do not add raw HTML rendering.
- Keep every tool invocation as an independent top-level UI step.
- Preserve loopback-only defaults and avoid persisting secrets in logs,
  sessions, browser storage, or databases.
- Add regression tests for bug fixes and failure paths.
- Keep mutable state under `ISLAMAI_HOME`, not in tracked source directories.

## Corpus contributions

Corpus content is not covered automatically by the project's MIT License. Each
asset must have all of the following before it can be bundled:

1. A stable upstream URL and immutable revision.
2. SHA-256, raw record count, and indexable text-bearing record count.
3. Exact edition/translator or compiler attribution.
4. A documented redistribution basis that applies to the underlying text, not
   merely to an API wrapper or repository.
5. Schema and retrieval tests.

Unclear rights block inclusion. Do not silently replace or rewrite sacred-text
translations to work around the gate.

## Pull requests

Keep commits reviewable and the worktree clean. In the pull request, summarize
the user impact, list verification commands and results, identify privacy or
security effects, and disclose any third-party material. By contributing
project-authored code or documentation, you agree that it may be distributed
under the MIT License.

All participants must follow the [Code of Conduct](CODE_OF_CONDUCT.md). Report
security issues using [SECURITY.md](SECURITY.md), not a public issue.
