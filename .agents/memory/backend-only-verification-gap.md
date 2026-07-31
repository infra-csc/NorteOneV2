---
name: Backend-only verification misses frontend-only bugs
description: Calling backend functions/endpoints directly to "verify" a feature end-to-end does not exercise the frontend's click handlers, disabled-button logic, or CSS/DOM interactions — bugs living purely in those layers slip through undetected.
---

A feature can be fully correct on the backend (validated via direct Python/API calls) while still being completely broken for the real user, because the bug lives in code that only runs through actual browser interaction: a disabled-attribute condition, a silent early-return guard clause, a stale/desynced React state, or a CSS element physically blocking a click (see native-resize-corner-overlap.md for a concrete case).

**Why:** it's tempting to treat "the backend saves correctly when I call it directly" as proof a feature works end-to-end, but that bypasses the entire frontend click-to-request path where these bugs live — this exact gap let a broken Save button ship undetected in a prior verification pass on this project.

**How to apply:** when interactive UI testing is blocked (e.g. an auth wall a Screenshot tool can't get through), do not rely on backend-only verification to declare a UI feature done. Instead trace the exact click path in code — the onClick handler, every guard clause/early return, the disabled-attribute expression, and any absolutely-positioned/overlapping elements near the control — and treat backend logs showing zero requests during a user's reported attempt as strong evidence the bug is frontend-side, not backend-side.
