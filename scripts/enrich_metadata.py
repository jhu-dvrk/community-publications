#!/usr/bin/env python3
import re
import time
import json
import requests
import shutil
import sys

# Reuse fetch logic
def fetch_with_retry(url, params, retries=3, delay=5):
    for i in range(retries):
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                sys.stdout.write(f"\rRate limited. Waiting {delay} seconds (Attempt {i+1}/{retries})...{' '*20}")
                sys.stdout.flush()
                time.sleep(delay)
                delay *= 2
            else:
                # 404 is fine, means not found
                if response.status_code == 404:
                    return None
                print(f"Error {response.status_code}: {response.text}")
                break
        except Exception as e:
            print(f"Request exception: {e}")
            time.sleep(delay)
    return None

def get_semantic_scholar_data(title, doi=None):
    base_url = "https://api.semanticscholar.org/graph/v1/paper"
    
    # Try searching by DOI first if available
    if doi:
        # Semantic Scholar DOI lookup
        url = f"{base_url}/DOI:{doi}"
        params = {"fields": "url,externalIds,title,abstract,openAccessPdf"}
        data = fetch_with_retry(url, params)
        if data:
            return data

    # Fallback to search by title
    if title:
        search_url = f"{base_url}/search"
        params = {
            "query": title,
            "fields": "url,externalIds,title,year,abstract,openAccessPdf",
            "limit": 1
        }
        data = fetch_with_retry(search_url, params)
        if data and data.get("data"):
            # Simple check to ensure it's likely the same paper (compare title similarity?)
            # For now, just take the top result if it exists
            return data["data"][0]
            
    return None

def enrich_bib(file_path):
    print(f"Enriching {file_path} with Semantic Scholar data...")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split into entries (using simple regex splitting on @ at start of line)
    # This is a bit fragile but works for well-formatted bib files (which ours is, thanks to the sorter)
    # We will reconstruct the file.
    
    entries = re.split(r'(?m)^@', content)
    enriched_entries = []
    updated_count = 0
    
    total_entries = len([e for e in entries if e.strip()])
    current_idx = 0

    for raw in entries:
        if not raw.strip():
            continue
            
        current_idx += 1
        print(f"Processing {current_idx}/{total_entries}...", end="\r")
        
        full_entry = "@" + raw
        
        # Extract fields
        title_match = re.search(r'title\s*=\s*[{"\'](.+?)[}"\'],?\s*\n', raw, re.IGNORECASE | re.DOTALL)
        if not title_match:
             title_match = re.search(r'title\s*=\s*[{"\'](.+?)[}"\']', raw, re.IGNORECASE)
        title = title_match.group(1) if title_match else ""
        title = re.sub(r'\s+', ' ', title).strip().strip('{}').strip('""')
        
        doi_match = re.search(r'doi\s*=\s*[{"\'](.+?)[}"\']', raw, re.IGNORECASE)
        doi = doi_match.group(1) if doi_match else None
        
        sem_match = re.search(r'semanticscholar\s*=\s*', raw, re.IGNORECASE)
        
        # Determine if we need to fetch
        # We fetch if ANY interesting field is missing, but for now let's be conservative
        # and fetch if we are modifying the entry or if specifically abstract is missing?
        # The user wants to add them. Let's check if they exist.
        
        abstract_match = re.search(r'abstract\s*=\s*', raw, re.IGNORECASE)
        pdf_match = re.search(r'openaccesspdf\s*=\s*', raw, re.IGNORECASE)
        
        needs_sem = sem_match is None
        needs_doi = doi is None
        needs_abs = abstract_match is None
        needs_pdf = pdf_match is None
        
        changes = []
        
        # We'll fetch if we are missing basic IDs OR if we are missing enriched metadata
        if (needs_sem or needs_doi or needs_abs or needs_pdf) and title:
            # Fetch data
            data = get_semantic_scholar_data(title, doi)
            
            if data:
                # Add Semantic Scholar URL
                if needs_sem and data.get("url"):
                    url = data.get("url")
                    changes.append(f"  semanticscholar = {{{url}}}")
                    
                # Add DOI if missing and found
                if needs_doi and data.get("externalIds") and data["externalIds"].get("DOI"):
                    new_doi = data["externalIds"]["DOI"]
                    changes.append(f"  doi = {{{new_doi}}}")
                    
                # Add Abstract
                if needs_abs and data.get("abstract"):
                    # Escape braces in abstract to be safe? 
                    # BibTeX abstracts can contain LaTeX. 
                    # Minimal escaping for now:
                    abstract = data["abstract"].replace("{", "\\{").replace("}", "\\}")
                    changes.append(f"  abstract = {{{abstract}}}")
                    
                # Add Open Access PDF
                if needs_pdf and data.get("openAccessPdf") and data["openAccessPdf"].get("url"):
                    pdf_url = data["openAccessPdf"]["url"]
                    changes.append(f"  openaccesspdf = {{{pdf_url}}}")
        
        if changes:
             updated_count += 1
             # Insert changes before the closing brace
             # Find last closing brace
             last_brace_idx = full_entry.rfind('}')
             if last_brace_idx != -1:
                 insertion = ",\n" + ",\n".join(changes) + "\n"
                 full_entry = full_entry[:last_brace_idx] + insertion + full_entry[last_brace_idx:]
                 
        enriched_entries.append(full_entry)
        
        # Be nice to API (Respect 1 RPS limit)
        time.sleep(1.5)

    print(f"\nUpdated {updated_count} entries.")
    
    # Backup
    shutil.copy(file_path, file_path + ".enriched.bak")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        # Join with double newline for clean formatting
        # Note: raw entries usually didn't have the preceding @, so we added it back.
        # But split remove the delimiter.
        # Wait, our loop added "@" back to `full_entry`.
        # However, the split logic `re.split` usually consumes delimiter unless captured.
        # Our raw entries do NOT start with @.
        # So full_entry is correct.
        
        for entry in enriched_entries:
            f.write(entry.strip())
            f.write("\n\n")

if __name__ == "__main__":
    file_path = "publications.bib"
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    enrich_bib(file_path)
