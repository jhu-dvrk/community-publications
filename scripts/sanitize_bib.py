#!/usr/bin/env python3
"""
sanitize_bib.py
---------------
Audits and repairs corrupted metadata, mismatched identifiers, polluted abstracts,
and missing venues in publications.bib using strict title + author verification
against local Semantic Scholar cache, OpenAlex, and Crossref.

Usage:
    python3 scripts/sanitize_bib.py [--dry-run] [--bib publications.bib]
"""

import argparse
import collections
import difflib
import glob
import html
import json
import os
import re
import time
import unicodedata
import requests
import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter

from cleanup_bib import FIELD_ORDER, enforce_one_field_per_line, extract_pub_date, normalize_months

USER_AGENT = "dVRK-Publications/1.0 (mailto:dvrk@jhu.edu)"
PREPRINT_PATTERNS = ("arxiv", "biorxiv", "medrxiv", "techrxiv", "21203/rs", "researchsquare", "ssrn", "10.1101/", "corr")

STOPWORDS = {
    "the", "a", "an", "of", "in", "for", "on", "with", "to", "and", "by", "from",
    "using", "via", "based", "towards", "toward", "into", "under", "over", "at",
    "as", "is", "are", "this", "that", "these", "those", "paper", "study", "work",
    "approach", "method", "methods", "system", "systems", "novel", "new",
    "framework", "model", "models", "learning", "deep", "data", "driven",
    "evaluation", "analysis", "design", "development", "control",
}

MASTHEAD_RE = re.compile(
    r"(is published by the ieee|joint publication of the ieee|for membership and subscription|"
    r"international conference on intelligent robots and systems.*(?:will be held|was held)|"
    r"innovative preprint repository,\s*arxiv,\s*was created|"
    r"guest editors\s*:.*professor of|"
    r"univ\.\s*of\s*melbourne.*university\s*of\s*salerno)",
    re.IGNORECASE | re.DOTALL,
)


def norm_text(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[{}]", "", s)
    s = re.sub(r"[^a-zA-Z0-9]+", " ", s.lower())
    return " ".join(s.split())


def title_sim(a, b):
    na, nb = norm_text(a), norm_text(b)
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def word_jaccard(a, b):
    wa = set(re.findall(r"[a-z]{4,}", norm_text(a))) - STOPWORDS
    wb = set(re.findall(r"[a-z]{4,}", norm_text(b))) - STOPWORDS
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def extract_surnames(author_str):
    surnames = set()
    if not author_str:
        return surnames
    for raw in re.split(r"\s+and\s+", author_str, flags=re.IGNORECASE):
        raw = re.sub(r"[{}]", "", raw).strip()
        if not raw:
            continue
        if "," in raw:
            last = raw.split(",")[0].strip()
        else:
            parts = raw.split()
            last = parts[-1] if parts else ""
        nl = norm_text(last)
        if nl:
            for token in nl.split():
                if len(token) >= 2:
                    surnames.add(token)
            surnames.add(nl.replace(" ", ""))
    return surnames


def oa_surnames(work):
    out = set()
    for auth in work.get("authorships") or []:
        disp = (auth.get("author") or {}).get("display_name") or ""
        parts = norm_text(disp).split()
        if parts:
            out.add(parts[-1])
            for p in parts:
                if len(p) >= 3:
                    out.add(p)
    return out


def cr_surnames(item):
    out = set()
    for auth in item.get("author") or []:
        fam = norm_text(auth.get("family") or "")
        if fam:
            out.add(fam.replace(" ", ""))
            for p in fam.split():
                if len(p) >= 2:
                    out.add(p)
    return out


def reconstruct_oa_abstract(inv):
    if not inv:
        return ""
    pos_map = {}
    for word, positions in inv.items():
        for pos in positions:
            pos_map[pos] = word
    text = " ".join(pos_map[i] for i in sorted(pos_map))
    return clean_abstract_text(text)


def clean_abstract_text(text):
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"^\s*abstract[\s:.\-—]+", "", text, flags=re.IGNORECASE)
    text = " ".join(text.split())
    return text.strip()


