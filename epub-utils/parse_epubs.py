"""Parse EPUB files in assets and emit Markdown into epub-utils/results."""

from __future__ import annotations

import argparse
import posixpath
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from epub_utils import Document

from lxml import etree


_SECTION_CONTAINER_TAGS = {"section", "article", "div", "body"}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_XHTML_MEDIA_TYPES = {"application/xhtml+xml", "text/html"}


@dataclass(frozen=True)
class TocEntry:
    label: str
    href: str
    fragment: Optional[str]
    order: int


@dataclass
class ContentData:
    idref: str
    href: str
    xml: str
    tree: Optional[etree._Element]


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
    HEADING_TAGS = _HEADING_TAGS
    IGNORE_TAGS = {"head", "title", "style", "script", "svg"}

    def __init__(self, image_resolver: Optional[Callable[[str, str], Optional[str]]] = None) -> None:
        super().__init__()
        self._lines: list[str] = []
        self._heading_level: Optional[int] = None
        self._heading_chunks: list[str] = []
        self._ignore_depth = 0
        self._image_resolver = image_resolver

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        tag = tag.lower()
        if tag in self.IGNORE_TAGS:
            self._ignore_depth += 1
            return
        if self._ignore_depth:
            return
        if tag == "img":
            attr_map = {key.lower(): value for key, value in attrs}
            src = attr_map.get("src", "") or ""
            alt = attr_map.get("alt", "") or ""
            resolved = None
            if self._image_resolver:
                resolved = self._image_resolver(src, alt)
            if resolved:
                self._ensure_blank_line()
                self._lines.append(f"![{alt}]({resolved})")
                self._ensure_blank_line()
            return
        if tag in self.HEADING_TAGS:
            self._heading_level = int(tag[1])
            self._heading_chunks = []
            self._ensure_blank_line()
            return
        if tag in self.BLOCK_TAGS:
            self._ensure_blank_line()

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        tag = tag.lower()
        if tag in self.IGNORE_TAGS:
            if self._ignore_depth:
                self._ignore_depth -= 1
            return
        if self._ignore_depth:
            return
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
        if self._ignore_depth:
            return
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

    def handle_startendtag(self, tag: str, attrs) -> None:  # type: ignore[override]
        tag = tag.lower()
        if tag in self.IGNORE_TAGS or self._ignore_depth:
            return
        if tag == "img":
            attr_map = {key.lower(): value for key, value in attrs}
            src = attr_map.get("src", "") or ""
            alt = attr_map.get("alt", "") or ""
            resolved = None
            if self._image_resolver:
                resolved = self._image_resolver(src, alt)
            if resolved:
                self._ensure_blank_line()
                self._lines.append(f"![{alt}]({resolved})")
                self._ensure_blank_line()
            return
        if tag in self.BLOCK_TAGS:
            self._ensure_blank_line()

    def _ensure_blank_line(self) -> None:
        if not self._lines:
            return
        if self._lines[-1] != "":
            self._lines.append("")

    def markdown(self) -> str:
        return "\n".join(self._lines).strip()


def _looks_like_html(text: str) -> bool:
    return "<" in text and ">" in text and re.search(r"</?[a-zA-Z]", text) is not None


def _html_to_markdown(
    text: str, image_resolver: Optional[Callable[[str, str], Optional[str]]] = None
) -> str:
    parser = _HtmlToMarkdown(image_resolver=image_resolver)
    parser.feed(text)
    return parser.markdown()


def _normalize_href(value: str) -> str:
    value = value.strip().replace("\\", "/")
    value = value.split("?", 1)[0]
    return posixpath.normpath(value).lstrip("./")


def _is_external_src(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered.startswith(("http://", "https://", "data:"))


def _zip_namelist_map(epub_zip: zipfile.ZipFile) -> dict[str, str]:
    return {
        posixpath.normpath(name).lstrip("./"): name
        for name in epub_zip.namelist()
    }


def _zip_has(namelist_map: dict[str, str], path: str) -> bool:
    return posixpath.normpath(path).lstrip("./") in namelist_map


def _extract_zip_file(
    epub_zip: zipfile.ZipFile,
    namelist_map: dict[str, str],
    zip_path: str,
    output_path: Path,
) -> bool:
    normalized = posixpath.normpath(zip_path).lstrip("./")
    if normalized not in namelist_map:
        return False
    data = epub_zip.read(namelist_map[normalized])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)
    return True


