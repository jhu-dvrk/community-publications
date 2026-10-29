#!/usr/bin/env python3
"""
tag_peer_reviewed.py
--------------------
Tags each publication in publications.bib with a `peer_reviewed` field:
  - peer_reviewed = {yes}    : Peer-reviewed journal, conference, or symposium paper.
  - peer_reviewed = {no}     : Unreviewed preprint (arXiv, Research Square, SSRN, etc.) or tech report.
  - peer_reviewed = {thesis} : Doctoral or Master's thesis.

Also checks candidate preprints against OpenAlex and Crossref: if an arXiv preprint
was subsequently accepted and published in a peer-reviewed venue (e.g. ICRA, IROS, RA-L),
the entry's venue and DOI are updated (promoted), and peer_reviewed is set to {yes}.

Title similarity verification is enforced so that no false-positive promotions occur.

Usage:
    python3 scripts/tag_peer_reviewed.py [--dry-run] [--bib path/to/publications.bib]
"""

import argparse
import difflib
import json
import os
import re
import sys
import time
import requests
import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter

# Standardized field order across all scripts
FIELD_ORDER = [
    'author', 'title', 'journal', 'booktitle', 'year', 'volume', 'number',
    'pages', 'month', 'publisher', 'editor', 'series', 'collection',
    'address', 'organization', 'issn', 'isbn',
    'doi', 'url', 'urldate', 'ieeexplore',
    'semanticscholar', 'arxiv', 'arxivid', 'archiveprefix', 'primaryclass', 'eprint',
    'pdf', 'openaccesspdf', 'howpublished', 'pubstate', 'date', 'tppubtype',
    'copyright', 'language',
    'research_field', 'data_type', 'peer_reviewed', 'dvrk_site', 'dvrk_cites', 'date_added',
    'keywords', 'abstract',
]

OVERRIDES_FILE = os.path.join(os.path.dirname(__file__), '..', 'peer_review_overrides.json')
USER_AGENT = 'dVRK-Publications/1.0 (mailto:dvrk@jhu.edu)'

# Known thesis DOI prefixes / repositories
THESIS_PATTERNS = [
    '10.25560/',               # Imperial College London Spiral
    '10.7939/',                # University of Alberta Education & Research Archive
    'spiral.imperial.ac.uk',
    'etheses.whiterose.ac.uk',
]

# Non-peer-reviewed preprint repositories and working paper platforms
PREPRINT_HOSTS = [
    'arxiv',
    'biorxiv',
    'medrxiv',
    'techrxiv',
    'research square',
    'researchsquare',
    '21203/rs',
    'ssrn',
    'chemrxiv',
]

