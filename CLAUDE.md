# CLAUDE.md — CloudVeil (SecureCrossCloud)

You are building **CloudVeil**, a fully hosted web platform on Microsoft Azure that encrypts every
uploaded file with its own unique key, stores only ciphertext in Azure Blob Storage, protects each
file key with a master key in Azure Key Vault (envelope encryption), and decrypts only for users who
pass authentication + role/permission checks. Every action is audited.

This is an MCA final-year project. Code quality, security correctness, and demonstrability all matter.
Build the **entire** project by following the phases below in order.

---

## 0. Working rules (read first)

1. **Cloud-only workflow. There is no local development environment.** Do not install or run MySQL,
   XAMPP, a local web server, or local storage/key emulators. The app only ever runs on Azure App Service.
   - Code is written in this folder → committed → pushed to GitHub → **GitHub Actions** runs tests,
     builds Tailwind CSS, and deploys to Azure App Service.
   - Verify each phase **on the live URL** (`curl`, the browser, `az webapp log tail`).
   - Unit tests run in CI using SQLite in-memory and in-memory fakes defined **only in `tests/`**.
     If Python is available locally you may also run `pytest` before pushing, but never depend on it.
2. Work **phase by phase** (Section 9). At the end of each phase: push, wait for the CI run to pass
   (`gh run watch`), verify on the live site, and print a short summary of what was done and what is next.
3. **Ask the user before** any command that creates, changes or deletes paid Azure resources, and
   before anything destructive (dropping databases, deleting resource groups, force-pushing).
   Show the exact command first.
4. **Never** print, log, commit or store: plaintext data keys, passwords, JWT secrets, connection
   strings. Secrets live only in `.env` (gitignored, read by infra scripts) and in App Service
   application settings / GitHub Actions secrets.
5. Read configuration only from environment variables via `app/config.py`. No hard-coded names.
6. If something in Azure fails (region quota, SKU unavailable, permission denied), stop, explain the
   error in plain words, and propose a fix — do not silently change the architecture.
7. Keep the stack fixed (Section 2). No React, Node backends, Docker, or other databases.
8. Prefer small, readable modules with docstrings. This code will be read by examiners.

---

## 1. Architecture

```
Developer machine: Claude Code + git + az CLI + gh CLI   (writes code, runs infra scripts — never runs the app)
   │ git push
   ▼
GitHub ── Actions: test (pytest) → build Tailwind → deploy (OIDC) ──►

Browser (HTML + Tailwind + Vanilla JS + Chart.js)
   │  HTTPS (TLS, App Service managed certificate, HTTPS-only)
   ▼
Azure App Service (Linux, Python 3.12) — Flask REST API + static frontend (gunicorn)
   │  System-assigned Managed Identity (DefaultAzureCredential) — no secrets for Azure services
   ├──► Azure Key Vault (RBAC mode) — RSA-3072 KEK "cloudveil-kek": wrapKey / unwrapKey
   ├──► Azure Blob Storage (primary region, private container "encrypted-files") — ciphertext only
   │        └── Object Replication ──► Storage account in secondary region (ciphertext copy)
   ├──► Azure Database for MySQL Flexible Server (TLS required) — users, file metadata, permissions, audit
   └──► Application Insights / Azure Monitor — telemetry; Key Vault + Storage diagnostic logs

NS-3 (separate, offline research component) — latency / throughput / packet loss simulation.
```

The app code has **only Azure implementations** (`AzureKeyVaultProvider`, `AzureBlobStorage`) behind
small interfaces (`KeyProvider`, `StorageBackend`) so tests can inject fakes from `tests/fakes.py`.

---

## 2. Tech stack (fixed)

- **Backend:** Python 3.12, Flask (app factory + blueprints), Flask-SQLAlchemy, Flask-Migrate,
  PyMySQL, `cryptography`, `bcrypt`, `PyJWT`, Flask-Limiter, gunicorn.
- **Azure SDKs:** `azure-identity`, `azure-keyvault-keys`, `azure-storage-blob`,
  `azure-monitor-opentelemetry`.
