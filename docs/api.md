# CloudVeil — REST API

Base URL: `https://cloudveil7k3.azurewebsites.net`

- Auth is a JWT in an **HttpOnly** cookie (`cv_access`), set on login. The
  browser sends it automatically (same-origin).
- State-changing requests (POST/PATCH/DELETE) must send the CSRF token from the
  `cv_csrf` cookie in an **`X-CSRF-Token`** header.
- Errors use `{"error": {"code": "...", "message": "..."}}` with an HTTP status.

## Auth

| Method | Path | Role | Body / notes |
|---|---|---|---|
| POST | `/api/auth/register` | public | `{full_name, email, password}` → creates a **student** (201) |
| POST | `/api/auth/login` | public | `{email, password}` → sets cookies; 401 invalid, 423 locked |
| POST | `/api/auth/logout` | any | CSRF; clears cookies |
| GET | `/api/auth/me` | any | current user; 401 if not signed in |

## Files

| Method | Path | Role | Body / notes |
|---|---|---|---|
| POST | `/api/files` | student | multipart `file` + `category`; CSRF; encrypts & stores (201) |
| GET | `/api/files` | student | the caller's own files |
| GET | `/api/files/shared` | officer | files shared with the caller (unexpired) |
| GET | `/api/files/<id>` | authorized | file metadata |
| GET | `/api/files/<id>/download` | authorized | decrypt + stream (attachment); 403 / 409 |
| POST | `/api/files/<id>/share` | owner | CSRF; `{grantee_email, expires_at?}` (officer only) |
| DELETE | `/api/files/<id>/share/<grantee_id>` | owner/admin | CSRF; revoke a share |
| DELETE | `/api/files/<id>` | owner | CSRF; soft-delete + delete blob |

`category` ∈ `marks_card, id_document, transfer_certificate, application_form, other`.
Allowed types: pdf, png, jpg, jpeg, docx, txt (extension **and** magic bytes).
Max upload: `MAX_UPLOAD_MB` (default 50).

File metadata shape:
```json
{"id":"<uuid>","original_name":"marks_card.pdf","content_type":"application/pdf",
 "size_bytes":1234,"sha256":"<hex>","sha256_short":"<12 hex>","category":"marks_card",
 "primary_region":"uaenorth","created_at":"<iso8601>"}
```

## Admin (role: admin)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/admin/users?role=` | list users |
| GET | `/api/admin/users/<id>` | one user |
| PATCH | `/api/admin/users/<id>` | CSRF; `{role?, is_active?}` → audited `ADMIN_ACTION` |
| GET | `/api/admin/audit?action=&user=&from=&to=&page=` | paginated audit log (25/page) |
| GET | `/api/admin/stats` | chart data (uploads/day, downloads vs denials, actions, storage/category) |
| POST | `/api/admin/benchmark` | CSRF; `{sizes:[bytes,…]}` → AES / wrap-unwrap / blob timings |

## Health

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | `{status, service, checks:{database, keyvault, blob}}`; 200 ok / 503 degraded |

## Status codes

`200` ok · `201` created · `400` invalid input · `401` unauthenticated ·
`403` forbidden · `404` not found · `409` integrity failure · `423` account
locked · `429` rate-limited · `502` storage/unwrap error.
