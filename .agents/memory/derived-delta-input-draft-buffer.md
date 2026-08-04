---
name: Derived-delta controlled input needs a local draft buffer
description: A text input whose displayed value is computed (delta = total - baseline) from committed state, rather than storing the typed text itself, silently erases in-progress negative/partial input on unrelated re-renders.
---

## The problem

Some numeric `<input>` fields don't store what the user types directly — they display a value **derived** from other committed state on every render (e.g. `delta = total - baseline`, recomputed fresh each time). The `onChange` handler parses the typed text and, once it's a valid number, commits it into the underlying state that the delta is computed from.

This works fine for positive/complete numbers, but breaks for any intermediate state that isn't independently parseable — most commonly a lone `"-"` (start of typing a negative number), or a temporarily-empty string. Since that intermediate text was never committed to the underlying state (by design — it isn't valid yet), any re-render caused by something else entirely in the component (a poll, an unrelated state update, a parent re-render) recomputes the derived value from the last-committed state and overwrites the DOM input's value, wiping the `-` before the user can type the digits after it. Symptom: "I can type positive numbers fine, but typing a negative number resets/clears as I type" (the stepper +/- buttons still work because they commit a complete value in one step, which masks the bug).

Plain fields whose state mirrors the typed text 1:1 (no derivation) don't have this problem — only fields showing a *view* of a *different* piece of state do.

## Fix pattern

Add a local "draft" text buffer (`useState<string | null>`, or `Record<rowKey, string>` for per-row fields in a list):
- `value`: read from the draft if present (formatted), else fall back to the derived/committed value.
- `onChange`: **unconditionally** write the raw stripped text into the draft on every keystroke (before any early-return for unparseable text), so the DOM always reflects exactly what was typed regardless of unrelated re-renders elsewhere in the component. Keep the existing parse-and-commit-if-valid logic unchanged after that.
- `onBlur`: clear the draft entry so the field reverts to the clean canonical formatted value once editing ends and stays in sync with external changes while not focused.

**Why:** the draft buffer is the single source of truth for "what's in the box" while focused; the derived value is only authoritative when nothing is being actively typed.

**How to apply:** for per-row draft maps keyed by array index, also clear the whole map (not just one key) whenever a row is inserted/removed elsewhere in the same list — removal shifts indices, so a stale keyed entry can end up rendering under the wrong row after the shift.
