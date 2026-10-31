"""CacheIQ Threshold Sweep Script (Phase P5).

Sweeps T_HIT in [0.70, 0.75, 0.80, 0.85, 0.90, 0.95] (with T_LOW = T_HIT - 0.10).
Uses REAL strategies, repository, and live PostgreSQL / pgvector.
Computes hit_rate, precision, false_hit_rate for:
- Strategy C: semantic_raw
- Strategy D: semantic_verified

Outputs:
- data/results/sweep.csv
- data/results/sweep.png (Matplotlib trade-off chart)
"""

import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import csv
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt

from backend.engine.eval.arena import load_dataset, PostgresArenaRunner

RESULTS_DIR = root_dir / "data" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
CSV_FILE = RESULTS_DIR / "sweep.csv"
PNG_FILE = RESULTS_DIR / "sweep.png"


def run_sweep():
    pairs = load_dataset()
    if not pairs:
        print("Error: No evaluation pairs found in data/eval/pairs.jsonl")
        return

    thresholds = [0.70, 0.75, 0.80, 0.85, 0.90, 0.95]
    records = []

    print("=" * 80)
    print("CacheIQ Threshold Sweep (Live Postgres / pgvector)")
    print(f"Dataset Size: {len(pairs)} pairs")
    print("=" * 80)
    print(f"{'T_HIT':<6} | {'T_LOW':<6} | Strategy C (Raw) Hit/Prec/False | Strategy D (Verified) Hit/Prec/False")
    print("-" * 80)

    for t_hit in thresholds:
        t_low = round(t_hit - 0.10, 2)
        runner = PostgresArenaRunner(t_hit=t_hit, t_low=t_low)

        row_c = runner.evaluate_strategy("semantic_raw", pairs)
        row_d = runner.evaluate_strategy("semantic_verified", pairs)

        raw_prec_str = f"{row_c.precision:.2f}" if row_c.precision is not None else "n/a"
        raw_false_str = f"{row_c.false_hit_rate:.2f}" if row_c.false_hit_rate is not None else "n/a"
        ver_prec_str = f"{row_d.precision:.2f}" if row_d.precision is not None else "n/a"
        ver_false_str = f"{row_d.false_hit_rate:.2f}" if row_d.false_hit_rate is not None else "n/a"

        records.append({
            "t_hit": t_hit,
            "t_low": t_low,
            "raw_hit_rate": row_c.hit_rate,
            "raw_precision": row_c.precision if row_c.precision is not None else "n/a",
            "raw_false_hit_rate": row_c.false_hit_rate if row_c.false_hit_rate is not None else "n/a",
            "ver_hit_rate": row_d.hit_rate,
            "ver_precision": row_d.precision if row_d.precision is not None else "n/a",
            "ver_false_hit_rate": row_d.false_hit_rate if row_d.false_hit_rate is not None else "n/a",
        })

        print(
            f"{t_hit:<6.2f} | {t_low:<6.2f} | "
            f"Hit: {row_c.hit_rate:<4.2f} Prec: {raw_prec_str:<4} False: {raw_false_str:<4} | "
            f"Hit: {row_d.hit_rate:<4.2f} Prec: {ver_prec_str:<4} False: {ver_false_str:<4}"
        )

    # Write CSV
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)
    print(f"\nSaved CSV results to: {CSV_FILE}")

    # Generate Chart
    try:
        t_vals = [r["t_hit"] for r in records]
        raw_hits = [r["raw_hit_rate"] for r in records]
        raw_false = [0.0 if r["raw_false_hit_rate"] == "n/a" else float(r["raw_false_hit_rate"]) for r in records]
        ver_hits = [r["ver_hit_rate"] for r in records]
        ver_false = [0.0 if r["ver_false_hit_rate"] == "n/a" else float(r["ver_false_hit_rate"]) for r in records]

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

        # Subplot 1: Hit Rate vs Threshold
        ax1.plot(t_vals, raw_hits, marker="o", color="#d97706", label="Strategy C (Semantic Raw)", linewidth=2)
        ax1.plot(t_vals, ver_hits, marker="s", color="#0d9488", label="Strategy D (Semantic Verified)", linewidth=2)
        ax1.axvline(x=0.85, color="#64748b", linestyle="--", alpha=0.7, label="Default T_HIT (0.85)")
        ax1.set_xlabel("Similarity Threshold (T_HIT)")
        ax1.set_ylabel("Hit Rate")
        ax1.set_title("Hit Rate vs Threshold")
        ax1.grid(True, linestyle=":", alpha=0.6)
        ax1.legend()

        # Subplot 2: False Hit Rate (Risk / Safety) vs Threshold
        ax2.plot(t_vals, raw_false, marker="o", color="#ba1a1a", label="Strategy C (Raw False Hits)", linewidth=2)
        ax2.plot(t_vals, ver_false, marker="s", color="#059669", label="Strategy D (Verified False Hits)", linewidth=2)
        ax2.axvline(x=0.85, color="#64748b", linestyle="--", alpha=0.7, label="Default T_HIT (0.85)")
        ax2.set_xlabel("Similarity Threshold (T_HIT)")
        ax2.set_ylabel("False Hit Rate (Wrong Answers)")
        ax2.set_title("False Hit Rate (Prefer MISS over wrong answer)")
        ax2.grid(True, linestyle=":", alpha=0.6)
        ax2.legend()

        plt.suptitle("CacheIQ Threshold Sweep & Verifier Safety Advantage (Live PostgreSQL / pgvector)", fontsize=13, fontweight="bold")
        plt.tight_layout()
        plt.savefig(PNG_FILE, dpi=150)
        plt.close()
        print(f"Saved sweep trade-off chart to: {PNG_FILE}")
    except Exception as e:
        print(f"Warning: Could not generate chart: {e}")


if __name__ == "__main__":
    run_sweep()
