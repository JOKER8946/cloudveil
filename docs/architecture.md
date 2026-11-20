# CloudVeil — Architecture

## System overview

```mermaid
flowchart TB
    dev["Developer machine<br/>Claude Code · git · az · gh<br/>(writes code, runs infra scripts)"]
    gh["GitHub<br/>Actions: test → build Tailwind → deploy (OIDC)"]
    dev -->|git push| gh

    subgraph Azure["Microsoft Azure (UAE North primary)"]
        app["App Service (Linux, Python 3.12)<br/>Flask REST API + static frontend<br/>System-assigned Managed Identity"]
        kv["Key Vault (RBAC)<br/>RSA-3072 KEK 'cloudveil-kek'<br/>wrap / unwrap"]
        blob["Blob Storage (private)<br/>container 'encrypted-files'<br/>ciphertext only"]
        blob2["Blob Storage (Korea Central)<br/>replicated ciphertext"]
        sql["MySQL Flexible Server (TLS)<br/>users · files · permissions · audit"]
        mon["Application Insights /<br/>Log Analytics"]
    end

    gh -->|azure/webapps-deploy| app
    browser["Browser<br/>HTML · Tailwind · Vanilla JS · Chart.js"] -->|HTTPS| app
    app -->|Managed Identity| kv
    app -->|Managed Identity| blob
    blob -->|Object Replication| blob2
    app -->|PyMySQL + TLS| sql
    app --> mon
```

## Envelope-encryption flow (upload)

```mermaid
sequenceDiagram
    participant U as User (browser)
    participant A as App Service (Flask)
    participant KV as Key Vault
    participant B as Blob Storage
    participant DB as MySQL

    U->>A: POST /api/files (multipart, JWT cookie + CSRF)
    A->>A: validate (ext + magic bytes)
    A->>A: DEK = AES-256-GCM key; nonce = 12 random bytes
    A->>A: ciphertext = AESGCM(DEK).encrypt(nonce, file, aad)
    A->>KV: wrap(DEK) via RSA-OAEP-256
    KV-->>A: wrapped_key + kek_key_id
    A->>B: upload ciphertext to files/<uuid>.bin
    A->>DB: INSERT file row (wrapped_key, nonce, sha256, …)
    A->>DB: INSERT audit row (UPLOAD)
    A-->>U: 201 { file metadata }
    Note over A: plaintext DEK dropped; never stored
```

## Authorize-and-decrypt flow (download)

```mermaid
sequenceDiagram
    participant U as User
    participant A as App Service
    participant DB as MySQL
    participant B as Blob Storage
    participant KV as Key Vault

    U->>A: GET /api/files/<id>/download
    A->>DB: load file + check can_download(user, file)
    alt not authorized
        A->>DB: audit DOWNLOAD_DENIED
        A-->>U: 403
    else authorized
        A->>B: fetch ciphertext
        A->>KV: unwrap(wrapped_key, kek_key_id)
        KV-->>A: DEK
        A->>A: AESGCM(DEK).decrypt(nonce, ct, aad)
        alt InvalidTag (tampered)
            A->>DB: audit INTEGRITY_FAIL
            A-->>U: 409
        else ok
            A->>A: verify SHA-256
            A->>DB: audit DOWNLOAD
            A-->>U: 200 stream (Content-Disposition: attachment)
        end
    end
```

## Key design points

- **Managed Identity everywhere** for Azure services — no storage keys or Key
  Vault secrets in the app. Access is RBAC: the identity has *Key Vault Crypto
  User* and *Storage Blob Data Contributor* only.
- **The KEK never leaves Key Vault.** Only wrap/unwrap operations cross the
  boundary; the database stores just the wrapped key and the key id/version.
- **Per-file DEK + nonce**, with AAD binding ciphertext to `(file_id, owner_id)`
  so a blob cannot be replayed under a different file/owner.
- **Single authorization choke point** (`can_download`) that is exhaustively
  unit-tested; every denial is audited.
- **Append-only audit** of every security-relevant action.
- **CI/CD via OIDC** — no long-lived cloud credentials in GitHub.

See `security-design.md` for the threat model and `api.md` for the REST API.
