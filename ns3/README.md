# CloudVeil — NS-3 network evaluation

An **offline research component** (separate from the hosted app) that simulates
the WAN path between a CloudVeil client and an Azure region, and the
primary→secondary **replication** hop, to study how latency, bandwidth and
packet loss affect transfer performance for the document sizes CloudVeil handles.

This is a simulation of the *network*, not of the app's cryptography — the app's
own AES/Key-Vault/blob timings are measured separately (`docs/benchmarks.md`).

## What it does

`scenarios/cloudveil_sim.cc` builds a point-to-point topology:

- `--regions=1` — two nodes (client ↔ Azure region): the **WAN** case.
- `--regions=2` — three nodes (client ↔ primary ↔ secondary): the
  **multi-region** replication path.

A TCP bulk transfer of `--payload` bytes is sent; FlowMonitor records
throughput, mean latency and packet loss. `run_all.sh` sweeps one variable at a
time:

| Variable | Range |
|---|---|
| Link delay | 20, 50, 100, 200, 300 ms |
| Bandwidth | 1, 5, 10, 50, 100 Mbps |
| Packet loss | 0, 1, 2, 5 % |

`plot_results.py` turns the CSV into `latency_vs_delay.png`,
`throughput_vs_bandwidth.png` and `throughput_vs_loss.png` in `results/`.

## Running it

### Option A — GitHub Actions (recommended, no local install)

Trigger the **NS-3 Evaluation** workflow (`.github/workflows/ns3.yml`) from the
Actions tab (`workflow_dispatch`). It builds ns-3, runs the sweeps, generates the
charts, and uploads `results/` as a downloadable artifact.

```bash
gh workflow run ns3.yml
# when finished:
gh run download --name ns3-results --dir ns3/results
```

### Option B — locally on Ubuntu / WSL2

```bash
# 1. Build tools
sudo apt-get update
sudo apt-get install -y g++ cmake ninja-build python3 python3-pip
pip install matplotlib

# 2. ns-3
wget https://www.nsnam.org/releases/ns-allinone-3.42.tar.bz2
tar xjf ns-allinone-3.42.tar.bz2
cd ns-allinone-3.42/ns-3.42
cp /path/to/cloudveil/ns3/scenarios/cloudveil_sim.cc scratch/
./ns3 configure -d optimized \
  --enable-modules core,network,internet,point-to-point,applications,flow-monitor
./ns3 build
cd /path/to/cloudveil

# 3. Run sweeps + plot
NS3_DIR="/path/to/ns-allinone-3.42/ns-3.42" \
  OUT="$PWD/ns3/results/cloudveil_results.csv" bash ns3/run_all.sh
python ns3/plot_results.py ns3/results/cloudveil_results.csv
```

## Output

- `results/cloudveil_results.csv` — one row per run.
- `results/latency_vs_delay.png`, `throughput_vs_bandwidth.png`,
  `throughput_vs_loss.png`.
