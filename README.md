# IslamAI

IslamAI is a local-first Quran and Hadith research assistant. It searches a
local English corpus, sends the question and selected source excerpts to a
hosted generation provider, and presents an answer with citations. Google
Gemini and OpenRouter are supported.

> [!WARNING]
> This is a pre-release v0.1 foundation with no tagged release. The source code
> is MIT-licensed, but redistribution rights for the bundled English
> translations are still being documented, so treat the bundled corpus as
> review-pending rather than cleared. See
> [Third-party notices](THIRD_PARTY_NOTICES.md).

IslamAI is an aid for finding source passages. It is **not a fatwa authority**,
does not replace qualified scholars, and can produce incomplete or incorrect
answers. Verify citations in a trusted edition and consult qualified scholarship
for religious rulings or consequential decisions.

## v0.1 scope

- Windows 10/11, Python 3.12, and a reproducible `uv.lock` environment
- Single-user access on `127.0.0.1`; it is not a hosted or multi-user service
- English-only corpus: 6,236 Quran verses and 36,512 source records across ten
  Hadith collections; 36,097 Hadith records contain retrievable text
- CPU-only SentenceTransformers embeddings and CPU FAISS search
- Hosted generation through Google Gemini (default `gemini-3.1-flash-lite`)
  or OpenRouter, which also reaches OpenAI and any OpenAI-compatible endpoint
- One compact, expandable search-activity row per answer, including repeated
  Quran and Hadith searches without nested tool cards
- Application-rendered Quran and Hadith quotation cards with trusted source
  footers when a retrieved record can be matched
- Local indexes, model cache, update state, and chat history under
  `%LOCALAPPDATA%\IslamAI` by default

GPU acceleration, ONNX embeddings, local generation models, multilingual
corpora, Linux/macOS packaging, and hosted authentication are intentionally out
of scope for v0.1.

## Requirements

- 64-bit Windows 10 or Windows 11
- Internet access for initial installation, the first embedding-model download,
  approved corpus updates, and generated answers
- An API key for one supported provider: a Google API key with access to the
  configured Gemini model, or an OpenRouter key and a tool-capable model
- Enough free disk space for Python, CPU PyTorch, dependencies, the embedding
  model, and generated indexes

You do not need to install Python or `uv` manually. The Windows bootstrap pins
`uv` 0.11.29 and installs managed Python 3.12 when needed.

## Install and run

Clone or download this repository, then use either method from the repository
root.

### Simplest method

Double-click `start_windows.bat`, or run:

```powershell
.\start_windows.bat
```

### PowerShell method

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_windows.ps1 -Launch
```

The launcher installs the locked end-user environment and opens IslamAI at
<http://127.0.0.1:8000>. If that port is occupied by another local application,
the launcher moves to the next free port and prints the address it chose. To
pin a specific port instead, pass `-Port`; an explicitly requested port that is
busy fails rather than being silently replaced. Either way the launcher
generates an exact loopback-only origin allowlist for that process, without a
wildcard:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_windows.ps1 -Launch -Port 8123
```

On first use, IslamAI validates the bundled corpus, downloads the BGE embedding
model if it is not cached, and builds local indexes while showing progress. A
missing API key is requested as a password and saved only to the ignored root
`.env` file after server-side validation.

To install without launching:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_windows.ps1
```

The installer is repeatable. It replaces an incompatible project `.venv`
instead of depending on a stale interpreter.

## Configuration

The UI normally collects the API key. For manual configuration, copy the
example and edit the ignored `.env` file:

```powershell
Copy-Item .env.example .env
```

| Variable | Purpose | Default |
| --- | --- | --- |
| `ISLAMAI_LLM_PROVIDER` | `google` or `openrouter` | Detected from the key that is set |
| `GOOGLE_API_KEY` | Google API key used for Gemini requests | Requested on first use |
| `GEMINI_MODEL` | Gemini model name | `gemini-3.1-flash-lite` |
| `OPENROUTER_API_KEY` | OpenRouter API key | Requested on first use |
| `OPENROUTER_MODEL` | OpenRouter model id; **must support tool calling** | `meta-llama/llama-3.3-70b-instruct:free` |
| `OPENROUTER_BASE_URL` | OpenAI-compatible endpoint; HTTPS only | `https://openrouter.ai/api/v1` |
| `ISLAMAI_HOME` | Absolute application data root; set in the process environment before starting | `%LOCALAPPDATA%\IslamAI` |
| `ISLAMAI_CORPUS_MANIFEST_URL` | Optional HTTPS corpus release-manifest endpoint | Update checks disabled |

`CHAINLIT_AUTH_SECRET` is generated locally when absent. Do not commit `.env` or
share its contents in logs or issue reports.

### Choosing a provider

Leave `ISLAMAI_LLM_PROVIDER` blank and IslamAI uses whichever key is configured.
If both are set, Google is used. If neither is set, IslamAI asks for an
OpenRouter key. Both keys can coexist in `.env`; switching providers erases
neither.

IslamAI answers by calling Quran and Hadith search tools, so **the model must
support tool calling**. A model that cannot is rejected when the key is
validated, rather than silently answering without citing any source. Free
OpenRouter models come and go, so list the current tool-capable ones with:

```bash
curl -s https://openrouter.ai/api/v1/models \
  | jq -r '.data[] | select(.id|endswith(":free"))
           | select(.supported_parameters|index("tools")) | .id'
```

Do not set `OPENROUTER_MODEL` to `openrouter/auto`: it can route to a model
without tool support. A cheap paid model is the stable choice.