def load_overrides():
    if os.path.exists(OVERRIDES_FILE):
        try:
            with open(OVERRIDES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: could not read {OVERRIDES_FILE}: {e}")
    return {"keys": {}, "venues": {}}

def clean_title_str(t):
    """Normalize title for fuzzy comparison."""
    if not t:
        return ""
    t = re.sub(r'[\{\}\`\'\"]', '', t)
    t = re.sub(r'[^a-zA-Z0-9\s]', ' ', t)
    return ' '.join(t.lower().split())

def title_similarity(t1, t2):
    """Compute similarity ratio between two titles."""
    c1 = clean_title_str(t1)
    c2 = clean_title_str(t2)
    if not c1 or not c2:
        return 0.0
    return difflib.SequenceMatcher(None, c1, c2).ratio()

def extract_arxiv_id(entry):
    """Extract valid arXiv ID (YYMM.NNNN or YYMM.NNNNN) from entry fields."""
    for field in ['eprint', 'arxivid', 'arxiv', 'doi', 'url', 'howpublished', 'journal', 'booktitle']:
        val = entry.get(field, '')
        if not val:
            continue
        m = re.search(r'(?:arxiv\.org/(?:abs|pdf)/|arxiv:\s*|/arxiv\.)(\d{4}\.\d{4,5})(?:v\d+)?', val, re.IGNORECASE)
        if m:
            return m.group(1)
        if field in ['eprint', 'arxivid'] and re.match(r'^\d{4}\.\d{4,5}(?:v\d+)?$', val.strip()):
            return val.strip().split('v')[0]
    return None

def is_thesis(entry):
    """Determine if entry is a doctoral or master's dissertation."""
    etype = entry.get('ENTRYTYPE', '').lower()
    if etype in ['phdthesis', 'mastersthesis']:
        return True
    doi = (entry.get('doi') or '').lower()
    url = (entry.get('url') or '').lower()
    for pat in THESIS_PATTERNS:
        if pat in doi or pat in url:
            return True
    return False

def is_candidate_preprint(entry):
    """Check if entry currently indicates a preprint or unreviewed working paper."""
    j = (entry.get('journal') or '').lower()
    b = (entry.get('booktitle') or '').lower()
    h = (entry.get('howpublished') or '').lower()
    doi = (entry.get('doi') or '').lower()
    url = (entry.get('url') or '').lower()
    eprint = (entry.get('eprint') or '').lower()
    archiveprefix = (entry.get('archiveprefix') or '').lower()
    etype = entry.get('ENTRYTYPE', '').lower()

    venue = f"{j} {b}".strip()
    if venue and not any(host in venue for host in PREPRINT_HOSTS):
        return False

    for host in PREPRINT_HOSTS:
        if host in j or host in b or host in h or host in doi or host in url:
            return True

    if archiveprefix == 'arxiv' or eprint:
        return True

    if etype == 'misc' and not (b or j):
        return True

    return False

def is_preprint_venue(venue_name):
    """Check if a venue name represents a preprint/working paper server rather than a peer-reviewed outlet."""
    if not venue_name:
        return True
    v_low = venue_name.lower()
    for host in PREPRINT_HOSTS:
        if host in v_low:
            return True
    return False

def check_openalex_for_published_work(title, arxiv_id=None, existing_doi=None):
    """Query OpenAlex to check if a preprint has an official published version."""
    query_target = None
    if existing_doi and not any(p in existing_doi.lower() for p in PREPRINT_HOSTS):
        query_target = f"https://doi.org/{existing_doi}"
    elif arxiv_id:
        query_target = f"https://doi.org/10.48550/arxiv.{arxiv_id}"

    if not query_target:
        return None

    api_url = f"https://api.openalex.org/works/{query_target}"
    try:
        r = requests.get(api_url, headers={'User-Agent': USER_AGENT}, timeout=8)
        if r.status_code != 200:
            return None
        data = r.json()
        
        # Verify title match to prevent incorrect metadata bindings
        retrieved_title = data.get('title') or ''
        if title_similarity(title, retrieved_title) < 0.65:
            return None

        canonical_doi = data.get('doi')
        if canonical_doi:
            canonical_doi = canonical_doi.replace('https://doi.org/', '').replace('http://doi.org/', '')
        
        work_type = data.get('type')  # 'article', 'conference-paper', 'preprint'
        primary_loc = data.get('primary_location') or {}
        source = primary_loc.get('source') or {}
        source_name = source.get('display_name') or ''
        source_type = source.get('type') or ''  # 'journal', 'conference', 'repository'

        if is_preprint_venue(source_name):
            return None

        is_published = False
        if canonical_doi and not any(p in canonical_doi.lower() for p in PREPRINT_HOSTS):
            is_published = True
        elif source_type in ['journal', 'conference']:
            is_published = True

        if is_published and source_name:
            return {
                'doi': canonical_doi or existing_doi,
                'venue': source_name,
                'source_type': source_type,
                'work_type': work_type,
                'year': data.get('publication_year'),
                'title': retrieved_title,
            }
    except Exception:
        pass
    return None

def check_crossref_for_doi(title, doi):
    """Query Crossref for published metadata given a DOI and verify title match."""
    if not doi or any(p in doi.lower() for p in PREPRINT_HOSTS):
        return None
    url = f"https://api.crossref.org/works/{doi}"
    try:
        r = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=8)
        if r.status_code != 200:
            return None
        item = r.json().get('message', {})
        wtype = item.get('type', '')

        # Check titles
        titles = item.get('title', [])
        retrieved_title = titles[0] if titles else ''
        if title_similarity(title, retrieved_title) < 0.65:
            return None

        if wtype in ['journal-article', 'proceedings-article', 'book-chapter']:
            container = item.get('container-title', [])
            venue = container[0] if container else ''
            if is_preprint_venue(venue):
                return None
            year = None
            issued = item.get('issued', {}).get('date-parts', [])
            if issued and len(issued[0]) > 0:
                year = issued[0][0]
            return {
                'doi': doi,
                'venue': venue,
                'work_type': wtype,
                'year': year,
                'title': retrieved_title,
            }
    except Exception:
        pass
    return None

def enforce_one_field_per_line(content):
    FIELD_RE = re.compile(r'^\s+[\w][\w\-]*\s*=')
    ENTRY_RE = re.compile(r'^@')
    CLOSE_RE = re.compile(r'^\s*\}')

    lines = content.split('\n')
    out = []
    depth = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append(line)
            depth = 0
            continue

        is_new_field = bool(FIELD_RE.match(line))
        is_entry_start = bool(ENTRY_RE.match(line))
        is_entry_close = bool(CLOSE_RE.match(line))

        if depth > 0 and not is_new_field and not is_entry_start and not is_entry_close:
            out[-1] = out[-1].rstrip() + ' ' + stripped
        else:
            out.append(line)
            depth = 0

        unescaped = re.sub(r'\\[{}]', '', (stripped if depth > 0 else line))
        depth += unescaped.count('{') - unescaped.count('}')
        depth = max(depth, 0)

    return '\n'.join(out)