def _split_target(target: str) -> tuple[str, Optional[str]]:
    if not target:
        return "", None
    href, _, fragment = target.partition("#")
    return href, fragment or None


def _flatten_toc_items(items: Iterable[object]) -> Iterable[object]:
    for item in items:
        yield item
        children = getattr(item, "children", None)
        if children:
            yield from _flatten_toc_items(children)


def _resolve_href(
    href: str, manifest_by_href: dict[str, dict], manifest_by_basename: dict[str, str]
) -> Optional[str]:
    if not href:
        return None
    normalized = _normalize_href(href)
    if normalized in manifest_by_href:
        return normalized
    while normalized.startswith("../"):
        normalized = normalized[3:]
        if normalized in manifest_by_href:
            return normalized
    basename = posixpath.basename(normalized)
    if basename in manifest_by_basename:
        return manifest_by_basename[basename]
    matches = [key for key in manifest_by_href if key.endswith(f"/{basename}")]
    if len(matches) == 1:
        return matches[0]
    return None


def _build_toc_entries(
    doc: Document, manifest_by_href: dict[str, dict], spine_hrefs: set[str]
) -> list[TocEntry]:
    toc = doc.toc
    if toc is None:
        return []
    try:
        toc_items = toc.get_toc_items()
    except Exception:
        return []
    manifest_by_basename: dict[str, str] = {}
    basenames: dict[str, list[str]] = {}
    for href in manifest_by_href:
        base = posixpath.basename(href)
        basenames.setdefault(base, []).append(href)
    for base, hrefs in basenames.items():
        if len(hrefs) == 1:
            manifest_by_basename[base] = hrefs[0]

    entries: list[TocEntry] = []
    order = 0
    for item in _flatten_toc_items(toc_items):
        target = (getattr(item, "target", None) or "").strip()
        label = (getattr(item, "label", None) or "").strip()
        href, fragment = _split_target(target)
        resolved = _resolve_href(href, manifest_by_href, manifest_by_basename)
        if not resolved or resolved not in spine_hrefs:
            continue
        if not label:
            label = _prettify_section_name(resolved)
        entries.append(TocEntry(label=label, href=resolved, fragment=fragment, order=order))
        order += 1
    return entries


def _load_content(doc: Document, idref: str, href: str) -> ContentData:
    content = _get_content(doc, idref)
    xml = getattr(content, "xml_content", None) or str(content)
    tree = None
    try:
        tree = etree.fromstring(xml.encode("utf-8"))
    except Exception:
        tree = None
    return ContentData(idref=idref, href=href, xml=xml, tree=tree)


def _element_local_name(element) -> str:
    tag = element.tag
    if isinstance(tag, str) and "}" in tag:
        return tag.split("}", 1)[1]
    return tag if isinstance(tag, str) else ""


def _is_heading(element) -> bool:
    return _element_local_name(element).lower() in _HEADING_TAGS


def _heading_level(element) -> int:
    name = _element_local_name(element).lower()
    return int(name[1]) if name.startswith("h") and len(name) == 2 else 0


def _find_anchor_node(tree, fragment: str):
    if tree is None or not fragment:
        return None
    matches = tree.xpath(f'//*[@id="{fragment}"]')
    if matches:
        return matches[0]
    matches = tree.xpath(f'//*[local-name()="a" and @name="{fragment}"]')
    return matches[0] if matches else None


def _find_section_container(node, allow_body: bool) -> Optional[object]:
    current = node
    while current is not None:
        tag = _element_local_name(current).lower()
        if tag in _SECTION_CONTAINER_TAGS:
            if tag == "body" and not allow_body:
                return None
            return current
        current = current.getparent()
    return None


def _collect_heading_section_nodes(heading) -> list[object]:
    parent = heading.getparent()
    if parent is None:
        return [heading]
    siblings = list(parent)
    try:
        start_index = siblings.index(heading)
    except ValueError:
        return [heading]
    level = _heading_level(heading)
    nodes: list[object] = []
    for sibling in siblings[start_index:]:
        if sibling is not heading and _is_heading(sibling):
            if _heading_level(sibling) <= level:
                break
        nodes.append(sibling)
    return nodes or [heading]


