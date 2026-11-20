# CloudVeil — 5-minute viva demo script

Live URL: **https://cloudveil7k3.azurewebsites.net**

Demo accounts (seeded by `flask seed-demo`; password **`Demo@12345`**):

| Role | Email |
|---|---|
| Student | `asha.student@cloudveil.demo` |
| Officer | `officer.admissions@cloudveil.demo` |
| Admin | `demo.admin@cloudveil.demo` |

> If the app was idle, load the page once to warm it (first request after idle
> can take ~20 s on the B1 tier).

## 0 · Framing (20s)
"CloudVeil encrypts every uploaded document with its own key, stores only
ciphertext in Azure, protects each file key with a master key in Azure Key
Vault, and decrypts only after authentication + authorization. Every action is
audited." Open **How it works** to show the 6 steps.

## 1 · Student uploads an encrypted document (60s)
- Sign in as the **student**.
- Drag a PDF/txt into the dropzone, pick a category, **Encrypt & upload**.
- Point out the row: 🔒 badge, short **SHA-256**, size, **region** (uaenorth).
- Open the Azure portal (or `az storage blob list`) → the blob is
  `files/<uuid>.bin`, random name, and its bytes are ciphertext — not the file.

## 2 · Share with an officer, officer downloads (45s)
- On the document, **Share** → enter `officer.admissions@cloudveil.demo`.
- Sign out, sign in as the **officer** → **Shared with me** → **Download**.
- The file downloads and opens correctly: it was decrypted server-side only
  after the authorization check passed.

## 3 · Unauthorized access is blocked (30s)
- As a different student (or in the API), request another user's file →
  **403**, and show the **DOWNLOAD_DENIED** row in the admin audit log.

## 4 · Tamper detection (45s)
- Run `bash scripts/tamper_test.sh` (overwrites a blob via `az`, then downloads).
- It returns **409** and logs **INTEGRITY_FAIL** — AES-GCM caught the tampering.

## 5 · Admin: audit, stats, benchmark (45s)
- Sign in as **admin** → **Audit log** (filter by action, paginate).
- **Stats** → Chart.js: uploads/day, downloads vs denials, actions by type,
  storage by category.
- **Benchmark** → AES-GCM vs Key Vault wrap/unwrap vs blob I/O timings.

## 6 · Close (15s)
- Only ciphertext in Blob Storage (both regions); only wrapped keys in MySQL;
  the KEK never leaves Key Vault; everything audited; every push to `main`
  tests + deploys via GitHub Actions + OIDC.

## Reset / housekeeping
- Re-seed demo data: set App Service `RUN_SEED=true`, restart, then set it back
  to `false`.
- Save credit between demos: `az mysql flexible-server stop -g rg-cloudveil -n mysql-cloudveil7k3`.
- Tear everything down: `bash infra/teardown.sh` (asks to confirm).
