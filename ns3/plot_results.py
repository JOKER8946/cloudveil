#!/usr/bin/env python3
"""ns3/plot_results.py — chart the CloudVeil NS-3 sweep results.

Reads the CSV produced by run_all.sh and writes latency / throughput / packet
-loss PNG charts into the same results directory.

Usage:  python ns3/plot_results.py [ns3/results/cloudveil_results.csv]
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

COLORS = {"1": "#4f6ef7", "2": "#ef4444"}


def load(path: Path):
    rows = []
    with path.open() as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def series(rows, label_prefix, x_key, y_key):
    """Return {regions: [(x, y), ...]} for rows whose label starts with prefix."""
    out = defaultdict(list)
    for r in rows:
        if r["label"].startswith(label_prefix):
            out[r["regions"]].append((float(r[x_key]), float(r[y_key])))
    for reg in out:
        out[reg].sort()
    return out


def line_chart(data, title, xlabel, ylabel, outfile):
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for reg, pts in sorted(data.items()):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        name = "Two-node WAN" if reg == "1" else "Multi-region"
        ax.plot(xs, ys, marker="o", color=COLORS.get(reg, "#10b981"), label=name)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(outfile, dpi=120)
    plt.close(fig)
    print("wrote", outfile)


def main() -> int:
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "ns3/results/cloudveil_results.csv"
    )
    if not csv_path.exists():
        print(f"no results at {csv_path}", file=sys.stderr)
        return 1
    rows = load(csv_path)
    out_dir = csv_path.parent

    line_chart(
        series(rows, "delay_", "delay_ms", "mean_delay_ms"),
        "Latency vs link delay",
        "one-way link delay (ms)",
        "measured mean latency (ms)",
        out_dir / "latency_vs_delay.png",
    )
    line_chart(
        series(rows, "bw_", "rate_mbps", "throughput_mbps"),
        "Throughput vs link bandwidth",
        "link bandwidth (Mbps)",
        "achieved throughput (Mbps)",
        out_dir / "throughput_vs_bandwidth.png",
    )
    line_chart(
        series(rows, "loss_", "loss_pct", "throughput_mbps"),
        "Throughput vs packet loss",
        "injected packet loss (%)",
        "achieved throughput (Mbps)",
        out_dir / "throughput_vs_loss.png",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