def _section_nodes_from_anchor(anchor, allow_body: bool) -> list[object]:
    node = anchor
    tag = _element_local_name(node).lower()
    if tag in {"a", "span"} and not list(node) and not (node.text or "").strip():
        next_node = node.getnext()
        if next_node is not None:
            node = next_node
    if _is_heading(node):
        return _collect_heading_section_nodes(node)
    container = _find_section_container(node, allow_body=allow_body)
    if container is not None:
        return [container]
    return [node]


def _nodes_to_html(nodes: Iterable[object]) -> str:
    return "\n".join(etree.tostring(node, encoding="unicode") for node in nodes)


def _render_markdown(
    html: str, image_resolver: Optional[Callable[[str, str], Optional[str]]] = None
) -> str:
    if not html.strip():
        return ""
    if _looks_like_html(html):
        html = _html_to_markdown(html, image_resolver=image_resolver)
    return _normalize_text(html)


def _extract_section_markdown(
    content: ContentData,
    fragment: str,
    allow_body: bool,
    image_resolver: Optional[Callable[[str, str], Optional[str]]] = None,
) -> Optional[str]:
    anchor = _find_anchor_node(content.tree, fragment)
    if anchor is None:
        return None
    nodes = _section_nodes_from_anchor(anchor, allow_body=allow_body)
    if not nodes:
        return None
    return _render_markdown(_nodes_to_html(nodes), image_resolver=image_resolver)


def _render_full_markdown(
    content: ContentData, image_resolver: Optional[Callable[[str, str], Optional[str]]] = None
) -> str:
    if content.tree is not None:
        body_nodes = content.tree.xpath('//*[local-name()="body"]')
        if body_nodes:
            return _render_markdown(_nodes_to_html(body_nodes), image_resolver=image_resolver)
    return _render_markdown(content.xml, image_resolver=image_resolver)


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


