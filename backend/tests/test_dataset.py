"""
Validation test for CacheIQ evaluation dataset (data/eval/pairs.jsonl).
Owned by Builder 2 per PRD §5.2 and builder2.md task B2-P1.
"""
import json
from pathlib import Path


def test_eval_dataset_integrity():
    dataset_path = Path(__file__).resolve().parent.parent.parent / "data" / "eval" / "pairs.jsonl"
    assert dataset_path.exists(), f"Dataset file not found at {dataset_path}"

    valid_labels = {"same", "different"}
    valid_categories = {
        "paraphrase",
        "related_different",
        "time_sensitive",
        "numeric",
        "ambiguous",
        "exact_dup",
    }

    seen_ids = set()
    category_counts = {}
    label_counts = {}
    total = 0

    with open(dataset_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                row = json.loads(line)
            except json.JSONDecodeError as err:
                raise AssertionError(f"Invalid JSON on line {line_num}: {err}")

            # Check required keys
            for key in ("id", "query_a", "query_b", "label", "category", "note"):
                assert key in row, f"Missing key '{key}' on line {line_num}"

            row_id = row["id"]
            query_a = row["query_a"]
            query_b = row["query_b"]
            label = row["label"]
            category = row["category"]
            note = row["note"]

            # Unique ID
            assert row_id not in seen_ids, f"Duplicate id '{row_id}' on line {line_num}"
            seen_ids.add(row_id)

            # Non-empty strings
            assert isinstance(row_id, str) and row_id.strip(), f"Empty id on line {line_num}"
            assert isinstance(query_a, str) and query_a.strip(), f"Empty query_a on line {line_num}"
            assert isinstance(query_b, str) and query_b.strip(), f"Empty query_b on line {line_num}"
            assert isinstance(note, str) and note.strip(), f"Empty note on line {line_num}"

            # Query length <= 200 chars
            assert len(query_a) <= 200, f"query_a exceeds 200 chars on line {line_num} ({len(query_a)} chars)"
            assert len(query_b) <= 200, f"query_b exceeds 200 chars on line {line_num} ({len(query_b)} chars)"

            # Allowed labels and categories
            assert label in valid_labels, f"Invalid label '{label}' on line {line_num}"
            assert category in valid_categories, f"Invalid category '{category}' on line {line_num}"

            # Ambiguous pairs must be labelled 'different' per PRD §5.2
            if category == "ambiguous":
                assert label == "different", f"Ambiguous pair {row_id} must be labelled 'different'"

            total += 1
            category_counts[category] = category_counts.get(category, 0) + 1
            label_counts[label] = label_counts.get(label, 0) + 1

    print("\n--- Dataset Validation Summary ---")
    print(f"Total pairs: {total}")
    print("Categories:")
    for cat, count in sorted(category_counts.items()):
        print(f"  {cat}: {count}")
    print("Labels:")
    for lbl, count in sorted(label_counts.items()):
        print(f"  {lbl}: {count}")

    # PRD §5.2 targets: >= 120 pairs
    assert total >= 120, f"Expected at least 120 pairs, got {total}"
    assert category_counts.get("paraphrase", 0) >= 40, "Too few paraphrase pairs"
    assert category_counts.get("related_different", 0) >= 30, "Too few related_different pairs"
    assert category_counts.get("time_sensitive", 0) >= 10, "Too few time_sensitive pairs"
    assert category_counts.get("numeric", 0) >= 10, "Too few numeric pairs"
    assert category_counts.get("ambiguous", 0) >= 8, "Too few ambiguous pairs"
    assert category_counts.get("exact_dup", 0) >= 5, "Too few exact_dup pairs"
    print("\n[OK] All dataset integrity and distribution checks passed.")


if __name__ == "__main__":
    test_eval_dataset_integrity()
