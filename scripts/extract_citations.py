"""
extract_citations.py
--------------------
Extracts internal citations between all papers in publications.bib.
For each paper:
1. Queries CrossRef (and cached references) for referenced works.
2. Intersects referenced DOIs and titles against all papers in publications.bib.
3. Builds the internal citation references.
4. Writes `dvrk_cites = {ID1 and ID2 and ...}` directly to publications.bib.
   (The companion `cited_by` relationship is computed dynamically on the fly by app.js).
"""

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
import urllib.request
import urllib.parse
import json
import time
import os
import re
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

CACHE_PATH = "cache/reference_cache.json"
BIB_PATH = "publications.bib"
HEADERS = {'User-Agent': 'dVRK-Community-Citation-Extractor/1.0 (mailto:deguet@jhu.edu)'}

def load_cache():
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2)

def normalize_title(t):
    if not t:
        return ""
    t = re.sub(r'[{}\'"\\]', '', t)
    t = re.sub(r'[^a-zA-Z0-9]', '', t).lower()
    return t

def normalize_doi(doi):
    if not doi:
        return ""
    doi = doi.strip()
    doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi, flags=re.IGNORECASE)
    doi = re.sub(r'^doi:\s*', '', doi, flags=re.IGNORECASE).strip().lower()
    return doi

def fetch_references_crossref(doi):
    """Fetch referenced DOIs and article titles from CrossRef."""
    clean_doi = normalize_doi(doi)
    if not clean_doi or clean_doi.startswith('10.48550/arxiv'):
        return None
    url = f"https://api.crossref.org/works/{urllib.parse.quote(clean_doi, safe='')}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            msg = data.get('message', {})
            raw_refs = msg.get('reference', [])
            extracted = []
            for r in raw_refs:
                r_doi = normalize_doi(r.get('DOI', ''))
                r_title = r.get('article-title', '').strip()
                if r_doi or r_title:
                    extracted.append({
                        'doi': r_doi,
                        'title': r_title
                    })
            return extracted
    except Exception:
        return None

