# CloudVeil infrastructure scripts

All scripts read configuration from `../.env` and are **idempotent** (safe to re-run).
They create **paid** Azure resources — run them only with approval.

Run order (Phase 2):

```bash
bash infra/provision.sh      # resource group, Key Vault + KEK, storage x2, MySQL, monitoring, web app
bash infra/roles.sh          # RBAC: managed identity + signed-in user
bash infra/github_oidc.sh    # GitHub Actions -> Azure OIDC + repo secrets
bash infra/app_settings.sh   # push app settings (DB, Key Vault, storage, JWT secret)
```

PowerShell equivalents (`*.ps1`) are provided for Windows users who prefer them; the `.sh`
versions are the reference implementation.

## Resources created

| Script | Creates |
|---|---|
| `provision.sh` | Resource group, Log Analytics + App Insights, Key Vault (RBAC, purge protection) + RSA-3072 KEK, primary + secondary storage (StorageV2, Standard_LRS, versioning) + container, MySQL Flexible B1ms + DB, App Service plan (Linux B1) + Web App (Python 3.12, HTTPS-only, managed identity) |
| `roles.sh` | Managed identity → Key Vault Crypto User + Storage Blob Data Contributor; signed-in user → Key Vault Crypto Officer + Storage Blob Data Contributor |
| `github_oidc.sh` | Entra app + federated credential (repo `main`) + Contributor on RG; GitHub secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` |
| `app_settings.sh` | App Service application settings (non-secret names + DB password, generated `JWT_SECRET`, App Insights connection string) |
| `replication.sh` | Object Replication of `encrypted-files` primary → secondary region (ask first) |
| `diagnostics.sh` | Key Vault `AuditEvent` + Storage blob logs → Log Analytics |
| `teardown.sh` | Deletes the resource group (asks to confirm) |

## Cost note (Azure for Students)

The standing monthly cost is dominated by **MySQL Flexible B1ms (~$12–15)** and **App Service B1
(~$13)**. Between demos, stop the database to save credit:

```bash
az mysql flexible-server stop -g rg-cloudveil -n mysql-<prefix>
az mysql flexible-server start -g rg-cloudveil -n mysql-<prefix>
```

## If OIDC app registration is blocked

Some school/university tenants forbid students from creating Entra app registrations. If
`github_oidc.sh` fails with `AuthorizationFailed` / insufficient privileges, deployment falls back to
an App Service **publish profile**:

```bash
az webapp deployment list-publishing-profiles -g rg-cloudveil -n <webapp> --xml > profile.xml
gh secret set AZURE_WEBAPP_PUBLISH_PROFILE --repo <user>/cloudveil < profile.xml
```

and the deploy workflow uses the publish profile instead of `azure/login`.
