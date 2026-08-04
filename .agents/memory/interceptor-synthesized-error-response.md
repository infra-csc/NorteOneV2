---
name: Shared interceptor synthesized errors must preserve .response/.config
description: A global axios interceptor that builds a new Error for a status code (instead of passing the original through) must copy over error.response/error.config, or any handler relying on response.data.detail for that status code silently degrades to a generic fallback.
---

## The problem

A shared axios response interceptor special-cased some HTTP status codes (e.g. 429 for
rate-limiting, 409 for a "busy/in-progress" lock) by synthesizing a **new** `Error` object
with a friendly flat message and a boolean flag (`isRateLimit`, `isBusy`), then rejecting
with that instead of the original error. One of these branches copied `error.response`
onto the new object; a sibling branch, added earlier for a single narrow use case, did not.

Months later, a *different, unrelated* feature started using the same status code (409)
for its own structured error (`{ detail: { code, message, ... } }`), read via
`err.response.data.detail.code` in its catch block. Because the interceptor's synthesized
error had no `.response` at all, that check always evaluated against `undefined` and
silently fell through to a generic fallback message — the specific, actionable error (and
the UI it was meant to open, e.g. an approval modal) never appeared. Nothing threw or
logged; it just looked like "saving mysteriously always fails."

**Why:** interceptors that flatten an error into `{ message, someFlag }` are convenient
for the one feature they were written for, but any *other* feature that later reuses the
same status code for a different, structured purpose has no way to know the response was
stripped — the bug is invisible from the call site that broke.

**How to apply:** whenever a shared interceptor synthesizes a new Error for a status code
(rather than rejecting the original `error`), always copy `error.response` and
`error.config` onto it too, mirroring whichever branch already does this correctly in the
same file — don't assume a flat message + flag is enough just because that was sufficient
for the first caller. When adding a new special-cased branch to such an interceptor,
grep the file for existing branches first and match their shape exactly, or extract a
shared "enrich but preserve response" helper so this can't be forgotten again.
