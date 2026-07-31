---
name: Blob download error body swallows backend error detail
description: Axios requests with responseType:'blob' return error bodies as a Blob, not JSON — breaks any shared extractError(e.response.data.detail) helper for file/CSV downloads.
---

## The problem

Any request made with `responseType: 'blob'` (file downloads, CSV/XLSX exports) that fails
still gets its error body parsed as a `Blob` by axios — even though the server sent JSON
(e.g. `{"detail": "..."}`). A shared error-message helper that reads
`e.response.data.detail` will always see `undefined` on these requests, because
`e.response.data` is a `Blob` object, not the parsed JSON. The user only ever sees the
generic fallback message, never the real reason (403, 404, file missing, etc.), which makes
the feature look broken even when the backend is returning a perfectly good explanation.

This is easy to miss because normal (non-blob) requests work fine — the bug only shows up
on download/export endpoints, and only when they actually fail, so it can hide for a long
time.

**Why:** axios has no way to know the *intended* content type of an error response ahead of
time; it just honors `responseType` for the whole request, success or failure.

**How to apply:** fix once, centrally, in the shared axios response interceptor — not per
call site. Before any other error handling, check if `error.response.data instanceof Blob`
and if its `type` includes `json`; if so, read it as text and `JSON.parse` it back into
`error.response.data` so every downstream `extractError`-style helper keeps working
unmodified. This fixes it app-wide for current and future blob-typed requests (downloads,
CSV exports, etc.) in one place instead of patching each call site.
