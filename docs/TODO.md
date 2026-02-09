# EPUB Parser TODO

## High Priority

- Internal link rewrite + validation
  - Preserve and rewrite `#anchor` links and cross-chapter links after split output.
  - Validate unresolved targets and report broken links.

- Footnotes/endnotes handling mode
  - Support configurable behavior:
    - keep inline
    - move to chapter end
    - collect into global notes file
  - Preserve backlink navigation.

- TOC + landmarks export (machine-readable)
  - Emit JSON manifest of sections, hierarchy, and optional page-list/landmarks.
  - Include stable IDs and source href/fragment mapping.

## Medium Priority

- Navigation dedupe/cleanup
  - Reduce duplicate front matter entries.
  - Suppress repeated OCR boilerplate blocks where confidence is low.

- OCR-aware cleanup pipeline (optional)
  - Header/footer stripping.
  - Hyphenation cleanup.
  - Confidence-based filtering/tuning options.

- Asset completeness improvements
  - Support `srcset`, `picture`, SVG-linked resources.
  - Optional audio/video extraction.

## Lower Priority

- Typography + semantic normalization
  - Better handling for lists, blockquotes, code/pre, tables, epigraphs, and small-caps.

- EPUB3 extras
  - Better support for `nav` variants, `page-list`, media overlays, and accessibility semantics.

- Stable naming + deterministic IDs
  - Generate section IDs independent of output ordering for app sync stability.

- Quality report output
  - Per-book report with TOC coverage, fallback activation, section count, missing assets, and broken refs.

## Suggested Implementation Order

1. Internal links + footnotes/endnotes
2. TOC/landmarks JSON manifest
3. OCR cleanup options
4. Asset completeness + EPUB3 extras
