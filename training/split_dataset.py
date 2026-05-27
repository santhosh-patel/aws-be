
import json
import random
import os
from pathlib import Path
from typing import List, Dict, Any

def load_data(file_path: Path) -> List[Dict[str, Any]]:
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_data(data: List[Dict[str, Any]], file_path: Path):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(data)} entries to {file_path.name}")

def main():
    # Define paths
    base_dir = Path(__file__).resolve().parent.parent
    processed_dir = base_dir / "datasets" / "processed"
    input_file = processed_dir / "all_merged.json"
    
    if not input_file.exists():
        print(f"Error: {input_file} not found. Run prepare_dataset.py first.")
        return

    # Load data
    print(f"Loading data from {input_file}...")
    data = load_data(input_file)
    total_count = len(data)
    
    # Shuffle data
    random.shuffle(data)
    
    # Split ratios
    train_ratio = 0.7
    val_ratio = 0.15
    test_ratio = 0.15
    
    train_end = int(total_count * train_ratio)
    val_end = train_end + int(total_count * val_ratio)
    
    train_data = data[:train_end]
    val_data = data[train_end:val_end]
    test_data = data[val_end:]
    
    # Save splits
    save_data(train_data, processed_dir / "train.json")
    save_data(val_data, processed_dir / "val.json")
    save_data(test_data, processed_dir / "test.json")
    
    print("\nDataset split complete:")
    print(f"Total: {total_count}")
    print(f"Train: {len(train_data)} ({len(train_data)/total_count:.1%})")
    print(f"Val:   {len(val_data)} ({len(val_data)/total_count:.1%})")
    print(f"Test:  {len(test_data)} ({len(test_data)/total_count:.1%})")

if __name__ == "__main__":
    main()
