# EPUB Utils Pipeline

This repo provides a small, opinionated pipeline for turning EPUBs into Markdown using the `epub-utils` Python library. The goal is to keep output readable while preserving structure, images, and optionally richer styling.

## Fundamental approach

1. **Parse EPUB via epub-utils**
   - Load the EPUB with `Document`.
   - Read metadata from `doc.package.metadata`.
   - Use `doc.package.spine` for reading order.
   - Prefer the EPUB TOC (`doc.toc`) to name sections, so output headings match the book’s table of contents instead of file names like `part0001`.

2. **Section extraction**
   - If the TOC provides anchors (for example `chapter.xhtml#ch1`), content is sliced to that section.
   - If the TOC only references files, the full file is used once per entry.
   - If there is no TOC, fall back to the spine order.
   - Optional heading fallback (`--chapter-fallback auto|force`) can synthesize section starts from heading-like patterns when TOC quality is poor.

3. **HTML handling**
   - The converter ignores `head`, `title`, `style`, `script`, and `svg` by default so those do not leak into text output.
   - Output can be either:
     - **Plain Markdown**: everything is converted to Markdown text.
     - **Rich Markdown**: complex HTML is preserved as raw HTML blocks and simple content is converted to Markdown.

4. **Image handling**
   - `<img>` tags are converted to Markdown images.
   - Image files are extracted from the EPUB and written to `epub-utils/results/<book_slug>/images/...`.
   - Links in Markdown use relative paths like `./<book_slug>/images/...`.
   - Optional `--media-all` extracts all manifest images, not just those referenced in content.

5. **CSS handling (rich mode only)**
   - Only CSS linked by the XHTML being processed is considered.
   - Two modes:
     - `--style inline`: embed CSS in a `<style>` block at the top of the Markdown.
     - `--style external`: copy CSS to `epub-utils/results/<book_slug>/styles/...` and insert `<link>` tags.

## Output layout

- Markdown files: `epub-utils/results/<book_slug>.md`
- Images: `epub-utils/results/<book_slug>/images/...`
- Styles (rich mode + external): `epub-utils/results/<book_slug>/styles/...`

## Script location

`epub-utils/parse_epubs.py`

## Usage

Convert all EPUBs under `assets` to Markdown:

```bash
python3 epub-utils/parse_epubs.py
```

Extract all manifest images too:

```bash
python3 epub-utils/parse_epubs.py --media-all
```

Rich Markdown with inline CSS:

```bash
python3 epub-utils/parse_epubs.py --markdown-mode rich --style inline
```

Rich Markdown with external CSS files:

```bash
python3 epub-utils/parse_epubs.py --markdown-mode rich --style external
```

## Notes and tradeoffs

- Markdown renderers vary: some ignore `<style>` or `<link>` tags. Inline CSS works best in permissive renderers (like local previews). GitHub may strip style/link tags.
- Rich mode keeps complex HTML blocks (tables, figures, elements with class/style) to preserve structure and styling where Markdown is too limited.
- Plain mode is best for maximum portability and minimal HTML.

## Flags summary

- `--input-dir`: directory containing EPUB files (default: `assets`)
- `--output-dir`: output directory (default: `epub-utils/results`)
- `--media-all`: extract all manifest images
- `--markdown-mode`: `plain` or `rich`
- `--style`: `inline` or `external` (only used in rich mode)
- `--split-chapters`: write one file per section under `results/<book_slug>/`
- `--chapter-fallback`: `off|auto|force`
  - `off`: use TOC/spine logic only
  - `auto`: only trigger fallback if TOC is degenerate (`entries <= 1` OR `unique_hrefs < 3` OR coverage `< 0.15`)
  - `force`: always attempt heading-based fallback first

## Heading fallback behavior

- The fallback scores each spine document as a possible chapter start using:
  - major heading regex hits (`chapter|book|part`, plus `preface|prologue|epilogue|introduction|foreword|afterword`)
  - heading tags (`h1`..`h3`) and top-of-document text
  - heading-like short first-line signals
  - OCR-noise penalty (`estimated to be only XX% accurate`)
- It accepts starts at confidence `>= 1.0` with minimum spacing between starts to reduce over-splitting.
- If fallback is requested but not used, a warning is printed with the reason.
- If fallback activates, a warning is printed with TOC/spine stats and detected start count.
