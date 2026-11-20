# CloudVeil — Security design & threat model

CloudVeil provides **encryption at rest with controlled, server-side
decryption**. It is explicitly **not** end-to-end encryption: because decryption
happens on the server (so the app can enforce authorization and integrity), a
fully-compromised App Service instance could observe plaintext in transit
through memory. The design minimises and contains that trust.

## Assets

- Users' uploaded documents (confidentiality + integrity).
- The master key (KEK) and per-file data keys (DEKs).
- The audit trail (tamper-evidence of actions).
- User credentials.

## Controls at a glance

| Layer | Control |
|---|---|
| Transport | HTTPS-only, HSTS, TLS to MySQL, managed-identity tokens |
| AuthN | bcrypt (cost 12), JWT (HS256, 30 min) in HttpOnly+Secure+SameSite=Strict cookie |
| AuthZ | role + per-file permissions via a single `can_download()`; admins have no auto-decrypt |
| Anti-abuse | 5 logins/min/IP rate limit; lockout 15 min after 5 failures; CSRF double-submit |
| Crypto | AES-256-GCM per file; RSA-OAEP-256 KEK wrap in Key Vault; SHA-256 integrity |
| Data at rest | ciphertext-only blobs; wrapped keys only in DB; KEK never leaves Key Vault |
| Headers | CSP (self), X-Frame-Options DENY, X-Content-Type-Options nosniff, Referrer-Policy |
| Monitoring | append-only audit log; App Insights; Key Vault + Storage diagnostics → Log Analytics |

## Threats and responses

### 1. Stolen storage credentials / leaked blobs
An attacker who obtains the Blob Storage contents (or account keys) gets only
**ciphertext**. Each file is AES-256-GCM encrypted with a unique DEK that is not
stored anywhere in plaintext. Without the KEK (in Key Vault) they cannot
unwrap any DEK. **Mitigated.**

### 2. Database leak
The `files` table holds `wrapped_key` (the DEK encrypted by the KEK) and the
`kek_key_id` — never a usable key. Combined with #1, a DB leak alone does not
reveal documents. Passwords are bcrypt hashes. **Mitigated** (the attacker still
needs both the blobs *and* Key Vault unwrap access).

### 3. Stolen user password
JWT sessions are short-lived (30 min) and in HttpOnly cookies (not readable by
JS). Rate limiting + lockout slow brute force. A stolen password grants only
that user's own authorization — a student cannot read others' files, an officer
sees only files explicitly shared with them. **Contained.**

### 4. Malicious / curious insider (admin)
Admins manage users and view audit/stats but get **no automatic decrypt access**
to student files; `can_download` treats them like anyone else. Any self-grant of
a permission is an audited `ADMIN_ACTION`. The audit log is append-only (no
update/delete routes). **Contained + auditable.**

### 5. Tampering with stored ciphertext
AES-GCM is authenticated encryption; any modification of the ciphertext, nonce,
or the `(file_id, owner_id)` binding fails the tag check on download → HTTP 409
and an `INTEGRITY_FAIL` audit row (demonstrated by `scripts/tamper_test.sh`).
**Detected.**

### 6. Replay / blob swapping
The AAD binds each ciphertext to its `file_id` and `owner_id`, so a blob cannot
be decrypted under a different file or owner even if swapped in storage.
**Mitigated.**

### 7. CSRF / clickjacking / injection
State-changing requests require the `X-CSRF-Token` double-submit value; cookies
are `SameSite=Strict`. `X-Frame-Options: DENY` and a strict CSP block framing and
third-party script injection. Uploads are validated by extension **and** magic
bytes and never executed. **Mitigated.**

### 8. Compromised deployment pipeline
Deployment uses a GitHub OIDC federated credential scoped to the repo's `main`
branch — there are no long-lived Azure secrets in GitHub. The federated subject
is pinned (including GitHub's immutable numeric IDs). **Reduced.**

## What CloudVeil does NOT protect against

- A fully-compromised App Service process (it can see plaintext during
  decryption) — this is inherent to server-side decryption.
- A compromised Key Vault + Storage + DB simultaneously.
- Endpoint compromise of a legitimately authorized user's browser.

## Residual risk & future work

- Move to envelope encryption with client-side decryption for true end-to-end
  confidentiality (at the cost of server-side authorization/preview).
- Back Flask-Limiter with Redis for multi-instance rate limiting.
- Customer-managed keys rotation schedule (`flask rewrap-keys` already supports
  re-wrapping to a new KEK version without touching blobs).