- **Frontend:** HTML5, Tailwind CSS (built in CI with the Tailwind standalone CLI → `app/static/css/app.css`),
  Vanilla JS (ES modules, `fetch`), Chart.js (vendored file in `static/vendor/`).
- **Tests (CI):** pytest, pytest-cov, SQLite in-memory. **Lint:** ruff, black (checked in CI).
- **Infra:** Azure CLI scripts (`infra/*.sh` bash + `.ps1` equivalents), run from the developer machine.
- **CI/CD:** GitHub Actions → Azure App Service via OIDC federated credential.
- **Evaluation:** NS-3 (C++ scenarios + Python plotting) in `ns3/`.

---

## 3. Repository layout

```
cloudveil/
├── CLAUDE.md  SETUP.md  README.md  .env.example  .gitignore  requirements.txt  requirements-dev.txt
├── wsgi.py                         # gunicorn entry: wsgi:app
├── startup.sh                      # App Service startup: flask db upgrade → optional seed → gunicorn
├── tailwind.config.js  app/static/src/input.css
├── app/
│   ├── __init__.py                 # create_app()
│   ├── config.py                   # ProdConfig / TestConfig from env
│   ├── extensions.py               # db, migrate, limiter
│   ├── models.py                   # User, File, FilePermission, AuditLog
│   ├── cli.py                      # flask seed-demo, flask create-admin, flask rewrap-keys
│   ├── auth/        (routes.py, service.py, decorators.py)
│   ├── files/       (routes.py, service.py)
│   ├── admin/       (routes.py)    # users, audit, stats, benchmark
│   ├── crypto/      (envelope.py, integrity.py, keyprovider.py)
│   ├── storage/     (blob.py)
│   ├── audit/       (logger.py)
│   ├── certs/       (Azure MySQL CA bundle .pem)
│   ├── templates/
│   └── static/      (css/, js/, img/, vendor/, src/)
├── migrations/
├── tests/    conftest.py  fakes.py  test_crypto.py  test_auth.py  test_files.py  test_authz.py  test_audit.py
├── scripts/  live_smoke_test.sh  live_benchmark.py  tamper_test.sh
├── infra/    provision.sh/.ps1  roles.sh  github_oidc.sh  app_settings.sh  replication.sh  diagnostics.sh  teardown.sh  README.md
├── .github/workflows/deploy.yml
├── ns3/      scenarios/*.cc  run_all.sh  plot_results.py  results/  README.md
└── docs/     architecture.md  security-design.md  api.md  testing-evidence.md  benchmarks.md  demo-script.md
```

---

## 4. Data model (MySQL, utf8mb4)

- **users**: `id` PK, `full_name`, `email` UNIQUE, `password_hash` (bcrypt, cost 12),
  `role` ENUM('student','officer','admin'), `is_active`, `failed_logins`, `locked_until`, `created_at`.
- **files**: `id` CHAR(36) UUID PK, `owner_id` FK, `original_name`, `content_type`, `size_bytes`,
  `blob_name` (random UUID, never the original name), `nonce` VARBINARY(12),
  `wrapped_key` VARBINARY(512), `kek_key_id` (full Key Vault key id incl. version),
  `wrap_alg` ('RSA-OAEP-256'), `sha256` CHAR(64), `primary_region`, `category`
  ('marks_card','id_document','transfer_certificate','application_form','other'),
  `is_deleted`, `created_at`.
- **file_permissions**: `id`, `file_id` FK, `grantee_id` FK, `can_download` BOOL,
  `granted_by` FK, `expires_at` NULL, `created_at`. UNIQUE(file_id, grantee_id).
- **audit_logs**: `id` BIGINT PK, `user_id` NULL FK, `action` ENUM('LOGIN','LOGIN_FAILED','LOGOUT',
  'UPLOAD','DOWNLOAD','DOWNLOAD_DENIED','SHARE','REVOKE','DELETE','INTEGRITY_FAIL','KEY_UNWRAP_FAIL',
  'ADMIN_ACTION'), `file_id` NULL, `status` ('success','denied','error'), `ip`, `user_agent`,
  `details` JSON, `created_at`. Append-only (no update/delete routes).

