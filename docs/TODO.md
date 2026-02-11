# EPUB Parser TODO

This file is the execution board for the lockstep roadmap across:
- `epub-utils`
- `rbook-utils`

Legend:
- `[x]` done
- `[ ]` pending
- `~` partial/in progress

## M0: Milestone Skeleton

- `[x]` Converted roadmap into milestone IDs (`M1..M8`)
- `[x]` Added explicit parity requirement for each milestone
- `[x]` Added acceptance criteria per milestone

## M1: Internal Link Rewrite + Validation

Status:
- `epub-utils`: `[x]`
- `rbook-utils`: `[x]`
- Tests/parity: `~`

Scope:
- Rewrite internal links for single-file and split-chapter outputs.
- Validate unresolved targets and report broken internal links.
- Keep unknown links unchanged (warn + report).

Acceptance:
- Internal anchor links resolve in split output.
- Cross-chapter links are rewritten to chapter-relative paths in split mode.
- Unresolved links are counted in `report.v1.json`.

## M2: Footnotes/Endnotes Modes

Status:
- `epub-utils`: `[x]` (markdown-footnote pattern support)
- `rbook-utils`: `[x]` (markdown-footnote pattern support)
- Tests/parity: `~`

Scope:
- Add `--notes-mode inline|chapter-end|global`.
- `inline`: leave notes unchanged.
- `chapter-end`: collect markdown note definitions at chapter end.
- `global`: collect markdown note definitions into `results/<book_slug>/notes.md`.

Acceptance:
- No-op with `inline`.
- Chapter-end/global outputs produce stable note IDs and backlinks for markdown footnote refs.

## M3: TOC + Landmarks + Page-List Export

Status:
- `epub-utils`: `[x]` (`manifest.v1.json`)
- `rbook-utils`: `[x]` (`manifest.v1.json`)
- Tests/parity: `~`

Scope:
- Add `--export-manifest off|v1`.
- Emit `manifest.v1.json` with:
  - `schema_version`, `book`, `spine`, `toc_tree`, `sections`,
  - `landmarks`, `page_list`, `assets`, `build`.
- Include stable `section_id`, source boundary mapping, and output path.

Acceptance:
- Manifest exists when enabled and contains deterministic section IDs.

## M4: Navigation Dedupe + OCR Cleanup

Status:
- `epub-utils`: `[x]`
- `rbook-utils`: `[x]`
- Tests/parity: `~`

Scope:
- Add `--nav-cleanup off|auto` (default `auto`).
- Add `--ocr-cleanup off|basic|aggressive` (default `off`).
- Dedupe noisy/duplicate TOC entries.
- Apply optional OCR cleanup (dehyphenation + repeated/noise line suppression).

Acceptance:
- TOC duplicate suppression counts are reported.
- OCR cleanup changes are counted in `report.v1.json`.

## M5: Asset Completeness + EPUB3 Media Handling

Status:
- `epub-utils`: `~` (images + manifest audio/video extraction)
- `rbook-utils`: `~` (images + manifest audio/video extraction)
- Tests/parity: `~`

Scope:
- Preserve existing image behavior.
- Expand `--media-all` to include optional audio/video extraction.
- Keep external/data URIs unchanged.

Acceptance:
- Image extraction remains backward compatible.
- Audio/video extracted when discoverable from manifest and `--media-all` is enabled.

## M6: Typography/Semantics Normalization

Status:
- `epub-utils`: `[ ]`
- `rbook-utils`: `[ ]`
- Tests/parity: `[ ]`

Scope:
- Improve normalization for lists/quotes/code/tables/epigraph conventions.
- Preserve safe rich fallback where markdown conversion is lossy.

Acceptance:
- No regressions in existing books while improving semantic fidelity.

## M7: Deterministic IDs + Stable Filename Scheme

Status:
- `epub-utils`: `[x]`
- `rbook-utils`: `[x]`
- Tests/parity: `~`

Scope:
- Canonical section boundary hashing -> stable `section_id`.
- Add `--filename-scheme legacy|stable` (default `legacy`) for split output.

Acceptance:
- Stable mode produces deterministic chapter filenames independent of label order churn.

## M8: Quality Report + Parity Gate

Status:
- `epub-utils`: `[x]` (`report.v1.json`)
- `rbook-utils`: `[x]` (`report.v1.json`)
- Tests/parity gate: `~`

Scope:
- Add `--quality-report off|v1`.
- Emit report including:
  - TOC/fallback/link/asset/OCR/cleanup/notes stats
  - warnings/errors arrays
- Add parity checks across both implementations.

Acceptance:
- Both parsers generate machine-readable report files with matching key metrics.
- Parity runs compare section counts + unresolved link counts + missing asset counts.

## Final Integration Gate

- `[ ]` Run lockstep commands for both parsers on reference books (`Alice`, `Meditations`, `Algebra`, `CBT`, `Ultralearning`).
- `[ ]` Compare:
  - section counts
  - first N section titles/IDs
  - unresolved link counts
  - missing asset counts
- `[ ]` Document known parity differences.
