---
name: tsc --noEmit can be clean while JSX tags are actually imbalanced
description: An extra/missing closing tag deep in nested conditional JSX can pass tsc --noEmit with 0 errors yet still crash Vite's real dev parser (SWC/esbuild) with "Unterminated regexp literal". Don't trust tsc alone to validate JSX structure.
---

## The problem

TypeScript's parser is deliberately lenient/error-recovering; it can accept a file with a
genuinely unbalanced JSX tree (one stray `</div>` or one missing open tag) and still report
`tsc --noEmit` exit code 0. Meanwhile Vite's actual dev transform (`vite:react-swc`, or
esbuild) uses a strict, spec-compliant lexer. When it hits the point in the file where the
tag imbalance has already made the parser drop out of "JSX children" mode back into a plain
JS expression context, it commonly manifests as a confusing, misleading error far from the
real cause: **"Unterminated regexp literal"** pointing at some unrelated `</div>` — because
the lexer, no longer expecting JSX, tries to read `<` as "less than" and the following `/` as
the start of a regex literal, then fails to find a closing `/` before end of line.

This is a real, reproducible parse failure, not a stale HMR/cache artifact — but it is very
easy to misdiagnose as one, especially if the dev server was flaky earlier in the session, or
if a workflow restart seems to "fix" it (restarting just re-triggers a fresh parse attempt;
if the file is genuinely still broken, the same error reappears on the next real recompile).

**Why:** tsc and SWC/esbuild use different grammars/recovery strategies; tsc's forgiving
error recovery is great for editor diagnostics but is not proof the JSX tree is well-formed.

**How to apply:** when a Vite/SWC "Unterminated regexp literal" (or similarly cryptic
lexer-level) error appears and `tsc --noEmit` says the file is clean, do NOT assume it's
stale cache. Get an authoritative, cache-independent second opinion by running esbuild
directly against the file (`esbuild.buildSync({ entryPoints: [path], loader: { '.tsx': 'tsx'
}, write: false })` in a quick Node script) — same strict parser class as SWC, but a fresh
one-shot process with no dev-server state to be stale. If esbuild also fails at the same
location, the bug is real: count `<div`/`</div>` (or whichever tag) opens vs closes between
the nearest enclosing `{cond && (` / ternary boundaries with a small script that tracks
running depth per line — the line where depth first goes negative (or ends non-zero) is the
true imbalance, which is often several lines away from the reported error location. Fix
there, then re-verify with esbuild before trusting a workflow restart's clean logs.