def parse_epub(epub_path: Path, output_dir: Path, media_all: bool = False) -> Optional[Path]:
    doc = Document(str(epub_path))
    metadata = doc.package.metadata
    title = _get_metadata_title(metadata) or epub_path.stem
    authors = _get_metadata_authors(metadata)
    book_slug = _slugify(title)

    manifest_list = [
        item
        for item in getattr(doc.package.manifest, "items", [])
        if isinstance(item, dict)
    ]
    manifest_by_id = {item.get("id"): item for item in manifest_list if item.get("id")}
    manifest_by_href = {
        _normalize_href(item.get("href")): item
        for item in manifest_list
        if item.get("href")
    }

    spine_entries: list[tuple[str, str]] = []
    for spine_item in getattr(doc.package.spine, "itemrefs", []):
        if isinstance(spine_item, dict):
            content_id = spine_item.get("idref") or spine_item.get("id")
        else:
            content_id = getattr(spine_item, "idref", None) or getattr(spine_item, "id", None)
        if not content_id:
            continue
        manifest_item = manifest_by_id.get(content_id)
        if not manifest_item:
            continue
        href = manifest_item.get("href")
        if not href:
            continue
        if manifest_item.get("media_type") not in _XHTML_MEDIA_TYPES:
            continue
        spine_entries.append((content_id, _normalize_href(href)))

    spine_hrefs_set = {href for _, href in spine_entries}
    spine_href_to_idref = {href: content_id for content_id, href in spine_entries}
    toc_entries = _build_toc_entries(doc, manifest_by_href, spine_hrefs_set)

    content_cache: dict[str, ContentData] = {}

    def get_content_data(href: str) -> Optional[ContentData]:
        if href in content_cache:
            return content_cache[href]
        idref = spine_href_to_idref.get(href)
        if not idref:
            return None
        try:
            data = _load_content(doc, idref, href)
        except Exception:
            return None
        content_cache[href] = data
        return data

    sections: list[tuple[str, str]] = []

    image_output_root = output_dir / book_slug / "images"
    extracted_images: dict[str, str] = {}
    extracted_count = 0

    with zipfile.ZipFile(epub_path, "r") as epub_zip:
        zip_map = _zip_namelist_map(epub_zip)

        def extract_media_href(href: str) -> Optional[str]:
            nonlocal extracted_count
            if href in extracted_images:
                return extracted_images[href]
            zip_path = posixpath.join(doc.package_href, href)
            output_path = image_output_root / href
            if not _extract_zip_file(epub_zip, zip_map, zip_path, output_path):
                return None
            rel_path = f"./{book_slug}/images/{href}"
            extracted_images[href] = rel_path
            extracted_count += 1
            return rel_path

        if media_all:
            for item in manifest_list:
                media_type = item.get("media_type") or ""
                if not media_type.startswith("image/"):
                    continue
                href = item.get("href")
                if not href:
                    continue
                normalized = _normalize_href(href)
                extract_media_href(normalized)

        def make_image_resolver(base_href: str) -> Callable[[str, str], Optional[str]]:
            def resolve_image(src: str, alt: str) -> Optional[str]:
                if not src or _is_external_src(src):
                    return src or None
                resolved = _normalize_href(
                    posixpath.join(posixpath.dirname(base_href), src)
                )
                manifest_item = manifest_by_href.get(resolved)
                if manifest_item:
                    href = resolved
                else:
                    zip_path = posixpath.join(doc.package_href, resolved)
                    if not _zip_has(zip_map, zip_path):
                        return src
                    href = resolved
                extracted = extract_media_href(href)
                return extracted or src

            return resolve_image

        if toc_entries:
            sections_by_entry: list[Optional[tuple[str, str]]] = [None] * len(toc_entries)
            href_counts: dict[str, int] = {}
            for entry in toc_entries:
                href_counts[entry.href] = href_counts.get(entry.href, 0) + 1
            href_has_section = {href: False for href in href_counts}
            first_index_by_href: dict[str, int] = {}
            seen_texts_by_href: dict[str, set[str]] = {
                href: set() for href in href_counts
            }

            for idx, entry in enumerate(toc_entries):
                first_index_by_href.setdefault(entry.href, idx)
                content_data = get_content_data(entry.href)
                if content_data is None:
                    continue
                image_resolver = make_image_resolver(content_data.href)
                allow_body = href_counts[entry.href] == 1
                text = None
                if entry.fragment:
                    text = _extract_section_markdown(
                        content_data,
                        entry.fragment,
                        allow_body=allow_body,
                        image_resolver=image_resolver,
                    )
                elif allow_body:
                    text = _render_full_markdown(content_data, image_resolver=image_resolver)
                if text:
                    if text in seen_texts_by_href[entry.href]:
                        continue
                    seen_texts_by_href[entry.href].add(text)
                    sections_by_entry[idx] = (entry.label, text)
                    href_has_section[entry.href] = True

            for href, has_section in href_has_section.items():
                if has_section:
                    continue
                first_index = first_index_by_href.get(href)
                if first_index is None:
                    continue
                content_data = get_content_data(href)
                if content_data is None:
                    continue
                image_resolver = make_image_resolver(content_data.href)
                text = _render_full_markdown(content_data, image_resolver=image_resolver)
                if not text:
                    continue
                sections_by_entry[first_index] = (toc_entries[first_index].label, text)

            sections = [section for section in sections_by_entry if section]
        else:
            for _, href in spine_entries:
                content_data = get_content_data(href)
                if content_data is None:
                    continue
                image_resolver = make_image_resolver(content_data.href)
                text = _render_full_markdown(content_data, image_resolver=image_resolver)
                if not text:
                    continue
                sections.append((_prettify_section_name(href), text))

    if not sections:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{book_slug}.md"

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
    if extracted_count:
        print(f"Extracted {extracted_count} images for {title}")
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
    parser.add_argument(
        "--media-all",
        action="store_true",
        help="Extract all manifest images, not just those referenced in content.",
    )
    args = parser.parse_args()

    epub_paths = sorted(args.input_dir.rglob("*.epub"))
    if not epub_paths:
        print(f"No EPUB files found under {args.input_dir}")
        return 1

    failures = 0
    for epub_path in epub_paths:
        try:
            output_path = parse_epub(epub_path, args.output_dir, media_all=args.media_all)
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
