---
name: CSV export double-BOM
description: Manually prefixing '\ufeff' before encoding with utf-8-sig doubles the BOM, corrupting the first CSV header cell.
---

Pattern found (and fixed on sight) more than once in this codebase's CSV
`StreamingResponse` exports:

```python
bom = '\ufeff'
content = bom + output.getvalue()
return StreamingResponse(io.BytesIO(content.encode('utf-8-sig')), ...)
```

`str.encode('utf-8-sig')` already writes the BOM bytes itself — the codec
does not check whether the string already starts with U+FEFF. Prefixing the
BOM character manually AND THEN encoding with `utf-8-sig` writes the BOM
twice. Decoding back with `.decode('utf-8-sig')` only strips one BOM
sequence, leaving a stray `\ufeff` character glued to the first header cell
(e.g. `"\ufeffEvento"` instead of `"Evento"`). Excel/Sheets are usually
lenient and hide it visually, but any code that reads the CSV
programmatically by exact header name (e.g. `csv.DictReader`) breaks with a
silent `KeyError` on the first column only — every other column is fine,
which is the tell that points at this exact bug.

**Why:** discovered while adding a new CSV export that copied a same-file
sibling's pattern; a test parsing the CSV by header name failed with
`KeyError` on the first column only. Grepping the backend for the same
`bom = '\ufeff'` + `.encode('utf-8-sig')` pair found it repeated verbatim
across multiple unrelated export endpoints (copy-pasted forward each time).

**How to apply:** to emit a CSV/text file with a BOM for Excel, do exactly
one of: (a) `output.getvalue().encode('utf-8-sig')` with no manual prefix,
or (b) prefix `'\ufeff'` manually and encode with plain `'utf-8'` (no
`-sig`). Never combine both. If you see `bom = '\ufeff'; content = bom +
text` sitting next to `.encode('utf-8-sig')` anywhere, it's this bug.
