# CloudVeil — Secure Data. Anywhere.

CloudVeil is a fully hosted web platform on Microsoft Azure that encrypts every uploaded file with its
own unique key, stores only ciphertext in Azure Blob Storage, protects each file key with a master key
in Azure Key Vault (envelope encryption), and decrypts only for users who pass authentication and
role/permission checks. Every action is audited.

> MCA final-year project. **Cloud-only workflow** — the app runs only on Azure App Service. Code is
> written here → pushed to GitHub → GitHub Actions tests, builds Tailwind, and deploys.

## Architecture (summary)

```
Browser (HTML + Tailwind + Vanilla JS + Chart.js)
        │ HTTPS
        ▼
Azure App Service (Flask, gunicorn) ── Managed Identity
   ├─► Key Vault (RSA-3072 KEK)  — wrap/unwrap data keys
   ├─► Blob Storage (ciphertext) — primary + replicated secondary region
   ├─► MySQL Flexible Server     — users, file metadata, permissions, audit
   └─► Application Insights       — telemetry
```

Envelope encryption: a per-file AES-256-GCM data key (DEK) encrypts the file; the DEK is wrapped by the
Key Vault RSA key (KEK) and only the wrapped key is stored in MySQL. The KEK never leaves Key Vault.

## Repository status

Built phase by phase per `CLAUDE.md`. See that file for the full specification and phase plan.

| Phase | Description | Status |
|---|---|---|
| 1 | Scaffold + CI skeleton | ✅ |
| 2 | Provision Azure | ✅ |
| 3 | First live deploy | ⏳ |
| 4 | Database & auth | ⏳ |
| 5 | Crypto core | ⏳ |
| 6 | Files API + audit | ⏳ |
| 7 | Frontend | ⏳ |
| 8 | Replication, monitoring, hardening | ⏳ |
| 9 | Evidence & demo data | ⏳ |
| 10 | NS-3 evaluation | ⏳ |
| 11 | Docs + teardown | ⏳ |

## Local developer tooling

There is **no local app runtime**. You only need git, Azure CLI, and GitHub CLI. Optionally, to run
tests before pushing:

```bash
pip install -r requirements-dev.txt
pytest
ruff check .
black --check .
```

## CI/CD

`.github/workflows/deploy.yml` runs lint (ruff + black) and tests (pytest) on every push/PR to `main`.
Deployment to Azure App Service via OIDC is added in Phase 3.
