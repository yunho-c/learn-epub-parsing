"""Parse EPUB files in assets and emit Markdown into epub-utils/results."""

from __future__ import annotations

import argparse
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Optional

from epub_utils import Document


class _HtmlToMarkdown(HTMLParser):
    BLOCK_TAGS = {
        "p",
        "div",
        "section",
        "article",
        "br",
        "hr",
        "li",
        "ul",
        "ol",
        "table",
        "tr",
        "td",
        "th",
        "blockquote",
    }
    HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__()
        self._lines: list[str] = []
        self._heading_level: Optional[int] = None
        self._heading_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        tag = tag.lower()
        if tag in self.HEADING_TAGS:
            self._heading_level = int(tag[1])
            self._heading_chunks = []
            self._ensure_blank_line()
            return
        if tag in self.BLOCK_TAGS:
            self._ensure_blank_line()

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        tag = tag.lower()
        if tag in self.HEADING_TAGS:
            heading_text = " ".join(self._heading_chunks).strip()
            if heading_text:
                level = self._heading_level or 2
                self._lines.append("#" * level + " " + heading_text)
            self._heading_level = None
            self._heading_chunks = []
            self._ensure_blank_line()
            return
        if tag in self.BLOCK_TAGS:
            self._ensure_blank_line()

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        text = data.strip()
        if not text:
            return
        if self._heading_level is not None:
            self._heading_chunks.append(text)
            return
        if not self._lines:
            self._lines.append(text)
            return
        if self._lines[-1] == "":
            self._lines.append(text)
        else:
            self._lines[-1] = self._lines[-1].rstrip() + " " + text

    def _ensure_blank_line(self) -> None:
        if not self._lines:
            return
        if self._lines[-1] != "":
            self._lines.append("")

    def markdown(self) -> str:
        return "\n".join(self._lines).strip()


def _looks_like_html(text: str) -> bool:
    return "<" in text and ">" in text and re.search(r"</?[a-zA-Z]", text) is not None


def _html_to_markdown(text: str) -> str:
    parser = _HtmlToMarkdown()
    parser.feed(text)
    return parser.markdown()


def _collect_text_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        results: list[str] = []
        for item in value:
            results.extend(_collect_text_values(item))
        return results
    text = getattr(value, "text", None)
    if isinstance(text, str) and text.strip():
        return [text.strip()]
    return []


def _first_text(value: object) -> Optional[str]:
    values = _collect_text_values(value)
    return values[0] if values else None


def _get_metadata_value(metadata: object, names: Iterable[str]) -> Optional[object]:
    if metadata is None:
        return None
    fields = getattr(metadata, "fields", None)
    if isinstance(fields, dict):
        for name in names:
            if name in fields and fields[name]:
                return fields[name]
    for name in names:
        try:
            value = getattr(metadata, name)
        except Exception:
            continue
        if value:
            return value
    return None


def _get_metadata_title(metadata: object) -> Optional[str]:
    value = _get_metadata_value(metadata, ("title", "titles", "dc_title"))
    if value is None:
        return None
    text = _first_text(value)
    return text


def _get_metadata_authors(metadata: object) -> Optional[str]:
    value = _get_metadata_value(metadata, ("creator", "creators", "authors", "contributors"))
    if value is None:
        return None
    texts = _collect_text_values(value)
    return ", ".join(texts) if texts else None


def _content_to_text(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    for attr in ("to_str", "to_plain", "inner_text"):
        if hasattr(content, attr):
            value = getattr(content, attr)
            try:
                result = value() if callable(value) else value
            except Exception:
                continue
            if isinstance(result, str):
                return result
    return str(content)


def _slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    value = value.strip("_.-")
    return value or "book"


def _prettify_section_name(value: str) -> str:
    base = Path(value).stem
    base = re.sub(r"[_-]+", " ", base).strip()
    return base.title() if base else value


def _get_content(doc: Document, content_id: str):
    if hasattr(doc, "find_content_by_id"):
        return doc.find_content_by_id(content_id)
    if hasattr(doc, "get_content"):
        return doc.get_content(content_id)
    raise AttributeError("Document has no find_content_by_id or get_content")


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_epub(epub_path: Path, output_dir: Path) -> Optional[Path]:
    doc = Document(str(epub_path))
    metadata = doc.package.metadata
    title = _get_metadata_title(metadata) or epub_path.stem
    authors = _get_metadata_authors(metadata)

    manifest_items = {
        item.get("id"): item
        for item in getattr(doc.package.manifest, "items", [])
        if isinstance(item, dict) and item.get("id")
    }

    sections: list[tuple[str, str]] = []
    for spine_item in getattr(doc.package.spine, "itemrefs", []):
        if isinstance(spine_item, dict):
            content_id = spine_item.get("idref") or spine_item.get("id")
        else:
            content_id = getattr(spine_item, "idref", None) or getattr(spine_item, "id", None)
        if not content_id:
            continue
        try:
            content = _get_content(doc, content_id)
        except Exception:
            continue
        raw_text = _content_to_text(content)
        if not raw_text.strip():
            continue
        if _looks_like_html(raw_text):
            raw_text = _html_to_markdown(raw_text)
        text = _normalize_text(raw_text)
        if not text:
            continue

        manifest_item = manifest_items.get(content_id)
        section_name = None
        if manifest_item is not None:
            section_name = manifest_item.get("href")
        section_name = section_name or content_id
        sections.append((_prettify_section_name(section_name), text))

    if not sections:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{_slugify(title)}.md"

    lines: list[str] = [f"# {title}"]
    if authors:
        lines.append(f"**Author:** {authors}")
    lines.append("")

    for section_title, section_text in sections:
        lines.append(f"## {section_title}")
        lines.append("")
        lines.append(section_text)
        lines.append("")

    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return output_path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    default_input = repo_root / "assets"
    default_output = Path(__file__).resolve().parent / "results"

    parser = argparse.ArgumentParser(
        description="Parse EPUB files into Markdown using epub-utils."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=default_input,
        help=f"Directory containing EPUB files (default: {default_input})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output,
        help=f"Output directory for Markdown files (default: {default_output})",
    )
    args = parser.parse_args()

    epub_paths = sorted(args.input_dir.rglob("*.epub"))
    if not epub_paths:
        print(f"No EPUB files found under {args.input_dir}")
        return 1

    failures = 0
    for epub_path in epub_paths:
        try:
            output_path = parse_epub(epub_path, args.output_dir)
        except Exception as exc:
            failures += 1
            print(f"Failed to parse {epub_path.name}: {exc}")
            continue
        if output_path is None:
            failures += 1
            print(f"No readable content in {epub_path.name}")
        else:
            print(f"Wrote {output_path}")

    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
