#!/usr/bin/env python3
"""scripts/live_benchmark.py — end-to-end client timings against the LIVE site.

Measures upload (encrypt+wrap+store) and download (fetch+unwrap+decrypt) latency
for several payload sizes, writes a CSV and PNG charts, and also records the
server-side /api/admin/benchmark numbers.

Requires: requests, matplotlib.  Reads config from ../.env.
Usage:  python scripts/live_benchmark.py [--repeats 3]
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import statistics
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "benchmarks"
SIZES = [100 * 1024, 1024 * 1024, 5 * 1024 * 1024]


def load_env() -> dict:
    env = {}
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v
    return env


def csrf_of(session: requests.Session) -> str:
    return session.cookies.get("cv_csrf", "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()

    env = load_env()
    base = os.environ.get("BASE_URL") or f"https://{env['WEBAPP_HOST']}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    s = requests.Session()
    email, pw = "bench.student@example.com", "Bench@12345"
    s.post(
        base + "/api/auth/register",
        json={"full_name": "Bench", "email": email, "password": pw},
        timeout=60,
    )
    s.post(base + "/api/auth/login", json={"email": email, "password": pw}, timeout=60)
    hdr = {"X-CSRF-Token": csrf_of(s)}

    rows = []
    for size in SIZES:
        ups, downs = [], []
        for _ in range(args.repeats):
            payload = os.urandom(size)
            t = time.perf_counter()
            r = s.post(
                base + "/api/files",
                headers=hdr,
                files={
                    "file": (
                        "bench.bin",
                        io.BytesIO(payload),
                        "application/octet-stream",
                    )
                },
                data={"category": "other"},
                timeout=600,
            )
            ups.append((time.perf_counter() - t) * 1000)
            fid = r.json()["file"]["id"]
            t = time.perf_counter()
            s.get(f"{base}/api/files/{fid}/download", timeout=600)
            downs.append((time.perf_counter() - t) * 1000)
            s.delete(f"{base}/api/files/{fid}", headers=hdr, timeout=60)
        rows.append(
            {
                "size_bytes": size,
                "size_label": human(size),
                "upload_ms_avg": round(statistics.mean(ups), 1),
                "download_ms_avg": round(statistics.mean(downs), 1),
            }
        )
        print(
            f"{human(size):>8}: upload {rows[-1]['upload_ms_avg']} ms, "
            f"download {rows[-1]['download_ms_avg']} ms"
        )

    csv_path = OUT_DIR / "live_benchmark.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print("wrote", csv_path)

    try:
        plot(rows)
    except Exception as exc:  # matplotlib optional
        print("skipped PNG (install matplotlib):", exc)
    return 0


def human(n: int) -> str:
    return f"{n // 1024} KB" if n < 1024 * 1024 else f"{n // 1024 // 1024} MB"


def plot(rows):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [r["size_label"] for r in rows]
    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(7, 4))
    w = 0.38
    ax.bar(
        [i - w / 2 for i in x],
        [r["upload_ms_avg"] for r in rows],
        w,
        label="Upload",
        color="#4f6ef7",
    )
    ax.bar(
        [i + w / 2 for i in x],
        [r["download_ms_avg"] for r in rows],
        w,
        label="Download",
        color="#10b981",
    )
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("latency (ms)")
    ax.set_title("CloudVeil end-to-end latency (client)")
    ax.legend()
    fig.tight_layout()
    out = OUT_DIR / "live_benchmark.png"
    fig.savefig(out, dpi=120)
    print("wrote", out)


if __name__ == "__main__":
    sys.exit(main())