No column ever holds a plaintext data key.

---

## 5. Cryptography spec (implement exactly)

**Encrypt (upload):**
1. `file_id = uuid4()`; `dek = AESGCM.generate_key(bit_length=256)`; `nonce = os.urandom(12)`.
2. `sha256 = hashlib.sha256(plaintext).hexdigest()`.
3. `ciphertext = AESGCM(dek).encrypt(nonce, plaintext, aad)` with
   `aad = f"cloudveil:v1:{file_id}:{owner_id}".encode()`.
4. `wrapped_key = key_provider.wrap(dek)` → Key Vault `CryptographyClient.wrap_key(KeyWrapAlgorithm.rsa_oaep_256, dek)`;
   store the returned key id (with version) in `kek_key_id`.
5. Upload `ciphertext` to blob `files/{blob_name}.bin`, metadata `{file_id, v: "1"}` only.
6. Insert `files` row; write `UPLOAD` audit; drop the `dek` reference.

**Decrypt (download):** authorize first (Section 6) → fetch blob → `dek = key_provider.unwrap(wrapped_key, kek_key_id)`
→ `AESGCM(dek).decrypt(nonce, ciphertext, aad)` (on `InvalidTag` → audit `INTEGRITY_FAIL`, HTTP 409)
→ recompute SHA-256, compare with `hmac.compare_digest` → stream with `Content-Disposition: attachment`
→ audit `DOWNLOAD`.

**Limits:** `MAX_UPLOAD_MB` (default 50) via Flask `MAX_CONTENT_LENGTH`. Allowed: pdf, png, jpg, jpeg,
docx, txt (check extension **and** magic bytes).

**Key rotation:** `flask rewrap-keys` re-wraps all DEKs with the newest KEK version without touching blobs.

---

## 6. Authentication & authorization

- Login with email + bcrypt. JWT (HS256, 30-min expiry; claims sub, role, jti) in an
  **HttpOnly, Secure, SameSite=Strict** cookie. CSRF double-submit header `X-CSRF-Token` on
  state-changing requests.
- Flask-Limiter (storage: in-memory is acceptable for a single instance; document this):
  5 login attempts/min/IP; lock account 15 min after 5 consecutive failures.
- Roles:
  - **student** — upload own files; list/download/delete own files; share own files with officers.
  - **officer** — list/download files explicitly shared with them (unexpired permission) only.
  - **admin** — manage users/roles, view audit logs and stats, revoke permissions, run benchmark.
    **No automatic decrypt access** to student files; self-grant only via audited `ADMIN_ACTION`.
- `can_download(user, file)` lives only in `files/service.py`, unit-tested for every
  role × ownership × permission × expiry combination. Every denial → `DOWNLOAD_DENIED` audit + 403.
- Security headers: HSTS, CSP (self only), X-Content-Type-Options, X-Frame-Options DENY, Referrer-Policy.
- Trust `X-Forwarded-For` from App Service via `ProxyFix` for correct client IPs in audit logs.

---

## 7. REST API

| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/api/auth/register` | public (creates student) | register |
| POST | `/api/auth/login` · `/api/auth/logout` | public / any | session |
| GET  | `/api/auth/me` | any | current user |
| POST | `/api/files` | student | upload + encrypt (multipart, `category`) |
| GET  | `/api/files` | student | my files |
| GET  | `/api/files/shared` | officer | shared with me |
| GET  | `/api/files/<id>` | authorized | metadata |
| GET  | `/api/files/<id>/download` | authorized | decrypt + stream |
| POST | `/api/files/<id>/share` | owner | `{grantee_email, expires_at?}` |
| DELETE | `/api/files/<id>/share/<grantee_id>` | owner/admin | revoke |
| DELETE | `/api/files/<id>` | owner | soft delete + delete blob |
| GET/PATCH | `/api/admin/users[/<id>]` | admin | manage users |
| GET  | `/api/admin/audit?action=&user=&from=&to=&page=` | admin | audit log |
| GET  | `/api/admin/stats` | admin | chart data |
| POST | `/api/admin/benchmark` | admin | server-side timings: AES-GCM enc/dec, wrap/unwrap, blob put/get for 100 KB–50 MB synthetic data (never stored as user files) |
| GET  | `/api/health` | public | liveness: DB, Key Vault, Blob reachability (no secrets in output) |

JSON errors: `{"error": {"code": "...", "message": "..."}}`. Document in `docs/api.md`.

---

## 8. Frontend pages

Responsive Tailwind UI, branded "CloudVeil — Secure Data. Anywhere."
- **Login / Register.**
- **Student dashboard:** drag-and-drop upload (category, progress bar); "My Documents" table (name,
  category, size, date, 🔒 encrypted badge, short SHA-256, region); Share modal (officer email, optional
  expiry); revoke; delete.
- **Officer dashboard:** "Shared with me" with download buttons.
- **Admin:** users (role change, activate/deactivate); audit log with filters + pagination; stats with
  Chart.js (uploads/day, downloads vs denials, actions by type, storage by category); benchmark page
  that runs `/api/admin/benchmark` and charts results.
- **"How it works"** page: Encrypt → Store → Replicate → Authorize → Decrypt → Audit (for the viva).

---

## 9. Phases and acceptance criteria

**Phase 1 — Scaffold + CI skeleton.** Repo layout, app factory, config, `.env.example`, `.gitignore`
(includes `.env`), `/api/health` (simple), `tests/` with one passing test, `deploy.yml` with a test job
only (lint + pytest). Create/push to the GitHub repo in `.env`. ✅ CI green on GitHub.

**Phase 2 — Provision Azure (ask before running).** Idempotent `infra/provision.sh` (+ `.ps1`) using `.env`:
resource group; Key Vault (RBAC mode, soft-delete + purge protection) + RSA-3072 key `cloudveil-kek`;
primary storage (StorageV2, Standard_LRS, min TLS 1.2, public blob access off, versioning + change feed)
+ container `encrypted-files`; secondary storage in `AZURE_SECONDARY_REGION` (versioning) + same container;
MySQL Flexible Server (Burstable B1ms, TLS required, DB `cloudveil`, firewall rule "Allow Azure services" only);
Log Analytics + Application Insights; App Service plan (Linux B1) + Web App (Python 3.12, HTTPS-only,
system-assigned identity, startup command `bash startup.sh`).
`infra/roles.sh`: web app identity → **Key Vault Crypto User** (vault) + **Storage Blob Data Contributor**
(primary account); signed-in user → **Key Vault Crypto Officer** (to create/rotate the KEK) +
**Storage Blob Data Contributor** (for the tamper test).
`infra/app_settings.sh`: push DB settings, `KEYVAULT_URL`, `KEK_NAME`, `STORAGE_ACCOUNT_URL`,
`STORAGE_CONTAINER`, `PRIMARY_REGION`, generated `JWT_SECRET`, `APPLICATIONINSIGHTS_CONNECTION_STRING`,
`SCM_DO_BUILD_DURING_DEPLOYMENT=true`, `RUN_SEED=false` to App Service (values from `.env` / az output,
never echoed). `infra/github_oidc.sh`: Entra app registration + federated credential for the repo's
`main` branch + role on the resource group; set GitHub secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
`AZURE_SUBSCRIPTION_ID` with `gh secret set`. ✅ summary of resource names printed; non-secret names
written back to `.env`.

**Phase 3 — First live deploy.** Extend `deploy.yml`: test → build Tailwind → `azure/login` (OIDC) →
`azure/webapps-deploy`. `startup.sh` runs `flask db upgrade`, then `flask seed-demo` if `RUN_SEED=true`,
then `gunicorn --bind=0.0.0.0 --timeout 600 --workers 2 wsgi:app`. `/api/health` now checks DB, Key Vault
and Blob. ✅ `curl https://<app>.azurewebsites.net/api/health` reports all three OK.

