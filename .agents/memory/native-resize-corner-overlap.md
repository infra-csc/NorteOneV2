---
name: Native CSS resize vs interactive footer corner
description: A panel made resizable via Tailwind `resize-x`/`resize-y`/`resize` + `overflow-auto` gets the browser's native resize grip in its bottom-right corner — a button placed there (e.g. a modal's Save button) has its clicks eaten by the grip instead of firing.
---

Symptom: user reports a button "does nothing" when clicked — no console error, no network request ever fires. Classic sign the click landed on an invisible native resize grip instead of the control underneath.

**Why:** any element with `resize: horizontal|vertical|both` AND `overflow` != visible gets a browser-drawn resize grip in its bottom-right corner (~13-16px hit area), regardless of which Tailwind utility set it. If interactive content (a modal footer's primary action button, commonly right-aligned) sits within that corner, a click there starts a ~0px resize drag instead of the button's onClick — no error, no visible change, "nothing happens."

**How to apply:** never place `resize-*` + `overflow-auto` directly on a container whose bottom-right corner also holds a clickable control. Prefer a custom drag handle instead: a thin (~8px) `absolute` strip along the resizable edge (e.g. `top-0 right-0 bottom-0 w-2 cursor-ew-resize` + manual `mousedown`/`mousemove`/`mouseup` listeners driving a width state), confined to the container's own padding gutter (e.g. inside a `p-5`) so it never overlaps inset content. When debugging a "click does nothing, no error, no request" report on any resizable panel, check for this before assuming a JS/validation bug.
