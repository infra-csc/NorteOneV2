---
name: Tree drill-down tables need sibling rows
description: Hierarchical tables (Painel do evento tree) must render expanded children as sibling <tr>s in the same table, never nested tables.
---

Rule: in hierarchical drill-down tables (e.g. Painel do evento: Kit → Modalidade → Pelotão → Produtos → Tamanho, with per-bank leaf splits), expanded children and bank-split rows MUST be rendered as sibling `<tr>` elements inside the same `<table>`, using indentation (paddingLeft by depth) for hierarchy.

**Why:** A redesign once wrapped children in `<tr><td colSpan><table>…` for framer-motion height animations. Each nested table computes its own auto column widths, so numeric columns (Inscritos/%/Receita/Ticket) stop lining up with the header, parent rows and tfoot — and the misalignment compounds recursively per depth level. Also, animating `height: 0→auto` on a `<tr>` with `overflow-hidden` is unreliable (overflow doesn't clip table rows), so the animation gain is illusory anyway.

**How to apply:** When restyling any tree table, keep sibling-row rendering; limit motion to safe micro-animations (chevron rotation, hover states). Also avoid framer-motion `animate={{ backgroundColor: … }}` on rows — the inline style overrides Tailwind depth-striping classes in both themes.
