# CloudVeil — Performance benchmarks

All numbers were captured from the **live** deployment on Azure App Service
(Linux **B1**, Python 3.12) in **UAE North**, with Key Vault and Blob Storage in
the same region, via `POST /api/admin/benchmark`. Synthetic random payloads are
used and written to temporary blobs that are deleted immediately — they are
never stored as user files.

## Key Vault (RSA-OAEP-256, per operation)

| Operation | Latency |
|---|---|
| Wrap data key | **≈ 40 ms** |
| Unwrap data key | **≈ 51 ms** |

The KEK wrap/unwrap cost is independent of file size (the data key is always 32
bytes). It is paid once per upload and once per download.

## Server-side timings by payload size

| Size | AES-GCM encrypt | AES-GCM decrypt | Blob put | Blob get |
|---|---|---|---|---|
| 100 KB | 0.12 ms | 0.10 ms | 48 ms | 12 ms |
| 1 MB | 1.10 ms | 1.08 ms | 57 ms | 50 ms |
| 10 MB | 23 ms | 37 ms | 142 ms | 295 ms |
| 50 MB | 351 ms | 442 ms | 921 ms | 1438 ms |

Observations:

- **AES-256-GCM is cheap** — even at 50 MB the symmetric crypto is well under
  half a second; throughput is roughly 120–140 MB/s on the B1 tier.
- **Blob I/O dominates** large transfers, as expected for network storage.
- **End-to-end upload** ≈ `AES encrypt + KEK wrap + blob put` and **download** ≈
  `blob get + KEK unwrap + AES decrypt + SHA-256 verify`; for a typical document
  (≤ 1 MB) the whole operation is well under ~150 ms of server work plus request
  latency.

## Reproducing

Server-side (admin session required):

```bash
curl -b admin.jar -H "X-CSRF-Token: <csrf>" -H 'Content-Type: application/json' \
  -X POST https://<app>.azurewebsites.net/api/admin/benchmark \
  --data '{"sizes":[102400,1048576,10485760,52428800]}'
```

Client end-to-end (upload + download round trips, writes CSV + PNG to
`docs/benchmarks/`):

```bash
pip install requests matplotlib
python scripts/live_benchmark.py --repeats 3
```

The admin dashboard **Benchmark** view runs the same endpoint and charts the
results with Chart.js.