def main(dry_run=False, write_json=False):
    print("Loading publications.bib...")
    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    with open(BIB_PATH, 'r', encoding='utf-8') as f:
        db = bibtexparser.load(f, parser=parser)

    print(f"Loaded {len(db.entries)} publications.")

    # Build lookup dictionaries
    doi_to_id = {}
    title_to_id = {}
    papers_info = {}

    for e in db.entries:
        pid = e['ID']
        doi = normalize_doi(e.get('doi', ''))
        raw_title = e.get('title', '')
        norm_title = normalize_title(raw_title)

        if doi:
            doi_to_id[doi] = pid
        if norm_title and len(norm_title) > 15:
            title_to_id[norm_title] = pid

        papers_info[pid] = {
            'id': pid,
            'title': raw_title.replace('{', '').replace('}', '').strip(),
            'year': e.get('year', ''),
            'author': e.get('author', ''),
            'doi': doi,
            'dvrk_site': e.get('dvrk_site', '')
        }

    print(f"Indexed {len(doi_to_id)} DOIs and {len(title_to_id)} titles.")

    cache = load_cache()
    print(f"Loaded cache with {len(cache)} entries.")

    entries_to_fetch = []
    for e in db.entries:
        doi = normalize_doi(e.get('doi', ''))
        if doi and doi not in cache:
            entries_to_fetch.append(doi)

    if entries_to_fetch:
        print(f"Need to fetch references for {len(entries_to_fetch)} DOIs.")
        new_cache = {}
        completed = 0
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_doi = {
                executor.submit(fetch_references_crossref, doi): doi
                for doi in entries_to_fetch
            }
            for future in as_completed(future_to_doi):
                doi = future_to_doi[future]
                completed += 1
                try:
                    refs = future.result()
                    new_cache[doi] = refs if refs is not None else []
                except Exception:
                    new_cache[doi] = []

                if completed % 25 == 0 or completed == len(entries_to_fetch):
                    print(f"  Fetched {completed}/{len(entries_to_fetch)} DOIs...")
                time.sleep(0.05)

        cache.update(new_cache)
        save_cache(cache)
        print("Updated reference cache.")
    else:
        print("All reference lists found in local cache.")

    # Match internal citations
    print("\nMatching internal community citations...")
    citations = {pid: {"cites": [], "cited_by": []} for pid in papers_info}
    total_edges = 0

    for e in db.entries:
        pid = e['ID']
        doi = normalize_doi(e.get('doi', ''))
        if not doi or doi not in cache:
            continue

        refs = cache.get(doi, [])
        matched_targets = set()

        for r in refs:
            r_doi = normalize_doi(r.get('doi', ''))
            r_title = normalize_title(r.get('title', ''))

            target_id = None
            if r_doi and r_doi in doi_to_id:
                target_id = doi_to_id[r_doi]
            elif r_title and len(r_title) > 20:
                # Substring or exact title match
                if r_title in title_to_id:
                    target_id = title_to_id[r_title]
                else:
                    for t_norm, t_id in title_to_id.items():
                        if (r_title in t_norm or t_norm in r_title) and abs(len(r_title) - len(t_norm)) < 15:
                            target_id = t_id
                            break

            if target_id and target_id != pid:
                matched_targets.add(target_id)

        for target_id in sorted(matched_targets):
            citations[pid]["cites"].append(target_id)
            citations[target_id]["cited_by"].append(pid)
            total_edges += 1

    # Sort arrays for stability
    for pid in citations:
        citations[pid]["cites"].sort()
        citations[pid]["cited_by"].sort()

    # Assign dvrk_cites to BibTeX entries
    tagged_count = 0
    for e in db.entries:
        pid = e['ID']
        cites_list = citations.get(pid, {}).get("cites", [])
        if cites_list:
            e['dvrk_cites'] = " and ".join(cites_list)
            tagged_count += 1
        elif 'dvrk_cites' in e:
            del e['dvrk_cites']

    papers_citing = sum(1 for p in citations.values() if p["cites"])
    papers_cited = sum(1 for p in citations.values() if p["cited_by"])

    print(f"\nInternal Citation Summary:")
    print(f"  Total internal citation links: {total_edges}")
    print(f"  Papers that cite other dVRK papers: {papers_citing}")
    print(f"  Papers cited by other dVRK papers: {papers_cited}")

    if not dry_run:
        writer = BibTexWriter()
        writer.indent = '  '
        writer.order_entries_by = None
        writer.add_trailing_comma = True
        with open(BIB_PATH, 'w', encoding='utf-8') as f:
            f.write(writer.write(db))
        print(f"\nSuccessfully wrote dvrk_cites to {BIB_PATH} ({tagged_count} publications tagged).")
    else:
        print(f"\n[DRY RUN] Would update {tagged_count} publications in {BIB_PATH}.")

    if write_json:
        json_output = {
            "summary": {
                "total_papers": len(papers_info),
                "total_citations": total_edges,
                "papers_citing": papers_citing,
                "papers_cited": papers_cited
            },
            "citations": citations
        }
        with open("citations.json", 'w', encoding='utf-8') as f:
            json.dump(json_output, f, indent=2)
        print(f"Saved citations to citations.json.")

    # Top 5 most cited dVRK papers
    top_cited = sorted(citations.items(), key=lambda x: len(x[1]["cited_by"]), reverse=True)[:5]
    print("\nTop 5 Most Cited Papers within Community:")
    for pid, data in top_cited:
        info = papers_info[pid]
        print(f"  - [{pid}] ({len(data['cited_by'])} citations): {info['title'][:60]} ({info['year']})")

if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser(description="Extract community citations and tag publications.bib with dvrk_cites.")
    arg_parser.add_argument("--dry-run", action="store_true", help="Perform citation extraction without modifying publications.bib.")
    arg_parser.add_argument("--write-json", action="store_true", help="Also export citation graph to citations.json.")
    args = arg_parser.parse_args()
    main(dry_run=args.dry_run, write_json=args.write_json)