def clean_doi(doi):
    if not doi:
        return ""
    d = doi.strip()
    d = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", d, flags=re.IGNORECASE)
    return d.strip()


def extract_arxiv_id(val):
    if not val:
        return None
    m = re.search(r"(\d{4}\.\d{4,5})(?:v\d+)?", val)
    return m.group(1) if m else None


def load_local_s2_cache():
    by_url = {}
    for path in glob.glob("cache/*.json"):
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            if isinstance(data, dict) and data.get("url"):
                by_url[data["url"].strip()] = data
        except Exception:
            pass
    return by_url


def batch_fetch_openalex_by_dois(dois):
    """Fetch OpenAlex works for a list of normalized lowercase DOIs."""
    unique = sorted({d.lower() for d in dois if d})
    results = {}
    batch_size = 40
    for i in range(0, len(unique), batch_size):
        batch = unique[i:i + batch_size]
        filt = "|".join(f"https://doi.org/{d}" for d in batch)
        try:
            r = requests.get(
                "https://api.openalex.org/works",
                params={
                    "filter": f"doi:{filt}",
                    "per-page": 50,
                    "select": "id,doi,title,display_name,type,publication_year,primary_location,authorships,abstract_inverted_index",
                },
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            if r.status_code == 200:
                for w in r.json().get("results", []):
                    d = clean_doi(w.get("doi") or "").lower()
                    if d:
                        results[d] = w
                    # Also index by any arXiv location DOI if OpenAlex merged preprint->published
                    for b_doi in batch:
                        if b_doi.startswith("10.48550/arxiv.") and b_doi not in results:
                            # Check title or single query fallback later
                            pass
        except Exception as e:
            print(f"Warning: OpenAlex batch error: {e}")
        time.sleep(0.1)
    return results


def fetch_crossref_doi(doi):
    try:
        r = requests.get(
            f"https://api.crossref.org/works/{requests.utils.quote(doi)}",
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json().get("message", {})
    except Exception:
        pass
    return None


def search_verified_work(title, authors_str):
    """Search OpenAlex and Crossref for an exact title + author match."""
    bib_surnames = extract_surnames(authors_str)

    # 1. OpenAlex search
    try:
        r = requests.get(
            "https://api.openalex.org/works",
            params={
                "search": re.sub(r"[{}]", "", title),
                "per-page": 5,
                "select": "id,doi,title,display_name,type,publication_year,primary_location,authorships,abstract_inverted_index",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        if r.status_code == 200:
            best = None
            best_sc = 0.0
            for w in r.json().get("results", []):
                wt = w.get("title") or w.get("display_name") or ""
                sc = title_sim(title, wt)
                if sc >= 0.86:
                    w_sur = oa_surnames(w)
                    if not bib_surnames or (bib_surnames & w_sur):
                        # Prefer non-preprint DOI over preprint DOI when scores tie
                        w_doi = clean_doi(w.get("doi") or "")
                        bonus = 0.02 if (w_doi and not any(p in w_doi.lower() for p in PREPRINT_PATTERNS)) else 0.0
                        if sc + bonus > best_sc:
                            best_sc = sc + bonus
                            best = w
            if best:
                src = ((best.get("primary_location") or {}).get("source") or {})
                src_type = src.get("type") or ""
                v_disp = (src.get("display_name") or "").strip()
                if src_type == "repository" or "..." in v_disp:
                    v_disp = ""
                return {
                    "doi": clean_doi(best.get("doi") or ""),
                    "venue": v_disp,
                    "source_type": src_type,
                    "work_type": best.get("type") or "",
                    "abstract": reconstruct_oa_abstract(best.get("abstract_inverted_index")),
                    "year": best.get("publication_year"),
                }
    except Exception:
        pass

    # 2. Crossref search fallback
    try:
        r = requests.get(
            "https://api.crossref.org/works",
            params={"query.bibliographic": re.sub(r"[{}]", "", title), "rows": 5},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        if r.status_code == 200:
            for item in r.json().get("message", {}).get("items", []):
                ct = (item.get("title") or [""])[0]
                sc = title_sim(title, ct)
                if sc >= 0.86:
                    c_sur = cr_surnames(item)
                    if not bib_surnames or (bib_surnames & c_sur):
                        wtype = item.get("type") or ""
                        if wtype in ("proceedings", "journal", "journal-issue", "book"):
                            continue
                        cont = (item.get("container-title") or [""])[0]
                        abs_raw = clean_abstract_text(item.get("abstract") or "")
                        return {
                            "doi": clean_doi(item.get("DOI") or ""),
                            "venue": html.unescape(cont).strip(),
                            "source_type": "journal" if "journal" in wtype else "conference",
                            "work_type": wtype,
                            "abstract": abs_raw if not MASTHEAD_RE.search(abs_raw) else "",
                            "year": ((item.get("issued") or {}).get("date-parts") or [[None]])[0][0],
                        }
    except Exception:
        pass

    # 3. arXiv Atom API fallback (recovers DOI-less preprints and exact arXiv abstracts)
    try:
        clean_t = re.sub(r'["{}]', "", title).strip()
        r = requests.get(
            "http://export.arxiv.org/api/query",
            params={"search_query": f'ti:"{clean_t}"', "max_results": 3},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        if r.status_code == 200:
            for entry_xml in re.findall(r"<entry>([\s\S]*?)</entry>", r.text):
                tm = re.search(r"<title>([\s\S]*?)</title>", entry_xml)
                sm = re.search(r"<summary>([\s\S]*?)</summary>", entry_xml)
                im = re.search(r"<id>http[s]?://arxiv\.org/abs/([^<\s]+)</id>", entry_xml)
                if tm and im and title_sim(title, tm.group(1)) >= 0.88:
                    xml_authors = " and ".join(re.findall(r"<name>([\s\S]*?)</name>", entry_xml))
                    if not bib_surnames or (bib_surnames & extract_surnames(xml_authors)):
                        aid = re.sub(r"v\d+$", "", im.group(1).strip())
                        return {
                            "doi": f"10.48550/arxiv.{aid}",
                            "venue": "",
                            "source_type": "repository",
                            "work_type": "preprint",
                            "abstract": clean_abstract_text(sm.group(1) if sm else ""),
                            "year": None,
                        }
    except Exception:
        pass

    return None


def main():
    ap = argparse.ArgumentParser(description="Sanitize corrupted abstracts, links, DOIs, and venues")
    ap.add_argument("--bib", default="publications.bib")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False

    with open(args.bib, "r", encoding="utf-8") as f:
        raw_content = normalize_months(f.read())

    bib_db = bibtexparser.loads(raw_content, parser=parser)
    entries = bib_db.entries
    print(f"Loaded {len(entries)} entries from {args.bib}")

    # Step 0: Check CoRR duplicate Hwang2020Efficientlya -> Hwang2020
    ids_map = {e["ID"]: e for e in entries}
    merged_keys = {}
    if "Hwang2020Efficientlya" in ids_map and "Hwang2020" in ids_map:
        e_corr = ids_map["Hwang2020Efficientlya"]
        if "corr2003.html#abs-2003-08520" in (e_corr.get("url") or ""):
            merged_keys["Hwang2020Efficientlya"] = "Hwang2020"
            entries = [e for e in entries if e["ID"] != "Hwang2020Efficientlya"]
            for e in entries:
                if e.get("dvrk_cites"):
                    cites = [c.strip() for c in e["dvrk_cites"].split(" and ") if c.strip()]
                    updated = []
                    for c in cites:
                        target = merged_keys.get(c, c)
                        if target != e["ID"] and target not in updated:
                            updated.append(target)
                    e["dvrk_cites"] = " and ".join(sorted(updated))
            bib_db.entries = entries
            print("Merged DBLP CoRR duplicate 'Hwang2020Efficientlya' into 'Hwang2020' (redirected dvrk_cites).")

    s2_cache = load_local_s2_cache()

    # Count duplicate semanticscholar URLs and duplicate abstracts
    s2_counts = collections.Counter(
        e.get("semanticscholar", "").strip() for e in entries if e.get("semanticscholar")
    )
    abs_groups = collections.defaultdict(list)
    for e in entries:
        a = (e.get("abstract") or "").strip()
        if a:
            abs_groups[norm_text(a[:160])].append(e)

    # Batch-fetch OpenAlex for all existing DOIs + arXiv DOIs
    all_lookup_dois = []
    for e in entries:
        d = clean_doi(e.get("doi") or "")
        if d:
            all_lookup_dois.append(d)
        aid = extract_arxiv_id(e.get("arxiv") or "") or extract_arxiv_id(e.get("eprint") or "")
        if aid:
            all_lookup_dois.append(f"10.48550/arxiv.{aid}")

    print("Batch-verifying DOIs and arXiv IDs against OpenAlex...")
    oa_by_doi = batch_fetch_openalex_by_dois(all_lookup_dois)

    log_doi_fixed = []
    log_doi_removed = []
    log_arxiv_cleaned = []
    log_s2_cleaned = []
    log_abs_replaced = []
    log_abs_removed = []
    log_abs_filled = []
    log_venue_filled = []

    # Detect duplicate DOIs across entries and assign each duplicate DOI only to its best-matching entry
    doi_entries = collections.defaultdict(list)
    for e in entries:
        dl = clean_doi(e.get("doi") or "").lower()
        if dl:
            doi_entries[dl].append(e)
    doi_counts = {dl: len(elist) for dl, elist in doi_entries.items()}
    doi_owner = {}
    for dl, elist in doi_entries.items():
        if len(elist) == 1:
            doi_owner[dl] = elist[0]["ID"]
        else:
            ref_title = ""
            ref_year = None
            w = oa_by_doi.get(dl)
            if w:
                ref_title = w.get("title") or w.get("display_name") or ""
                ref_year = w.get("publication_year")
            else:
                cr = fetch_crossref_doi(dl)
                if cr:
                    ref_title = (cr.get("title") or [""])[0]
                    ref_year = ((cr.get("issued") or {}).get("date-parts") or [[None]])[0][0]
            if ref_title:
                best_e = max(
                    elist,
                    key=lambda cand: (
                        round(title_sim(cand.get("title", ""), ref_title), 3),
                        1 if (ref_year and str(cand.get("year", "")).strip() == str(ref_year)) else 0,
                    ),
                )
                if title_sim(best_e.get("title", ""), ref_title) >= 0.65:
                    doi_owner[dl] = best_e["ID"]

    for e in entries:
        eid = e["ID"]
        title = e.get("title", "")
        authors = e.get("author", "")
        etype = (e.get("ENTRYTYPE") or "").lower()

        # --- 1. Clean polluted semanticscholar (& tainted openaccesspdf) ---
        bad_s2_record = None
        s2_url = (e.get("semanticscholar") or "").strip()
        if s2_url:
            cached_s2 = s2_cache.get(s2_url)
            is_bad_s2 = False
            if cached_s2:
                if title_sim(title, cached_s2.get("title") or "") < 0.72:
                    is_bad_s2 = True
                    bad_s2_record = cached_s2
            if s2_counts[s2_url] > 1:
                is_bad_s2 = True
                if cached_s2:
                    bad_s2_record = cached_s2
            if is_bad_s2:
                del e["semanticscholar"]
                log_s2_cleaned.append(eid)
                oa_pdf = ((bad_s2_record or {}).get("openAccessPdf") or {}).get("url")
                if oa_pdf and e.get("openaccesspdf") == oa_pdf:
                    del e["openaccesspdf"]

        # --- 2. Verify & Clean arXiv / eprint ---
        for af in ("arxiv", "eprint", "arxivid"):
            aval = e.get(af)
            aid = extract_arxiv_id(aval) if aval else None
            if aid:
                arxiv_doi = f"10.48550/arxiv.{aid}"
                w_arx = oa_by_doi.get(arxiv_doi)
                if not w_arx:
                    # Single OpenAlex lookup in case canonical DOI superseded arxiv DOI
                    try:
                        r = requests.get(
                            f"https://api.openalex.org/works/https://doi.org/{arxiv_doi}",
                            headers={"User-Agent": USER_AGENT},
                            timeout=8,
                        )
                        if r.status_code == 200:
                            w_arx = r.json()
                            oa_by_doi[arxiv_doi] = w_arx
                    except Exception:
                        pass
                if w_arx:
                    wt = w_arx.get("title") or w_arx.get("display_name") or ""
                    if title_sim(title, wt) < 0.65:
                        old_v = e.pop(af)
                        log_arxiv_cleaned.append((eid, af, old_v, wt[:45]))

        # Restore clean arxiv URL if verified eprint exists and arxiv was purged
        if not e.get("arxiv") and e.get("eprint"):
            aid = extract_arxiv_id(e["eprint"])
            if aid:
                e["arxiv"] = f"https://arxiv.org/abs/{aid}"

        # --- 3. Verify & Repair DOI ---
        cur_doi = clean_doi(e.get("doi") or "")
        doi_valid = False
        verified_work = None

        if cur_doi:
            dl = cur_doi.lower()
            # Check if published journal entry has a lingering bioRxiv/arXiv preprint DOI
            has_formal_venue = bool(
                (e.get("journal") or e.get("booktitle"))
                and not any(p in ((e.get("journal") or "") + " " + (e.get("booktitle") or "")).lower() for p in PREPRINT_PATTERNS)
            )
            is_preprint_doi_on_pub = has_formal_venue and any(p in dl for p in ("10.1101/", "10.48550/arxiv", "21203/rs"))

            is_duplicate_loser = (doi_counts.get(dl, 0) > 1 and doi_owner.get(dl) != eid)

            w = oa_by_doi.get(dl)
            if w and not is_preprint_doi_on_pub and not is_duplicate_loser:
                wt = w.get("title") or w.get("display_name") or ""
                if title_sim(title, wt) >= 0.65:
                    doi_valid = True
                    src = ((w.get("primary_location") or {}).get("source") or {})
                    src_type = src.get("type") or ""
                    v_disp = (src.get("display_name") or "").strip()
                    if src_type == "repository" or "..." in v_disp:
                        v_disp = ""
                    verified_work = {
                        "doi": cur_doi,
                        "venue": v_disp,
                        "source_type": src_type,
                        "work_type": w.get("type") or "",
                        "abstract": reconstruct_oa_abstract(w.get("abstract_inverted_index")),
                    }
            elif not w and not is_preprint_doi_on_pub and not is_duplicate_loser:
                cr = fetch_crossref_doi(cur_doi)
                if cr:
                    ct = (cr.get("title") or [""])[0]
                    if title_sim(title, ct) >= 0.65:
                        doi_valid = True
                        cont = (cr.get("container-title") or [""])[0]
                        abs_raw = clean_abstract_text(cr.get("abstract") or "")
                        verified_work = {
                            "doi": cur_doi,
                            "venue": html.unescape(cont).strip(),
                            "source_type": "",
                            "work_type": cr.get("type") or "",
                            "abstract": abs_raw if not MASTHEAD_RE.search(abs_raw) else "",
                        }
                    else:
                        # Explicitly mismatched in Crossref (e.g. proceedings front-matter DOI)
                        doi_valid = False
                else:
                    # Unindexed future DOI (e.g. accepted 2026 ICRA DOI) — keep if unique
                    if doi_counts[dl] == 1:
                        doi_valid = True

            if not doi_valid:
                # Search for the true paper DOI
                time.sleep(0.08)
                found = search_verified_work(title, authors)
                if found and found.get("doi") and found["doi"].lower() != dl:
                    old_doi = cur_doi
                    e["doi"] = found["doi"]
                    if e.get("url") and old_doi.lower() in e["url"].lower():
                        e["url"] = f"https://doi.org/{found['doi']}"
                    verified_work = found
                    doi_valid = True
                    log_doi_fixed.append((eid, old_doi, found["doi"]))
                else:
                    # Keep book ISBN-DOI only for legitimate @inbook/@incollection chapters
                    is_book_chapter = etype in ("inbook", "incollection") and (
                        "10.1007/978-" in dl or "10.1016/c" in dl
                    )
                    if not is_book_chapter:
                        old_doi = e.pop("doi", None)
                        if e.get("url") and old_doi and old_doi.lower() in e["url"].lower():
                            del e["url"]
                        log_doi_removed.append((eid, old_doi))
        else:
            # Missing DOI: check if verified arXiv or search gives us verified abstract/DOI
            aid = extract_arxiv_id(e.get("arxiv") or "") or extract_arxiv_id(e.get("eprint") or "")
            if aid and f"10.48550/arxiv.{aid}" in oa_by_doi:
                w = oa_by_doi[f"10.48550/arxiv.{aid}"]
                if title_sim(title, w.get("title") or "") >= 0.70:
                    verified_work = {
                        "doi": "",
                        "venue": "",
                        "abstract": reconstruct_oa_abstract(w.get("abstract_inverted_index")),
                    }

        # --- 4. Check & Repair Abstract ---
        cur_abs = (e.get("abstract") or "").strip()
        if cur_abs:
            is_corrupt_abs = False
            reason = ""

            # (a) Masthead / editorial / front-matter boilerplate
            if MASTHEAD_RE.search(cur_abs):
                is_corrupt_abs = True
                reason = "masthead/front-matter"

            # (b) Matches a purged bad Semantic Scholar abstract
            if not is_corrupt_abs and bad_s2_record and bad_s2_record.get("abstract"):
                if title_sim(cur_abs[:250], bad_s2_record["abstract"][:250]) >= 0.65:
                    is_corrupt_abs = True
                    reason = "polluted S2 abstract"

            # (c) Duplicate abstract across unrelated authors
            if not is_corrupt_abs:
                grp = abs_groups.get(norm_text(cur_abs[:160]), [])
                if len(grp) > 1:
                    my_sur = extract_surnames(authors)
                    unrelated = any(not (my_sur & extract_surnames(other.get("author", ""))) for other in grp if other["ID"] != eid)
                    if unrelated:
                        is_corrupt_abs = True
                        reason = f"duplicated across {len(grp)} unrelated papers"

            # (d) Disagrees with verified OpenAlex/Crossref abstract (low word Jaccard)
            if not is_corrupt_abs and verified_work and len(verified_work.get("abstract") or "") > 100:
                jac = word_jaccard(cur_abs, verified_work["abstract"])
                if jac < 0.14:
                    is_corrupt_abs = True
                    reason = f"disagrees with verified DOI abstract (jaccard={jac:.2f})"

            # (e) Zero significant title-word overlap in abstract
            if not is_corrupt_abs:
                t_words = set(re.findall(r"[a-z]{4,}", norm_text(title))) - STOPWORDS
                a_words = set(re.findall(r"[a-z]{4,}", norm_text(cur_abs)))
                if len(t_words) >= 4 and len(t_words & a_words) == 0:
                    is_corrupt_abs = True
                    reason = "zero title-keyword overlap"

            if is_corrupt_abs:
                # Try to get verified abstract if we don't have one yet
                if not (verified_work and verified_work.get("abstract")):
                    time.sleep(0.08)
                    found = search_verified_work(title, authors)
                    if found and found.get("abstract"):
                        verified_work = found

                replacement_abs = (verified_work or {}).get("abstract") or ""
                if replacement_abs and len(replacement_abs) >= 60 and not MASTHEAD_RE.search(replacement_abs):
                    e["abstract"] = replacement_abs
                    log_abs_replaced.append((eid, reason, cur_abs[:50], replacement_abs[:55]))
                else:
                    del e["abstract"]
                    log_abs_removed.append((eid, reason, cur_abs[:60]))
            else:
                # Minor cleanup: strip leading "Abstract " if present
                cleaned_cur = re.sub(r"^\s*Abstract(?:[\s:.\-—]+(?=[A-Z]))", "", cur_abs)
                if cleaned_cur != cur_abs and len(cleaned_cur) > 60:
                    e["abstract"] = cleaned_cur
        else:
            # Missing abstract: fill if we already fetched a verified abstract (or query arXiv for preprints)
            if not (verified_work and verified_work.get("abstract")) and e.get("peer_reviewed") == "no":
                found = search_verified_work(title, authors)
                if found and found.get("abstract"):
                    verified_work = found
            replacement_abs = (verified_work or {}).get("abstract") or ""
            if replacement_abs and len(replacement_abs) >= 60 and not MASTHEAD_RE.search(replacement_abs):
                e["abstract"] = replacement_abs
                log_abs_filled.append((eid, replacement_abs[:55]))

        # Restore clean arxiv URL if verified eprint or 10.48550/arxiv DOI exists
        if not e.get("arxiv"):
            aid_restore = extract_arxiv_id(e.get("eprint") or "")
            if not aid_restore and "10.48550/arxiv." in (e.get("doi") or "").lower():
                aid_restore = extract_arxiv_id(e.get("doi") or "")
            if not aid_restore and "10.48550/arxiv." in ((verified_work or {}).get("doi") or "").lower():
                aid_restore = extract_arxiv_id(verified_work["doi"])
            if aid_restore:
                e["arxiv"] = f"https://arxiv.org/abs/{aid_restore}"

        # --- 5. Repair Missing / Malformed Venues ---
        for vf in ("journal", "booktitle"):
            if e.get(vf):
                v_clean = html.unescape(e[vf])
                v_clean = " ".join(v_clean.split())
                e[vf] = v_clean

        has_venue = bool(e.get("journal") or e.get("booktitle") or e.get("howpublished") or e.get("school"))
        if not has_venue and e.get("peer_reviewed") == "yes":
            v_info = None
            # Prefer Crossref container-title first (avoids OpenAlex repository names and ellipsis truncations)
            if e.get("doi"):
                cr = fetch_crossref_doi(clean_doi(e["doi"]))
                if cr and title_sim(title, (cr.get("title") or [""])[0]) >= 0.65:
                    cont = html.unescape((cr.get("container-title") or [""])[0]).strip()
                    if cont:
                        v_info = {"venue": cont, "work_type": cr.get("type") or ""}
            if not v_info and verified_work and verified_work.get("venue"):
                if verified_work.get("source_type") != "repository" and "..." not in verified_work["venue"]:
                    v_info = verified_work
            if not v_info:
                found = search_verified_work(title, authors)
                if found and found.get("venue"):
                    v_info = found
            if v_info and v_info.get("venue"):
                v_name = " ".join(v_info["venue"].split())
                if etype == "article" or "journal" in (v_info.get("work_type") or ""):
                    e["journal"] = v_name
                else:
                    e["booktitle"] = v_name
                log_venue_filled.append((eid, v_name))

        # Standardize theses missing school / entrytype
        if e.get("peer_reviewed") == "thesis":
            if etype not in ("phdthesis", "mastersthesis"):
                e["ENTRYTYPE"] = "phdthesis"
                etype = "phdthesis"
            if not e.get("school") and e.get("publisher"):
                pub_school = re.sub(r"\s+Library$", "", e["publisher"].strip(), flags=re.IGNORECASE)
                e["school"] = pub_school
                log_venue_filled.append((eid, pub_school))

        # Standardize pure unreviewed preprints that still have journal/booktitle = "arXiv preprint" or Research Square DOIs
        if e.get("peer_reviewed") == "no":
            aid = extract_arxiv_id(e.get("arxiv") or "") or extract_arxiv_id(e.get("eprint") or "") or extract_arxiv_id(e.get("doi") or "")
            for vf in ("journal", "booktitle"):
                v_low = (e.get(vf) or "").lower()
                if v_low in ("arxiv", "arxiv preprint", "arxiv.org"):
                    if aid:
                        e[vf] = f"arXiv preprint arXiv:{aid}"
                    else:
                        e[vf] = "arXiv preprint"
            if not (e.get("journal") or e.get("booktitle") or e.get("howpublished")):
                if aid:
                    e["howpublished"] = f"arXiv preprint arXiv:{aid}"
                elif "21203/rs" in (e.get("doi") or "").lower() or "researchsquare" in (e.get("url") or "").lower():
                    e["howpublished"] = "Research Square preprint"
                    log_venue_filled.append((eid, "Research Square preprint"))

    print("\n================ SANITIZATION SUMMARY ================")
    print(f"Total entries remaining:           {len(entries)}")
    print(f"Mismatched DOIs repaired:          {len(log_doi_fixed)}")
    print(f"Unresolvable bogus DOIs removed:   {len(log_doi_removed)}")
    print(f"Polluted arXiv fields removed:     {len(log_arxiv_cleaned)}")
    print(f"Mismatched S2 links removed:       {len(log_s2_cleaned)}")
    print(f"Corrupted abstracts replaced:      {len(log_abs_replaced)}")
    print(f"Corrupted abstracts deleted:       {len(log_abs_removed)}")
    print(f"Missing abstracts filled:          {len(log_abs_filled)}")
    print(f"Missing venues populated:          {len(log_venue_filled)}")

    if log_doi_fixed:
        print("\n--- Repaired DOIs ---")
        for eid, old_d, new_d in log_doi_fixed:
            print(f"  • {eid}: {old_d} -> {new_d}")
    if log_doi_removed:
        print("\n--- Removed Bogus DOIs ---")
        for eid, old_d in log_doi_removed:
            print(f"  • {eid}: removed {old_d}")
    if log_arxiv_cleaned:
        print("\n--- Removed Polluted arXiv Fields ---")
        for eid, af, old_v, wt in log_arxiv_cleaned:
            print(f"  • {eid}.{af}: removed '{old_v}' (was '{wt}')")
    if log_abs_replaced:
        print("\n--- Replaced Corrupted Abstracts ---")
        for eid, reason, old_a, new_a in log_abs_replaced:
            print(f"  • {eid} [{reason}]:\n      WAS: '{old_a}...'\n      NOW: '{new_a}...'")
    if log_abs_removed:
        print("\n--- Deleted Corrupted Abstracts (no verified replacement online) ---")
        for eid, reason, old_a in log_abs_removed:
            print(f"  • {eid} [{reason}]: removed '{old_a}...'")
    if log_venue_filled:
        print("\n--- Populated Missing Venues ---")
        for eid, v in log_venue_filled:
            print(f"  • {eid}: '{v}'")

    if not args.dry_run:
        def sort_key(entry):
            y, m, d = extract_pub_date(entry)
            return (-y, -m, -d, entry.get("title", "").lower(), entry.get("ID", "").lower())

        bib_db.entries.sort(key=sort_key)
        writer = BibTexWriter()
        writer.indent = "  "
        writer.order_entries_by = None
        writer.display_order = FIELD_ORDER
        writer.add_trailing_comma = True

        output = enforce_one_field_per_line(writer.write(bib_db))
        with open(args.bib, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"\nSuccessfully wrote sanitized bibliography to {args.bib}.")
    else:
        print("\n[Dry Run] No files were modified.")


if __name__ == "__main__":
    main()
