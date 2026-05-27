
import json
import glob
import os
import sys
from pathlib import Path
from typing import List, Dict, Any

def load_json(file_path: str) -> List[Dict[str, Any]]:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return []

def validate_entry(entry: Dict[str, Any]) -> bool:
    required_keys = ["query", "expected_tool", "expected_domain"]
    return all(key in entry for key in required_keys)

def main():
    # Define paths
    base_dir = Path(__file__).resolve().parent.parent
    raw_dir = base_dir / "datasets" / "raw"
    processed_dir = base_dir / "datasets" / "processed"
    
    # Create processed directory if it doesn't exist
    processed_dir.mkdir(parents=True, exist_ok=True)
    
    # Find all JSON files in raw directory
    json_files = glob.glob(str(raw_dir / "*.json"))
    
    if not json_files:
        print(f"No JSON files found in {raw_dir}")
        sys.exit(1)
        
    print(f"Found {len(json_files)} raw dataset files")
    
    all_data = []
    total_entries = 0
    valid_entries = 0
    
    for file_path in json_files:
        print(f"Processing {os.path.basename(file_path)}...")
        data = load_json(file_path)
        
        file_valid_count = 0
        for entry in data:
            total_entries += 1
            if validate_entry(entry):
                all_data.append(entry)
                valid_entries += 1
                file_valid_count += 1
            else:
                print(f"Skipping invalid entry in {os.path.basename(file_path)}: {entry.get('query', 'UNKNOWN')}")
                
        print(f"  -> Added {file_valid_count} entries")

    # Remove duplicates (based on query string)
    unique_data = []
    seen_queries = set()
    
    for entry in all_data:
        query = entry["query"].strip().lower()
        if query not in seen_queries:
            unique_data.append(entry)
            seen_queries.add(query)
    
    duplicate_count = len(all_data) - len(unique_data)
    print(f"Removed {duplicate_count} duplicate queries")
    
    output_path = processed_dir / "all_merged.json"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(unique_data, f, indent=2, ensure_ascii=False)
        
    print(f"\nSuccessfully saved {len(unique_data)} entries to {output_path}")
    print(f"Total processed: {total_entries}, Valid: {valid_entries}, Final Unique: {len(unique_data)}")

if __name__ == "__main__":
    main()
