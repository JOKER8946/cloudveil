# CloudVeil — Your setup checklist (cloud-only, no local development)

Nothing runs on your computer. Claude Code writes the code and runs Azure/GitHub commands from your
terminal; GitHub Actions tests and deploys; the app runs only on Azure.

## A. Accounts
- [ ] **Azure subscription.** Confirm you are **Owner** (Portal → Subscriptions → your sub →
      Access control (IAM) → View my access). Needed to assign roles and set up GitHub deployment.
- [ ] **GitHub account** + an empty repo, e.g. `cloudveil` (private is fine).
- [ ] **Claude Code** installed and signed in.

## B. Install on your computer (tools only — no database, no web server)
| Tool | Why | Check with |
|---|---|---|
| Git | push code | `git --version` |
| Azure CLI | create Azure resources | `az version` |
| GitHub CLI | create repo, set secrets, watch deploys | `gh --version` |
| Python 3.12 *(optional)* | lets Claude Code run tests before pushing; CI runs them anyway | `python --version` |

Not needed: XAMPP, MySQL, VS Code, Docker, NS-3 (NS-3 can run inside GitHub Actions).

## C. Sign in (you do this yourself — never paste passwords into the chat)
```bash
az login
az account set --subscription "<your subscription name or id>"
gh auth login
```
Register the resource providers once (harmless if already registered):
```bash
for p in Microsoft.KeyVault Microsoft.Storage Microsoft.DBforMySQL Microsoft.Web Microsoft.Insights Microsoft.OperationalInsights; do az provider register -n $p; done
```

## D. Create the project folder
```bash
mkdir cloudveil && cd cloudveil
git init
# copy CLAUDE.md and SETUP.md into this folder
```

## E. Create `.env` in the project folder
```ini
# ---- Azure ----
AZURE_SUBSCRIPTION_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_RESOURCE_GROUP=rg-cloudveil
AZURE_PRIMARY_REGION=centralindia
AZURE_SECONDARY_REGION=southeastasia
# lowercase letters + digits, short, unique (used to build resource names)
NAME_PREFIX=cloudveil7k3

# ---- MySQL Flexible Server admin (strong password; stays only in this file + App Service settings) ----
MYSQL_ADMIN_USER=cvadmin
MYSQL_ADMIN_PASSWORD=<12+ chars, upper, lower, digit, symbol>

# ---- First admin login for the CloudVeil web app ----
SEED_ADMIN_EMAIL=you@example.com
SEED_ADMIN_PASSWORD=<strong password>

# ---- GitHub ----
GITHUB_REPO=<your-username>/cloudveil
```
`.env` is never committed. Claude Code adds it to `.gitignore` in Phase 1.

## F. Budget safety (strongly recommended)
Portal → Cost Management → Budgets → monthly budget (e.g. ₹1,500) with email alerts at 50/80/100%.
Between demos you can stop the MySQL server to save credit (`az mysql flexible-server stop -g rg-cloudveil -n <name>`).

## G. Azure resources that will be created (each step needs your approval)
Resource group · Key Vault + RSA key · 2 storage accounts (primary + secondary region) ·
MySQL Flexible Server (B1ms) · App Service plan (B1) + Web App · Log Analytics + Application Insights ·
Entra app registration for GitHub deployment.

## H. If something fails
- *SKU/region not available* (MySQL) → change `AZURE_PRIMARY_REGION` (e.g. `southindia`, `eastasia`) and rerun.
- *AuthorizationFailed* on role assignment / app registration → you are not Owner, or your tenant blocks app registrations; fix in IAM / Entra settings.
- *Name already taken* → change `NAME_PREFIX`.
