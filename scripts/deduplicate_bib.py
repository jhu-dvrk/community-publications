#!/usr/bin/env python3
"""
Interactively find and remove duplicate entries from publications.bib.

Detection strategies (in order of confidence):
  1. Identical DOI (after normalisation)  — almost certainly the same paper
  2. Title similarity ≥ 0.92              — very likely the same paper
  3. Title similarity ≥ 0.75              — probable duplicate; show for review

For each suspected duplicate you can:
  [1] keep entry A   — discard B
  [2] keep entry B   — discard A
  [m] merge          — combine both, preferring richer field values
  [s] skip           — leave both in the file (not a duplicate)
  [q] quit           — stop reviewing; save any changes made so far

Usage:
    python3 scripts/deduplicate_bib.py
    python3 scripts/deduplicate_bib.py --bib path/to/file.bib
    python3 scripts/deduplicate_bib.py --dry-run   # report only, no writes
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from itertools import combinations

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def normalize_doi(doi: str) -> str:
    doi = doi.lower().strip()
    for prefix in (
        "https://doi.org/", "http://doi.org/",
        "https://dx.doi.org/", "http://dx.doi.org/",
        "doi:",
    ):
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
    return doi


def normalize_title(title: str) -> str:
    """Lowercase, strip LaTeX, remove punctuation, collapse whitespace."""
    # Remove LaTeX commands like \textregistered, {\em ...}, etc.
    title = re.sub(r"\\[a-zA-Z]+(?:\{[^}]*\})?", " ", title)
    title = re.sub(r"\{([^}]*)\}", r"\1", title)  # unwrap plain braces
    title = title.lower()
    title = re.sub(r"[^\w\s]", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def title_similarity(t1: str, t2: str) -> float:
    return SequenceMatcher(None, normalize_title(t1), normalize_title(t2)).ratio()


def entry_doi(entry: dict) -> str | None:
    raw = entry.get("doi", "").strip()
    return normalize_doi(raw) if raw else None


def entry_display_fields(entry: dict) -> list[str]:
    return [k for k in entry if k not in ("ENTRYTYPE", "ID")]


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def find_duplicates(
    entries: list[dict],
    min_doi_title_sim: float = 0.50,
) -> tuple[list[tuple[dict, dict, str, float]], dict[str, list[dict]]]:
    """
    Return (pairs, bad_doi_groups).

    pairs          — (entryA, entryB, reason, confidence) tuples sorted by
                     confidence.  reason ∈ {'doi', 'title-high', 'title-mid'}
    bad_doi_groups — {doi: [entries]} where multiple entries share a DOI but
                     are clearly different papers (proceedings-level DOI or
                     CrossRef mis-assignment).  These are NOT flagged as
                     duplicates but are reported separately so the user can
                     choose to clear the incorrect DOI field.
    """
    pairs: list[tuple[dict, dict, str, float]] = []
    seen: set[frozenset] = set()
    bad_doi_groups: dict[str, list[dict]] = {}

    # --- Step 1: group by normalised DOI ---
    doi_groups: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        d = entry_doi(e)
        if d:
            doi_groups[d].append(e)

    for doi, group in doi_groups.items():
        if len(group) < 2:
            continue

        # 3+ entries sharing a DOI → almost certainly a proceedings/container
        # DOI, not a per-paper DOI.
        if len(group) >= 3:
            bad_doi_groups[doi] = group
            continue

        # 2 entries: check title similarity before declaring a duplicate.
        a, b = group[0], group[1]
        t_a = a.get("title", "")
        t_b = b.get("title", "")
        sim = title_similarity(t_a, t_b) if (t_a and t_b) else 0.0

        if sim < min_doi_title_sim:
            # Same DOI, very different titles → CrossRef mis-assignment or
            # a container DOI used for two unrelated chapters/papers.
            bad_doi_groups[doi] = group
            continue

        # Genuine duplicate
        key = frozenset((a["ID"], b["ID"]))
        if key not in seen:
            seen.add(key)
            pairs.append((a, b, "doi", 1.0))

    # --- Step 2: title similarity for all remaining pairs ---
    for a, b in combinations(entries, 2):
        key = frozenset((a["ID"], b["ID"]))
        if key in seen:
            continue
        t_a = a.get("title", "")
        t_b = b.get("title", "")
        if not t_a or not t_b:
            continue
        sim = title_similarity(t_a, t_b)
        if sim >= 0.92:
            seen.add(key)
            pairs.append((a, b, "title-high", sim))
        elif sim >= 0.75:
            seen.add(key)
            pairs.append((a, b, "title-mid", sim))

    order = {"doi": 0, "title-high": 1, "title-mid": 2}
    pairs.sort(key=lambda x: (order[x[2]], -x[3]))
    return pairs, bad_doi_groups


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

CONFIDENCE_LABEL = {
    "doi":        "⚠️  DOI match   — almost certainly the same paper",
    "title-high": "🔶 High title similarity — very likely the same paper",
    "title-mid":  "🔷 Moderate title similarity — possible duplicate",
}


def display_entry(label: str, entry: dict) -> None:
    fields = entry_display_fields(entry)
    title  = entry.get("title",    "—")
    year   = entry.get("year",     "—")
    venue  = (entry.get("journal") or entry.get("booktitle") or "—")
    doi    = entry.get("doi",      "—")
    etype  = entry.get("ENTRYTYPE","?")

    print(f"  ┌─ Entry {label}: {entry['ID']}  (@{etype})")
    # Wrap title at 68 chars
    words, line = title.split(), ""
    title_lines = []
    for w in words:
        if len(line) + len(w) + 1 > 68:
            title_lines.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    if line:
        title_lines.append(line)
    print(f"  │  Title:  {title_lines[0]}")
    for tl in title_lines[1:]:
        print(f"  │          {tl}")
    print(f"  │  Year:   {year}")
    print(f"  │  Venue:  {venue[:72]}")
    print(f"  │  DOI:    {doi}")
    # Field list
    field_str = ", ".join(fields)
    wrapped = []
    line = ""
    for part in (field_str + " ").split(", "):
        part = part.strip()
        if not part:
            continue
        if len(line) + len(part) + 2 > 60:
            wrapped.append(line)
            line = part
        else:
            line = (line + ", " + part).strip(", ")
    if line:
        wrapped.append(line)
    print(f"  │  Fields: {wrapped[0] if wrapped else ''} ({len(fields)} total)")
    for wl in wrapped[1:]:
        print(f"  │          {wl}")
    print(f"  └{'─'*65}")


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

# Fields where we always want the most complete value
UNION_FIELDS = {
    "doi", "semanticscholar", "arxiv", "ieeexplore", "url",
    "dvrk_site", "research_field", "data_type", "abstract",
    "keywords", "pages", "volume", "number", "isbn", "issn",
    "openaccesspdf", "pdf",
}

# Fields from the richer (more fields) entry take precedence for these
PREFER_RICHER = {
    "author", "title", "journal", "booktitle", "year",
    "publisher", "month", "address",
}


def merge_entries(a: dict, b: dict) -> dict:
    """Return a new entry dict combining the best of a and b."""
    # Use the entry with more content-bearing fields as the base
    a_fields = [k for k in a if k not in ("ENTRYTYPE", "ID") and a[k].strip()]
    b_fields = [k for k in b if k not in ("ENTRYTYPE", "ID") and b[k].strip()]
    if len(b_fields) > len(a_fields):
        base, other = dict(b), dict(a)
    else:
        base, other = dict(a), dict(b)

    for field, value in other.items():
        if field in ("ENTRYTYPE", "ID"):
            continue
        value = value.strip() if isinstance(value, str) else value
        existing = base.get(field, "").strip() if isinstance(base.get(field), str) else ""

        if field in UNION_FIELDS:
            # Take whichever is non-empty; prefer longer if both present
            if not existing:
                base[field] = value
            elif value and len(value) > len(existing):
                base[field] = value
        elif field in PREFER_RICHER:
            # Base already has the richer entry's value; keep it
            if not existing:
                base[field] = value
        else:
            # Unknown / extra field: add if missing
            if not existing and value:
                base[field] = value

    return base


# ---------------------------------------------------------------------------
# BibTeX I/O
# ---------------------------------------------------------------------------

FIELD_ORDER = [
    "author", "title", "journal", "booktitle", "year", "volume", "number",
    "pages", "month", "publisher", "doi", "url", "ieeexplore",
    "semanticscholar", "arxiv", "pdf", "openaccesspdf",
    "research_field", "data_type", "dvrk_site", "abstract", "keywords",
]


def load_bib(path: str) -> tuple[bibtexparser.bibdatabase.BibDatabase, BibTexParser]:
    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    with open(path, encoding="utf-8") as f:
        db = bibtexparser.load(f, parser=parser)
    return db


def write_bib(path: str, db: bibtexparser.bibdatabase.BibDatabase) -> None:
    writer = BibTexWriter()
    writer.indent = "  "
    writer.order_entries_by = None
    writer.display_order = FIELD_ORDER
    writer.add_trailing_comma = True
    with open(path, "w", encoding="utf-8") as f:
        f.write(writer.write(db))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactively remove duplicate BibTeX entries.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--bib",      default="publications.bib", help="Path to bib file")
    parser.add_argument("--dry-run",  action="store_true", help="Report duplicates without writing")
    parser.add_argument("--min-sim",  type=float, default=0.75,
                        help="Minimum title similarity to flag (default: 0.75)")
    args = parser.parse_args()

    print(f"Loading {args.bib}...")
    db = load_bib(args.bib)
    entries = db.entries
    print(f"  {len(entries)} entries loaded.\n")

    pairs, bad_doi_groups = find_duplicates(entries)

    # --- Report proceedings/bad DOIs ---
    if bad_doi_groups:
        print("=" * 70)
        print(f"  ⚠️  Found {len(bad_doi_groups)} DOI(s) shared by unrelated papers.")
        print("      These look like proceedings-level or mis-assigned DOIs,")
        print("      NOT actual duplicates (different titles, same DOI).")
        print("="*70)
        for doi, group in bad_doi_groups.items():
            print(f"\n  DOI: {doi}  ({len(group)} entries)")
            for e in group:
                print(f"    • {e['ID']:35s} {e.get('title','')[:55]}")
        print()
        if not args.dry_run:
            ans = input(
                f"  Remove this incorrect DOI field from all {sum(len(g) for g in bad_doi_groups.values())} affected entries? [y/n]: "
            ).lower().strip()
            if ans in ("y", "yes"):
                cleared = 0
                for doi, group in bad_doi_groups.items():
                    for e in group:
                        if "doi" in e:
                            del e["doi"]
                            cleared += 1
                print(f"  Cleared DOI field from {cleared} entries.")
        print()

    if not pairs:
        print("No title/content duplicates found. ✅")
        if bad_doi_groups and not args.dry_run:
            # Still write back if we cleared bad DOIs
            write_bib(args.bib, db)
            print(f"Written {len(entries)} entries to {args.bib}")
            print("Run 'python3 scripts/cleanup_bib.py' to normalise formatting.")
        return

    print(f"Found {len(pairs)} suspected duplicate pair(s).\n")
    if args.dry_run:
        print("─" * 70)
        for i, (a, b, reason, conf) in enumerate(pairs, 1):
            print(f"  #{i:3d}  [{CONFIDENCE_LABEL[reason]}]  conf={conf:.2f}")
            print(f"       A: {a['ID']:30s}  {a.get('title','')[:55]}")
            print(f"       B: {b['ID']:30s}  {b.get('title','')[:55]}")
        return

    # Back up before making any changes
    backup = args.bib + ".dedup-bak"
    shutil.copy(args.bib, backup)
    print(f"Backup saved to {backup}\n")

    # Build a set of IDs to remove (we remove by ID, keep others)
    to_remove: set[str] = set()
    # Entries that were merged (replacement entry keyed by the winning ID)
    replacements: dict[str, dict] = {}

    for i, (a, b, reason, conf) in enumerate(pairs, 1):
        # Skip if either entry was already handled
        if a["ID"] in to_remove or b["ID"] in to_remove:
            continue

        print("=" * 70)
        print(f"  Duplicate {i}/{len(pairs)}  |  {CONFIDENCE_LABEL[reason]}  (conf={conf:.2f})")
        print("=" * 70)
        display_entry("A", a)
        display_entry("B", b)

        while True:
            choice = input("\n  [1] keep A / [2] keep B / [m] merge / [s] skip / [q] quit: ").lower().strip()
            if choice in ("1",):
                to_remove.add(b["ID"])
                print(f"  ✅ Keeping {a['ID']}, removing {b['ID']}")
                break
            elif choice in ("2",):
                to_remove.add(a["ID"])
                print(f"  ✅ Keeping {b['ID']}, removing {a['ID']}")
                break
            elif choice in ("m", "merge"):
                merged = merge_entries(a, b)
                # Keep the key from whichever entry has more fields
                winner_id = a["ID"] if len(entry_display_fields(a)) >= len(entry_display_fields(b)) else b["ID"]
                loser_id  = b["ID"] if winner_id == a["ID"] else a["ID"]
                merged["ID"] = winner_id
                replacements[winner_id] = merged
                to_remove.add(loser_id)
                # Show merged field count
                merged_fields = [k for k in merged if k not in ("ENTRYTYPE", "ID")]
                print(f"  🔀 Merged into {winner_id} ({len(merged_fields)} fields), removed {loser_id}")
                break
            elif choice in ("s", "skip"):
                print("  ⏭  Skipped — both entries retained.")
                break
            elif choice in ("q", "quit"):
                print("Stopping review.")
                break
            else:
                print("  Please type 1, 2, m, s, or q.")
        else:
            continue  # inner while else → didn't break on 'q'
        if choice in ("q", "quit"):
            break

    if not to_remove and not replacements:
        print("\nNo changes made.")
        return

    # Apply removals and replacements
    new_entries = []
    for e in entries:
        eid = e["ID"]
        if eid in to_remove:
            continue
        if eid in replacements:
            new_entries.append(replacements[eid])
        else:
            new_entries.append(e)

    removed_count = len(entries) - len(new_entries) - sum(
        1 for rid in replacements if rid not in to_remove
    )
    db.entries = new_entries

    print(f"\nRemoved {len(to_remove)} entr{'y' if len(to_remove)==1 else 'ies'}; "
          f"{len(replacements)} merge(s) applied.")
    print(f"Writing {len(new_entries)} entries back to {args.bib}...")
    write_bib(args.bib, db)
    print("Done. Run 'python3 scripts/cleanup_bib.py' to normalise formatting.")


if __name__ == "__main__":
    main()