def tag_publications(bib_path, dry_run=False):
    overrides = load_overrides()
    key_overrides = overrides.get('keys', {})
    venue_overrides = overrides.get('venues', {})

    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False

    with open(bib_path, 'r', encoding='utf-8') as f:
        content = f.read()

    bib_database = bibtexparser.loads(content, parser=parser)
    total = len(bib_database.entries)
    print(f"Loaded {total} entries from {bib_path}")

    stats = {'yes': 0, 'no': 0, 'thesis': 0, 'promoted': 0}
    promotions = []

    for entry in bib_database.entries:
        eid = entry.get('ID', '')
        title = entry.get('title', '')

        # 1. Manual key override
        if eid in key_overrides:
            status = key_overrides[eid]
            entry['peer_reviewed'] = status
            stats[status] = stats.get(status, 0) + 1
            continue

        # 2. Theses
        if is_thesis(entry):
            entry['peer_reviewed'] = 'thesis'
            stats['thesis'] += 1
            continue

        # 3. Candidate preprints & promotion check
        if is_candidate_preprint(entry):
            existing_doi = entry.get('doi')
            arxiv_id = extract_arxiv_id(entry)

            published_info = None
            if existing_doi and not any(p in existing_doi.lower() for p in PREPRINT_HOSTS):
                published_info = check_crossref_for_doi(title, existing_doi)
                if not published_info:
                    published_info = check_openalex_for_published_work(title, existing_doi=existing_doi)
            elif arxiv_id:
                time.sleep(0.08)
                published_info = check_openalex_for_published_work(title, arxiv_id=arxiv_id)

            if published_info and published_info.get('venue') and not is_preprint_venue(published_info['venue']):
                old_venue = entry.get('journal') or entry.get('booktitle') or entry.get('howpublished') or 'Preprint'
                new_venue = published_info['venue']
                new_doi = published_info.get('doi') or existing_doi
                wtype = published_info.get('work_type') or ''

                promotions.append((eid, old_venue, new_venue, new_doi))
                stats['promoted'] += 1
                stats['yes'] += 1
                entry['peer_reviewed'] = 'yes'

                if not dry_run:
                    if 'journal' in wtype or entry.get('ENTRYTYPE') == 'article':
                        entry['journal'] = new_venue
                        entry['ENTRYTYPE'] = 'article'
                        if 'booktitle' in entry:
                            del entry['booktitle']
                    else:
                        entry['booktitle'] = new_venue
                        entry['ENTRYTYPE'] = 'inproceedings'
                        if 'journal' in entry:
                            del entry['journal']
                    
                    if new_doi:
                        entry['doi'] = new_doi
                    if published_info.get('year'):
                        entry['year'] = str(published_info['year'])
                    if 'howpublished' in entry and any(h in entry['howpublished'].lower() for h in PREPRINT_HOSTS):
                        del entry['howpublished']
                continue
            else:
                # Confirmed unreviewed preprint
                entry['peer_reviewed'] = 'no'
                stats['no'] += 1
                continue

        # 4. Venue overrides
        v_combined = f"{entry.get('journal', '')} {entry.get('booktitle', '')}".strip()
        matched_override = False
        for v_pat, v_stat in venue_overrides.items():
            if v_pat.lower() in v_combined.lower():
                entry['peer_reviewed'] = v_stat
                stats[v_stat] = stats.get(v_stat, 0) + 1
                matched_override = True
                break
        if matched_override:
            continue

        # 5. Default published works (Conferences, Journals, Hamlyn/CRAS Symposia, Book chapters)
        entry['peer_reviewed'] = 'yes'
        stats['yes'] += 1

    print("\n--- Tagging Results ---")
    print(f"Total entries:         {total}")
    print(f"Peer-reviewed (yes):   {stats['yes']}")
    print(f"Preprints (no):        {stats['no']}")
    print(f"Theses (thesis):       {stats['thesis']}")
    print(f"Preprints promoted:    {stats['promoted']}")

    if promotions:
        print("\nPromoted Preprints:")
        for eid, old_v, new_v, new_doi in promotions:
            print(f"  • {eid}: '{old_v}' -> '{new_v}' (DOI: {new_doi})")

    if not dry_run:
        writer = BibTexWriter()
        writer.indent = '  '
        writer.order_entries_by = None
        writer.display_order = FIELD_ORDER
        writer.add_trailing_comma = True

        out = writer.write(bib_database)
        out = enforce_one_field_per_line(out)

        with open(bib_path, 'w', encoding='utf-8') as f:
            f.write(out)
        print(f"\nSaved updated entries to {bib_path}")
    else:
        print("\n[Dry Run] No files were modified.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Tag publications by peer-review status")
    parser.add_argument('--bib', default='publications.bib', help="Path to publications.bib")
    parser.add_argument('--dry-run', action='store_true', help="Preview changes without modifying file")
    args = parser.parse_args()

    tag_publications(args.bib, dry_run=args.dry_run)
