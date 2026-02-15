#!/usr/bin/env python3
import re
import sys

def parse_bib_entries(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by @ at the start of a line (or start of file)
    # We use a lookahead to keep the @ delimiter
    # This regex looks for @ followed by an entry type, capturing the entry
    entries = []
    
    # Simple state machine to capture entries preserving comments/formatting if possible
    # But strictly speaking, for sorting, we might need to reconstruct content.
    # A safer approach for a large file is to read entry by entry.
    
    # Regex finditer approach
    # Matches @type{id, ... } including nested braces
    
    # Let's try a simpler approach: splitting by "\n@" or "^@" 
    # and then parsing the key fields 'year' and 'title' for sorting.
    
    raw_entries = re.split(r'(?m)^@', content)
    parsed_entries = []
    
    for raw in raw_entries:
        if not raw.strip():
            continue
            
        full_entry = "@" + raw
        
        # Extract Year
        year_match = re.search(r'year\s*=\s*[{"\']?(\d{4})[}"\']?', raw, re.IGNORECASE)
        year = int(year_match.group(1)) if year_match else 0
        
        # Extract Title
        title_match = re.search(r'title\s*=\s*[{"\'](.+?)[}"\'],?\s*\n', raw, re.IGNORECASE | re.DOTALL)
        if not title_match:
             # Try single line match
             title_match = re.search(r'title\s*=\s*[{"\'](.+?)[}"\']', raw, re.IGNORECASE)
             
        title = title_match.group(1) if title_match else ""
        # Clean title (remove newlines, extra braces)
        title = re.sub(r'\s+', ' ', title).strip().strip('{}').strip('""')
        
        parsed_entries.append({
            'content': full_entry,
            'year': year,
            'title': title
        })
        
    return parsed_entries

def sort_entries(entries):
    # Sort by Year (Descending) then Title (Ascending)
    # We use a tuple (year, title) for sorting keys.
    # Since we want Year DESC, we can use negative year or reverse=True.
    # But proper multi-key sort with mixed directions:
    # Sort by title first (ascending), then by year (descending) - relying on stable sort
    
    entries.sort(key=lambda x: x['title'].lower())
    entries.sort(key=lambda x: x['year'], reverse=True)
    
    return entries

def main():
    bib_file = 'publications.bib'
    if len(sys.argv) > 1:
        bib_file = sys.argv[1]
        
    print(f"Reading {bib_file}...")
    entries = parse_bib_entries(bib_file)
    print(f"Found {len(entries)} entries.")
    
    sorted_entries = sort_entries(entries)
    
    print("Sorting...")
    
    # Backup
    backup_file = bib_file + ".bak"
    with open(backup_file, 'w', encoding='utf-8') as f:
        with open(bib_file, 'r', encoding='utf-8') as original:
            f.write(original.read())
    print(f"Backed up to {backup_file}")
    
    with open(bib_file, 'w', encoding='utf-8') as f:
        for entry in sorted_entries:
            f.write(entry['content'].strip())
            f.write("\n\n")
            
    print(f"Successfully sorted {bib_file} by Year (Desc) and Title (Asc).")

if __name__ == '__main__':
    main()
