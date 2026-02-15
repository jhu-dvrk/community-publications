#!/usr/bin/env python3
import re
import sys
import shutil

def migrate_urls(file_path):
    print(f"Migrating URLs in {file_path}...")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by entries to safely process
    # Using regex to find entries
    # We will process line by line for simplicity and safety against regex limits on large files,
    # but we need to know we are inside an entry.
    
    # Actually, a safer way for this specific task (moving a field value) 
    # might be to iterate through lines.
    
    new_lines = []
    
    # We need to track if we are inside an entry to maybe reorder or just replace.
    # Simple replacement strategy:
    # Look for "url = {.*?ieeexplore.ieee.org.*?}" and change key to "ieeexplore ="
    
    # Regex for url field with IEEE link
    # url\s*=\s*\{.*ieeexplore\.ieee\.org.*\}
    
    lines = content.splitlines()
    migrated_count = 0
    
    for line in lines:
        # distinct check for url field containing ieee
        # We assume standard formatting from our previous sort script: "  url={...},"
        # But we should be robust to spacing.
        
        match = re.search(r'^\s*url\s*=\s*[\{"](.*?ieeexplore\.ieee\.org.*?)[\}"]', line, re.IGNORECASE)
        if match:
             # Found an IEEE URL in the url field
             # Replace 'url' with 'ieeexplore'
             new_line = re.sub(r'^\s*url\s*=', '  ieeexplore =', line, flags=re.IGNORECASE)
             new_lines.append(new_line)
             migrated_count += 1
        else:
            new_lines.append(line)
            
    # Write back
    backup_file = file_path + ".migrated.bak"
    shutil.copy(file_path, backup_file)
    print(f"Backup created at {backup_file}")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(new_lines))
        # Add trailing newline
        f.write("\n")
        
    print(f"Migrated {migrated_count} URLs to 'ieeexplore' field.")

if __name__ == "__main__":
    bib_file = "publications.bib"
    if len(sys.argv) > 1:
        bib_file = sys.argv[1]
    
    migrate_urls(bib_file)
