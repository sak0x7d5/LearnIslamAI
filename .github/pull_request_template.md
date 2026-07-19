## Summary

Describe the user-visible outcome and why the change is needed.

## Verification

- [ ] `uv sync --locked --group dev --python 3.12`
- [ ] `uv run --no-sync pytest`
- [ ] `uv run --no-sync ruff check src tests`
- [ ] Relevant Windows launch or UI behavior checked

List any additional tests and their results.

## Safety and scope

- [ ] The change remains within the documented v0.1 scope, or the scope change
      was discussed first.
- [ ] No secret, `.env`, chat history, model cache, or generated index is included.
- [ ] Privacy, network, citation, and failure-mode effects are described.
- [ ] New model-rendered content is escaped; no raw HTML path was added.
- [ ] Dependency changes do not add CUDA, `faiss-gpu`, `torchvision`, or
      `torchaudio`.
- [ ] Any corpus content has immutable provenance, attribution, hashes, counts,
      and a verified redistribution basis.

## Third-party material

List third-party code, text, data, models, or assets and their licenses. Write
`None` if this change adds none.
