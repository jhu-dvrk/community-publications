#!/usr/bin/env python3
"""
Interactively find and remove duplicate entries from publications.bib.

Detection strategies (in order of confidence):
  1. Identical DOI (after normalisation)  — almost certainly the same paper
  2. Title similarity ≥ 0.92              — very likely the same paper
  3. Title similarity ≥ min_sim (0.75)    — probable duplicate; show for review

For each suspected duplicate you can:
  [1] keep entry A   — discard B (and redirect incoming dvrk_cites B -> A)
  [2] keep entry B   — discard A (and redirect incoming dvrk_cites A -> B)
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
import shutil
from collections import defaultdict
from itertools import combinations

from bib_utils import (
    DEFAULT_BIB_PATH,
    load_bib,
    normalize_doi,
    redirect_or_prune_cites,
    title_similarity,
    write_bib,
)


def entry_doi(entry: dict) -> str | None:
    raw = entry.get("doi", "").strip()
    norm = normalize_doi(raw)
    return norm if norm else None


def entry_display_fields(entry: dict) -> list[str]:
    return [k for k in entry if k not in ("ENTRYTYPE", "ID")]


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def find_duplicates(
    entries: list[dict],
    min_sim: float = 0.75,
) -> list[tuple[dict, dict, str, float]]:
    """Return (entryA, entryB, reason, confidence) tuples sorted by confidence."""
    pairs: list[tuple[dict, dict, str, float]] = []
    seen: set[frozenset] = set()

    # Step 1: group by normalized DOI
    doi_groups: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        d = entry_doi(e)
        if d:
            doi_groups[d].append(e)

    for doi, group in doi_groups.items():
        if len(group) < 2:
            continue
        for a, b in combinations(group, 2):
            sim = title_similarity(a.get("title", ""), b.get("title", ""))
            if sim >= 0.50:
                key = frozenset((a["ID"], b["ID"]))
                if key not in seen:
                    seen.add(key)
                    pairs.append((a, b, "doi", 1.0))

    # Step 2: title similarity for all remaining pairs
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
        elif sim >= min_sim:
            seen.add(key)
            pairs.append((a, b, "title-mid", sim))

    order = {"doi": 0, "title-high": 1, "title-mid": 2}
    pairs.sort(key=lambda x: (order[x[2]], -x[3]))
    return pairs


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
    title  = entry.get("title", "—")
    year   = entry.get("year", "—")
    venue  = entry.get("journal") or entry.get("booktitle") or entry.get("howpublished") or entry.get("school") or "—"
    doi    = entry.get("doi", "—")
    etype  = entry.get("ENTRYTYPE", "?")

    print(f"  ┌─ Entry {label}: {entry['ID']}  (@{etype})")
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

AND_LIST_FIELDS = {"dvrk_site", "research_field", "data_type", "dvrk_cites"}

UNION_FIELDS = {
    "doi", "semanticscholar", "arxiv", "ieeexplore", "url",
    "abstract", "keywords", "pages", "volume", "number", "isbn", "issn",
    "openaccesspdf", "pdf", "school",
}

PREFER_RICHER = {
    "author", "title", "journal", "booktitle", "year",
    "publisher", "month", "address", "peer_reviewed",
}


def merge_entries(a: dict, b: dict) -> dict:
    """Return a new entry dict combining the best of a and b."""
    a_fields = [k for k in a if k not in ("ENTRYTYPE", "ID") and str(a[k]).strip()]
    b_fields = [k for k in b if k not in ("ENTRYTYPE", "ID") and str(b[k]).strip()]
    if len(b_fields) > len(a_fields):
        base, other = dict(b), dict(a)
    else:
        base, other = dict(a), dict(b)

    # Prefer 'yes' over 'no' when merging a preprint with its published paper
    if base.get("peer_reviewed") == "no" and other.get("peer_reviewed") == "yes":
        base["peer_reviewed"] = "yes"

    for field, value in other.items():
        if field in ("ENTRYTYPE", "ID"):
            continue
        value = value.strip() if isinstance(value, str) else value
        existing = base.get(field, "").strip() if isinstance(base.get(field), str) else ""

        if field == "date_added":
            if not existing:
                base[field] = value
            elif value:
                base[field] = min(existing, value)
        elif field in AND_LIST_FIELDS:
            tokens = {t.strip() for t in existing.split(" and ") if t.strip()}
            tokens |= {t.strip() for t in str(value).split(" and ") if t.strip()}
            if tokens:
                base[field] = " and ".join(sorted(tokens))
        elif field in UNION_FIELDS:
            if not existing:
                base[field] = value
            elif value and len(value) > len(existing):
                base[field] = value
        elif field in PREFER_RICHER:
            if not existing:
                base[field] = value
        else:
            if not existing and value:
                base[field] = value

    return base


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactively remove or merge duplicate BibTeX entries.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--bib", default=DEFAULT_BIB_PATH, help="Path to bib file")
    parser.add_argument("--dry-run", action="store_true", help="Report duplicates without writing")
    parser.add_argument("--min-sim", type=float, default=0.75, help="Minimum title similarity to flag (default: 0.75)")
    args = parser.parse_args()

    print(f"Loading {args.bib}...")
    db = load_bib(args.bib)
    entries = db.entries
    print(f"  {len(entries)} entries loaded.\n")

    pairs = find_duplicates(entries, min_sim=args.min_sim)

    if not pairs:
        print("No duplicates found. ✅")
        return

    print(f"Found {len(pairs)} suspected duplicate pair(s).\n")
    if args.dry_run:
        print("─" * 70)
        for i, (a, b, reason, conf) in enumerate(pairs, 1):
            print(f"  #{i:3d}  [{CONFIDENCE_LABEL[reason]}]  conf={conf:.2f}")
            print(f"       A: {a['ID']:30s}  {a.get('title','')[:55]}")
            print(f"       B: {b['ID']:30s}  {b.get('title','')[:55]}")
        return

    backup = args.bib + ".dedup-bak"
    shutil.copy(args.bib, backup)
    print(f"Backup saved to {backup}\n")

    to_remove: set[str] = set()
    replacements: dict[str, dict] = {}
    merged_id_map: dict[str, str] = {}

    for i, (a, b, reason, conf) in enumerate(pairs, 1):
        if a["ID"] in to_remove or b["ID"] in to_remove:
            continue

        print("=" * 70)
        print(f"  Duplicate {i}/{len(pairs)}  |  {CONFIDENCE_LABEL[reason]}  (conf={conf:.2f})")
        print("=" * 70)
        display_entry("A", a)
        display_entry("B", b)

        while True:
            choice = input("\n  [1] keep A / [2] keep B / [m] merge / [s] skip / [q] quit: ").lower().strip()
            if choice == "1":
                to_remove.add(b["ID"])
                merged_id_map[b["ID"]] = a["ID"]
                print(f"  ✅ Keeping {a['ID']}, removing {b['ID']}")
                break
            elif choice == "2":
                to_remove.add(a["ID"])
                merged_id_map[a["ID"]] = b["ID"]
                print(f"  ✅ Keeping {b['ID']}, removing {a['ID']}")
                break
            elif choice in ("m", "merge"):
                merged = merge_entries(a, b)
                winner_id = a["ID"] if len(entry_display_fields(a)) >= len(entry_display_fields(b)) else b["ID"]
                loser_id  = b["ID"] if winner_id == a["ID"] else a["ID"]
                merged["ID"] = winner_id
                replacements[winner_id] = merged
                to_remove.add(loser_id)
                merged_id_map[loser_id] = winner_id
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
        if choice in ("q", "quit"):
            break

    if not to_remove and not replacements:
        print("\nNo changes made.")
        return

    new_entries = []
    for e in entries:
        eid = e["ID"]
        if eid in to_remove:
            continue
        new_entries.append(replacements.get(eid, e))

    redirect_or_prune_cites(new_entries, merged_map=merged_id_map)
    db.entries = new_entries

    print(f"\nRemoved {len(to_remove)} entr{'y' if len(to_remove) == 1 else 'ies'}; "
          f"{len(replacements)} merge(s) applied.")
    write_bib(args.bib, db, sort=True)
    print(f"Wrote canonically sorted bibliography ({len(new_entries)} entries) to {args.bib}. ✅")


if __name__ == "__main__":
    main()