`OPENROUTER_BASE_URL` accepts any OpenAI-compatible endpoint, so pointing it at
`https://api.openai.com/v1` with an OpenAI key uses OpenAI directly.

`ISLAMAI_HOME` is needed by the bootstrap before `.env` is loaded. To relocate
the managed runtime and application data, set it in PowerShell before launching:

```powershell
$env:ISLAMAI_HOME = "D:\IslamAI"
.\start_windows.bat
```

The value must be an absolute directory and cannot be a drive root.

## Data, updates, and privacy

The bundled release corpus contains:

- Quran: filename-labeled Sahih International English translation, 6,236 verses
- Hadith: Sunan Abu Dawud, Sahih al-Bukhari, Forty Hadith of Shah Waliullah
  Dehlawi, Sunan Ibn Majah, Muwatta Malik, Sahih Muslim, Sunan an-Nasai, Forty
  Hadith of an-Nawawi, Forty Hadith Qudsi, and Jami at-Tirmidhi

The pinned upstream Hadith files contain 415 blank-text records. IslamAI preserves
those source files and counts them in the 36,512-record corpus total, but does not
embed empty text; 36,097 Hadith records are text-bearing and searchable. The
manifest records both totals so this omission is explicit rather than silently
rewriting sacred-source data.

Corpus files, embeddings, FAISS indexes, and chat history remain local. The
first model load contacts Hugging Face unless the model is already cached.
When you ask a question, the question and retrieved source excerpts are sent to
the configured generation provider. How far they travel depends on which one:

- **Google Gemini** — one hop. The question and excerpts go to Google, handled
  under the terms and data practices of your account and API service.
- **OpenRouter** — two hops. They go to OpenRouter, and on to whichever upstream
  model provider OpenRouter routes the request to. That upstream is a party you
  did not choose directly, and free (`:free`) models commonly carry terms
  permitting training on submitted data. Read a model's terms on its OpenRouter
  page before selecting it. OpenRouter offers account-level data-policy
  controls; IslamAI does not set them for you.

If that second hop is not acceptable for the sources you are researching, use
Gemini, or point `OPENROUTER_BASE_URL` at a provider you have a direct
agreement with.

Corpus update checks are disabled unless `ISLAMAI_CORPUS_MANIFEST_URL` points to
an HTTPS release-manifest endpoint. When configured, IslamAI prompts before any
check and asks at most once per day. Choosing **Later**, allowing the prompt to
time out, or leaving the endpoint unset makes no corpus-update network request.
Accepted updates are downloaded to staging, validated, indexed, and activated
atomically; the previous valid corpus/index remains available for rollback.
Generated answers still require network access.

Default local paths:

```text
%LOCALAPPDATA%\IslamAI\
  cache\
  corpus\
  models\
  runtime_files\
  state\
  tools\
  vector_indices\
  chat_history.db
```

Set `ISLAMAI_HOME` before launching to relocate the managed tools and mutable
IslamAI data. The project `.venv` remains in the repository checkout.

## Troubleshooting

- **PowerShell blocks the script:** use the `powershell -NoProfile
  -ExecutionPolicy Bypass -File ...` command above. It changes policy only for
  that process.
- **A previous `.venv` points to a removed Python:** rerun the installer; it
  detects and replaces incompatible project environments.
- **The first search is slow:** first launch downloads the embedding model and
  builds CPU indexes. Later launches reuse the cache and validated indexes.
- **The provider rejects the key or model:** confirm the key, account access,
  and quota for the provider in use, and that the model name is correct. Never
  paste the key into a public issue.
- **"The model did not return a tool call":** the configured model cannot call
  tools, so it cannot search the corpus. Set `OPENROUTER_MODEL` (or
  `GEMINI_MODEL`) to a tool-capable model.
- **OpenRouter reports no credit:** add credit, or set `OPENROUTER_MODEL` to a
  free model that supports tool calling.
- **The port is already in use:** if it is already IslamAI, open the displayed
  address instead of launching twice. Otherwise choose a free `-Port` value.
- **An update fails:** IslamAI keeps the previous validated corpus and index.
  Include only redacted logs when reporting the failure.

## Development

Install the locked development group through the same pinned bootstrap, then use
the project environment directly (the managed `uv` is intentionally not added to
`PATH`):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_windows.ps1 -Dev
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check src tests
```

The GitHub Actions definition performs the same checks on Windows, verifies that
the environment contains CPU-only PyTorch and excludes GPU/vision/audio extras,
and starts the loopback Chainlit server for a smoke test. The workflow is
prepared locally but will not run until this repository is pushed with explicit
authorization.

See [CONTRIBUTING.md](CONTRIBUTING.md) before proposing a change. Corpus changes
have stricter provenance and rights requirements than code changes.

## Uninstall

1. Stop IslamAI.
2. Delete the repository checkout, including its ignored `.env` and `.venv`.
3. Delete `%LOCALAPPDATA%\IslamAI`, or the directory specified by
   `ISLAMAI_HOME`, to remove models, indexes, history, and update state.

An independently installed system `uv` cache is outside IslamAI's cleanup; the
bootstrap's own cache is under `ISLAMAI_HOME` and is removed in step 3.

## License and data status

IslamAI source code and project-authored documentation are licensed under the
[MIT License](LICENSE). That license does **not** grant rights to third-party
Quran translations, Hadith translations, grading data, model weights, or other
third-party material. Their status is described in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

No public release should be made until every bundled corpus asset has a verified
source, attribution, and redistribution basis recorded in the corpus manifest.