**Phase 4 — Database & auth.** Models + migrations, register/login/logout/me, JWT cookie, CSRF, rate limit,
lockout, `@require_role`, `flask create-admin` (reads `SEED_ADMIN_*` from app settings). ✅ CI tests for
login success/failure/lockout/role guard; live login works.

**Phase 5 — Crypto core.** `envelope.py`, `integrity.py`, `AzureKeyVaultProvider`, `AzureBlobStorage`;
fakes in `tests/fakes.py`. ✅ CI tests: round-trip at several sizes; unique DEK + nonce per file; tampered
ciphertext → `InvalidTag`; wrong AAD fails; wrapped key ≠ DEK; no DEK persisted.

**Phase 6 — Files API + audit.** All file/share endpoints, `can_download`, audit logger. ✅ authz-matrix
tests in CI; `scripts/live_smoke_test.sh` (curl) on the live site: register → upload → list → share →
officer download → unauthorized 403; portal/`az storage blob list` shows only `.bin` ciphertext.

**Phase 7 — Frontend.** All pages in Section 8. ✅ full walkthrough on the live URL for each role.

**Phase 8 — Replication, monitoring, hardening.** `infra/replication.sh` (ask first): Object Replication
primary → secondary for `encrypted-files`. `infra/diagnostics.sh`: Key Vault `AuditEvent` + Storage logs
→ Log Analytics. App Insights telemetry in Flask. `flask rewrap-keys`. ✅ uploaded ciphertext appears in
the secondary account; Key Vault unwrap events visible in Log Analytics (include the KQL query in docs).

**Phase 9 — Evidence & demo data.** `flask seed-demo` (admission use case: 3 students, 2 officers,
1 admin, **fake** sample documents — never real personal data), run once by setting `RUN_SEED=true`,
restarting, then setting it back to `false`. `scripts/tamper_test.sh` (overwrite one blob via az CLI →
download returns 409 + `INTEGRITY_FAIL` audit). Benchmarks via `/api/admin/benchmark` plus
`scripts/live_benchmark.py` (end-to-end upload/download timings from the client, CSV + PNG charts) →
`docs/benchmarks.md`. `docs/testing-evidence.md`: 403 on unauthorized access, tamper detection,
DB holds no plaintext keys (show a query run through a temporary firewall rule the user approves,
then removed), blobs hold no plaintext, cross-region copy. ✅ all evidence captured from the live system.

**Phase 10 — NS-3 evaluation.** In `ns3/`: two-node WAN and multi-region topologies; vary delay
(20–300 ms), bandwidth (1–100 Mbps), loss (0–5%); payloads matching benchmark sizes; FlowMonitor →
`plot_results.py` charts for latency, throughput, packet loss. `ns3/README.md` with Ubuntu/WSL2 install.
(This is a research simulation, not app hosting; it can also run in a GitHub Actions workflow
`ns3.yml` on ubuntu-latest that uploads the results as artifacts if the user prefers not to install it.)
✅ CSVs and plots in `ns3/results/`.

**Phase 11 — Docs + teardown.** README (overview, live URL, screenshots, Azure setup, CI/CD, demo
credentials), `architecture.md` (Mermaid), `security-design.md` (threat model: stolen storage creds,
DB leak, stolen user password, insider, tampering; what CloudVeil does and does not protect — decryption
is server-side, so this is encryption at rest + controlled decryption, not end-to-end),
`demo-script.md` (5-minute viva walkthrough). `infra/teardown.sh` deletes the resource group (asks to confirm).

---

## 10. Definition of done

- Live HTTPS URL on Azure App Service; all three roles work end-to-end.
- Only ciphertext in Blob Storage (both regions); only wrapped keys in MySQL; KEK never leaves Key Vault.
- Unauthorized download → 403 + audit row; tampered blob → detected + audit row.
- CI green with ≥80% coverage on `app/crypto`, `app/files`, `app/auth`; every push to `main` deploys.
- Benchmarks, NS-3 results and docs present.
