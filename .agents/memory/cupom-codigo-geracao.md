---
name: Coupon code auto-generation
description: Durable rules for auto-generated cortesia cupom codes (fixed length, uniqueness) — read before touching or extending that generation logic.
---

Coupon codes for cortesia (courtesy) requests are generated server-side (sigla + SKU + random suffix) instead of pasted/imported by hand, and every code must come out the **same total length** — the random suffix shrinks or grows to compensate for how long the sigla+SKU prefix is.

**Why a fixed total length is tricky:** the total must be sized against the *worst-case* prefix length (max possible sigla length combined with the longest realistic SKU), not the typical/observed one. An early version picked a total based on typical lengths and it silently broke — a legitimate max-length sigla plus a legitimate max-length SKU produced longer codes than everything else, violating "all codes are the same length." A hard cap that rejects (loudly, with a clear message) any prefix combination too long for the configured total is required as a backstop, since the source fields (area sigla, event SKU) aren't fully bounded by this feature's own validation.

Uniqueness: check the persisted history first (case-insensitive), retry a bounded number of times, and keep a real DB unique index as the last resort — treat a caught integrity error as "just retry" ONLY when it's actually that specific unique index rejecting the insert; anything else is a different bug and must surface as its own error, not get relabeled as a generation conflict.

**How to apply:** any future feature that also produces these coupon codes (e.g. a bulk-generate-from-pending-requests flow) should reuse the existing generation logic rather than re-implementing the pattern, and should re-check the worst-case-length reasoning above if the inputs (sigla/SKU rules) ever change.
