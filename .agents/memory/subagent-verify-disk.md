---
name: Verify subagent work landed on disk
description: Subagents can report success without writing any files; always verify via git status before trusting the report.
---

Rule: after any subagent (especially DESIGN) reports completion, verify the work actually exists before proceeding: `git --no-optional-locks status --short` plus a quick `wc -l` / timestamp check on the target file.

**Why:** A DESIGN subagent once returned a detailed success report ("redesign completed, tsc passes, files changed") while `git status` was completely clean and the target file was byte-identical. A follow-up message via `messageSubagentAndGetResponse` (using the `subagentAlias` returned by the original call, not the `sub:<uuid>` id printed in messages) got it to actually apply the edits.

**How to apply:** Treat subagent completion messages as claims, not evidence. Verify disk state first; if empty, message the same subagent with the concrete evidence ("git status clean, file unmodified") rather than relaunching from scratch — it retains context and applies the work on the second pass.
