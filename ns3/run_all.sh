#!/usr/bin/env bash
# ns3/run_all.sh — run the CloudVeil parameter sweeps against a built ns-3.
#
#   NS3_DIR=/path/to/ns-3-dev OUT=$(pwd)/ns3/results/cloudveil_results.csv \
#     bash ns3/run_all.sh
#
# The scenario (scratch/cloudveil_sim) must already be built in NS3_DIR.
# Sweeps one variable at a time (delay, bandwidth, loss) for the two-node WAN
# (regions=1) and the multi-region replication path (regions=2).
set -euo pipefail

NS3_DIR="${NS3_DIR:?set NS3_DIR to your ns-3 directory}"
OUT="${OUT:-$(pwd)/ns3/results/cloudveil_results.csv}"
PAYLOAD="${PAYLOAD:-1048576}"

mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"

cd "$NS3_DIR"
run() { ./ns3 run "cloudveil_sim $* --payload=${PAYLOAD} --out=${OUT}"; }

for regions in 1 2; do
  echo "=== regions=${regions}: delay sweep (20..300 ms) ==="
  for d in 20 50 100 200 300; do
    run --regions="$regions" --delay="$d" --rate=20 --loss=0 --label="delay_r${regions}"
  done

  echo "=== regions=${regions}: bandwidth sweep (1..100 Mbps) ==="
  for r in 1 5 10 50 100; do
    run --regions="$regions" --delay=50 --rate="$r" --loss=0 --label="bw_r${regions}"
  done

  echo "=== regions=${regions}: loss sweep (0..5 %) ==="
  for l in 0 1 2 5; do
    run --regions="$regions" --delay=50 --rate=20 --loss="$l" --label="loss_r${regions}"
  done
done

echo "Results written to ${OUT}"
