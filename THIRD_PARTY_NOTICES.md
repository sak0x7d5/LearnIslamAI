# Third-party notices and corpus provenance

Last audited: 2026-09-13 (provenance pin); rights review unchanged since 2026-07-18

The MIT License in `LICENSE` applies to IslamAI's project-authored source code
and documentation. It does not relicense third-party religious texts,
translations, grading data, model weights, packages, or hosted services.

## Publication status

**The bundled corpus is not cleared for public redistribution.** The facts below
identify where the current files appear to have come from, but they do not prove
that every upstream contributor had authority to relicense each underlying
translation. This is a release blocker, not a claim that redistribution is
either permitted or prohibited.

The current `src/data/corpus-manifest.json` deliberately marks all 12 bundled
assets `review_required`: one English Quran translation, ten English Hadith
editions, and one Surah-name lookup.

Before a public release, obtain and record a redistribution basis for each exact
edition from the translator, publisher, rights holder, or an authoritative
license statement. Record the evidence and immutable source revision in
`src/data/corpus-manifest.json`. If rights remain unclear, exclude the asset
from the release; do not silently alter or substitute its wording.

## English Quran translation

| Local asset | Label in filename | Records | Recorded upstream source | Status |
| --- | --- | ---: | --- | --- |
| `src/data/quran/english/en-sahih-international-simple.json` | Sahih International, simple | 6,236 | None in the imported file, original repository history, or legacy manifest | **Blocked: source edition and redistribution permission unresolved** |

The filename identifies the translation as Sahih International, but the file
contains only verse keys and text. It does not include translator, publisher,
source URL, revision, attribution terms, or a license. Do not infer permission
from the availability of similar text in unrelated Quran APIs.

## English Hadith editions

The legacy downloader and manifest trace the following files to the versioned
`1` API of [fawazahmed0/hadith-api](https://github.com/fawazahmed0/hadith-api/tree/1).
That upstream repository publishes its repository under [the
Unlicense](https://github.com/fawazahmed0/hadith-api/blob/1/LICENSE) and lists
several external organizations and websites in its [references
file](https://github.com/fawazahmed0/hadith-api/blob/1/References.md).

| Local asset | Collection label in file | Records | Versioned upstream asset |
| --- | --- | ---: | --- |
| `eng-abudawud.json` | Sunan Abu Dawud | 5,274 | [source](https://raw.githubusercontent.com/fawazahmed0/hadith-api/df57907be35291c91ad6a6691180e22ca9920784/editions/eng-abudawud.json) |
| `eng-bukhari.json` | Sahih al Bukhari | 7,589 | [source](https://raw.githubusercontent.com/fawazahmed0/hadith-api/df57907be35291c91ad6a6691180e22ca9920784/editions/eng-bukhari.json) |
| `eng-dehlawi.json` | Forty Hadith of Shah Waliullah Dehlawi | 40 | [source](https://raw.githubusercontent.com/fawazahmed0/hadith-api/df57907be35291c91ad6a6691180e22ca9920784/editions/eng-dehlawi.json) |
| `eng-ibnmajah.json` | Sunan Ibn Majah | 4,343 | [source](https://raw.githubusercontent.com/fawazahmed0/hadith-api/df57907be35291c91ad6a6691180e22ca9920784/editions/eng-ibnmajah.json) |
| `eng-malik.json` | Muwatta Malik | 1,858 | [source](https://raw.githubusercontent.com/fawazahmed0/hadith-api/df57907be35291c91ad6a6691180e22ca9920784/editions/eng-malik.json) |
| `eng-muslim.json` | Sahih Muslim | 7,563 | [source](https://raw.githubusercontent.com/fawazahmed0/hadith-api/df57907be35291c91ad6a6691180e22ca9920784/editions/eng-muslim.json) |
| `eng-nasai.json` | Sunan an Nasai | 5,765 | [source](https://raw.githubusercontent.com/fawazahmed0/hadith-api/df57907be35291c91ad6a6691180e22ca9920784/editions/eng-nasai.json) |
| `eng-nawawi.json` | Forty Hadith of an-Nawawi | 42 | [source](https://raw.githubusercontent.com/fawazahmed0/hadith-api/df57907be35291c91ad6a6691180e22ca9920784/editions/eng-nawawi.json) |
| `eng-qudsi.json` | Forty Hadith Qudsi | 40 | [source](https://raw.githubusercontent.com/fawazahmed0/hadith-api/df57907be35291c91ad6a6691180e22ca9920784/editions/eng-qudsi.json) |
| `eng-tirmidhi.json` | Jami At Tirmidhi | 3,998 | [source](https://raw.githubusercontent.com/fawazahmed0/hadith-api/df57907be35291c91ad6a6691180e22ca9920784/editions/eng-tirmidhi.json) |

Total: 36,512 source records. Of these, 36,097 contain nonblank text and are
indexable; 415 upstream blank-text records are retained byte-for-byte in the
audited source files but are not embedded.

The upstream Unlicense is relevant to material authored by that repository's
contributors. The local edition files do not identify English translators or
publishers in their embedded metadata. The upstream edition catalog partially
fills that gap: it lists Muhsin Khan for `eng-bukhari`, Abdul Hamid Siddiqui for
`eng-muslim`, Shah Waliullah Dehlawi for `eng-dehlawi`, and Imam Nawawi for
`eng-nawawi`; the other six author fields are `Unknown`. The latter two names
identify the source collections' compilers rather than an English translator.
All ten catalog `source` fields are blank.

Neither the catalog nor the general references file maps every English edition
to a translator, publisher, authoritative source, and text-specific license.
Even the two named English translations have no redistribution grant recorded
there. Consequently, rights to the underlying English translations and any
third-party grading text remain **unresolved for every listed edition**.
Upstream reference `1` was resolved on 2026-09-13 to commit
`df57907be35291c91ad6a6691180e22ca9920784`, and every bundled English edition
was verified byte-for-byte against the `editions/` files at that commit; the
table links above point at that revision, and `src/data/corpus-manifest.json`
records it as each edition's source revision. Provenance is therefore fixed to
an immutable upstream state; the rights questions above remain open.

## Surah-name lookup

`src/data/quran/metadata/surah.json` is a 114-entry display lookup. The bundled
manifest describes it as simplified chapter names adapted from existing project
metadata and marks it `review_required`. The original metadata's provenance and
redistribution basis still require evidence before public release.

## Models, packages, and services

- [`BAAI/bge-small-en-v1.5`](https://huggingface.co/BAAI/bge-small-en-v1.5) is
  downloaded at runtime and is not bundled in the repository. Its model card
  and license govern use of the model weights.
- Python packages are resolved by `uv.lock` and retain their respective
  licenses. Installing them does not make them part of IslamAI's MIT-licensed
  source.
- Google Gemini is a hosted third-party service. Users supply their own API key,
  and use is governed by Google's applicable terms and data practices.

This notice is a provenance audit, not legal advice.
