# dVRK Publications Scripts

Utility scripts for maintaining and updating `publications.bib`.

## Setup

```zsh
# Create the virtual environment (once)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r scripts/requirements.txt
```

## Available Scripts

---

### `find_new_papers.py` — Search for new papers

Searches multiple sources for new dVRK / da Vinci Research Kit papers, then
walks you through each result interactively so you can add or reject it.

**Sources searched (in order):**

| Source | API key needed? | Notes |
|---|---|---|
| **CrossRef** | No | Best for published journal/conference papers; uses polite pool |
| **arXiv** | No | Best for preprints and open-access papers |
| **Semantic Scholar** | Optional | Works without a key but heavily rate-limited; set `SEMANTIC_SCHOLAR_API_KEY` for reliable access |
| **IEEE Xplore** | Yes | Set `IEEE_API_KEY` to enable |

**Usage:**

```zsh
# Search a specific year (most common use case)
python3 scripts/find_new_papers.py --start-year 2026 --end-year 2026

# Search a range
python3 scripts/find_new_papers.py --start-year 2024 --end-year 2026

# With optional API keys for broader coverage
SEMANTIC_SCHOLAR_API_KEY=your_key python3 scripts/find_new_papers.py --start-year 2026 --end-year 2026
```

**Interactive prompts:**
- `y` — add to `publications.bib`
- `n` — reject (saved to `rejected_papers.json` so it won't appear again)
- `s` — skip (will appear again next run)
- `q` — quit

**Getting API keys (optional):**
- **Semantic Scholar**: Apply at https://www.semanticscholar.org/product/api#api-key-form  
  Set via `export SEMANTIC_SCHOLAR_API_KEY=your_key` (or add to your shell profile).
- **IEEE Xplore**: Apply at https://developer.ieee.org/  
  Set via `export IEEE_API_KEY=your_key`.

---

### `cleanup_bib.py` — Normalise the bib file

Sorts all entries (by year descending, then title ascending), standardises
field ordering and indentation, renames legacy `dvrk_sites` → `dvrk_site`,
and adds trailing commas. **Run this after any batch add.**

```zsh
python3 scripts/cleanup_bib.py
# or with an explicit path:
python3 scripts/cleanup_bib.py path/to/file.bib
```

---

### `deduplicate_bib.py` — Find and remove duplicate entries

Detects entries that appear more than once (same DOI, near-identical title,
or same author+year+similar title) and walks you through each suspected pair
interactively.

**Detection confidence levels:**

| Level | Criterion | Action suggested |
|---|---|---|
| ⚠️ DOI match | Same DOI after normalisation | Almost certainly a duplicate |
| 🔶 High similarity | Title similarity ≥ 0.92 | Very likely a duplicate |
| 🔷 Moderate similarity | Title similarity ≥ 0.75 | Review carefully |

**Interactive prompts:**
- `1` — keep entry A, discard B
- `2` — keep entry B, discard A
- `m` — **merge**: combine both entries, keeping the best field values from each
- `s` — skip (leave both in the file)
- `q` — quit (saves changes made so far)

A `.dedup-bak` backup is created before any changes are written.

```zsh
# Interactive mode (recommended)
python3 scripts/deduplicate_bib.py

# Report only — no changes written
python3 scripts/deduplicate_bib.py --dry-run

# Lower the similarity threshold to catch more candidates
python3 scripts/deduplicate_bib.py --min-sim 0.70
```


---

### `enrich_metadata.py` — Back-fill missing fields

Walks every entry in `publications.bib` and fetches missing `doi`,
`semanticscholar`, `abstract`, `arxiv`, and `url` fields from Semantic Scholar.
Results are cached in `cache/` to avoid redundant API calls.

```zsh
# Normal run (uses cache, fetches missing data)
python3 scripts/enrich_metadata.py

# Force re-fetch (ignore cache age)
python3 scripts/enrich_metadata.py --days 0

# Re-apply cached data only (no network calls)
python3 scripts/enrich_metadata.py --reprocess
```

> **Note:** This script works best with a `SEMANTIC_SCHOLAR_API_KEY` set.
> Without one, it will be rate-limited and the run may take a very long time.

---

## Recommended workflow

```zsh
# 1. Search for new papers and add them
python3 scripts/find_new_papers.py --start-year 2026 --end-year 2026

# 2. Normalise and sort the file
python3 scripts/cleanup_bib.py

# 3. (Optional) Back-fill any missing metadata
python3 scripts/enrich_metadata.py

# 4. Commit
git add publications.bib rejected_papers.json
git commit -m "Add 2026 dVRK papers"
```
