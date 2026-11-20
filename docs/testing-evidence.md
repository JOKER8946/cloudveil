# CloudVeil — Testing evidence

Evidence captured from the **live** system (`https://cloudveil7k3.azurewebsites.net`)
and from CI. Reproduce with the scripts in `scripts/`.

## 1. Unauthorized download is denied (403 + audit)

`scripts/live_smoke_test.sh` performs: register → upload → list → share with an
officer → officer download → **unauthorized user download → 403**. A student who
is neither the owner nor a grantee receives `403 forbidden` and a
`DOWNLOAD_DENIED` audit row is written.

```
[8] unauthorized user is denied (403)
  PASS: intruder denied (403)
== ALL 10 CHECKS PASSED ==
```

The authorization decision lives in a single function, `can_download()`
(`app/files/service.py`), unit-tested for every role × ownership × permission ×
expiry combination (`tests/test_authz.py`). **Admins get no automatic decrypt
access.**

## 2. Tamper detection (409 + INTEGRITY_FAIL)

`scripts/tamper_test.sh` uploads a file, then overwrites its ciphertext blob
directly via the Azure CLI (bypassing the app), then downloads through the API:

```
[4] overwrite the newest ciphertext blob with junk (direct az write)
    tampering with files/<uuid>.bin
[5] download again — expect 409 (integrity failure)
    PASS: tamper detected (HTTP 409)
[6] confirm INTEGRITY_FAIL in the audit log (admin)
    PASS: 1 INTEGRITY_FAIL audit row(s)
```

AES-GCM authentication fails on the modified ciphertext → `InvalidTag` → HTTP
`409` and an `INTEGRITY_FAIL` audit row. The file is now permanently unreadable,
proving the integrity guarantee.

## 3. Blob Storage holds only ciphertext

`az storage blob list` on the primary container shows only random-named
`files/<uuid>.bin` objects — never the original filename:

```
Name                                            Size
files/1d862dd1-...-7ec787096d16.bin             55
files/bb2b588b-...-813fc750fe57.bin             29
```

Downloading a blob and inspecting its bytes shows ciphertext, not plaintext
(e.g. first bytes `fb 00 ca 79 …`, not the readable document content). Object
size = plaintext length + 16-byte GCM tag.

## 4. Cross-region replication (ciphertext only)

Object Replication copies the ciphertext container from the primary account
(UAE North) to the secondary account (Korea Central). After enabling the policy
and uploading a file, the same `.bin` ciphertext object appears in the secondary
account (`az storage blob list` on `<prefix>sec`). Only ciphertext crosses
regions; the KEK never leaves Key Vault.

## 5. The database holds no plaintext keys

By design, the `files` table stores only:

- `wrapped_key` `VARBINARY(512)` — the DEK **wrapped** by the Key Vault KEK, and
- `kek_key_id` — the Key Vault key id (with version) used to wrap it.

There is **no column for a plaintext data key**, and `tests/test_crypto.py`
asserts that the `EncryptedFile` result object exposes no `dek`/`key` field and
that the wrapped key cannot be used directly as the AES key.

To demonstrate this on the live database, add a temporary MySQL firewall rule
for your current IP (approve first), run:

```sql
SELECT id, HEX(LEFT(wrapped_key,8)) AS wrapped_prefix, kek_key_id
FROM files LIMIT 5;
```

— the `wrapped_key` is opaque wrapped bytes, not a usable key — then remove the
firewall rule. (This requires a one-off firewall change; run it only when
needed and delete the rule afterwards.)

## 6. CI evidence

Every push to `main` runs lint (ruff + black) and the test suite (pytest). The
crypto, files and auth packages have **≥ 88 %** coverage. Highlights:

- `test_crypto.py` — round-trip at several sizes, unique DEK + nonce per file,
  tampered ciphertext → `InvalidTag`, wrong AAD fails, wrapped key ≠ DEK, no DEK
  persisted.
- `test_authz.py` — the full `can_download` matrix.
- `test_files.py`, `test_sharing.py`, `test_audit.py`, `test_admin.py`,
  `test_auth.py`, `test_cli.py` — API, sharing, audit, admin and CLI behaviour.
