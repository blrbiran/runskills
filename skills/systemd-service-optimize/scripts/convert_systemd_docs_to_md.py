#!/usr/bin/env python3
"""Convert local systemd HTML manpages under doc/ into Markdown references."""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from markdownify import markdownify as md


def extract_saved_url(raw_html: str) -> str | None:
    # Example: <!-- saved from url=(0086)https://... -->
    m = re.search(r"saved from url=\(\d+\)(\S+)", raw_html)
    return m.group(1) if m else None


def normalize_markdown(text: str) -> str:
    text = text.replace("¶", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def convert_one(html_path: Path, out_dir: Path) -> Path:
    raw = html_path.read_text(encoding="utf-8", errors="ignore")
    saved_url = extract_saved_url(raw)
    soup = BeautifulSoup(raw, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    for tag in soup.select("a.headerlink"):
        tag.decompose()

    title = (soup.title.get_text(strip=True) if soup.title else html_path.stem) or html_path.stem

    # Keep only the manpage body to drop top nav, version selector, etc.
    main = soup.select_one("div.refentry")
    if main is None:
        main = soup.body if soup.body is not None else soup

    body_md = md(
        str(main),
        heading_style="ATX",
        bullets="-",
        strip=["span"],
    )
    body_md = normalize_markdown(body_md)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    header = [
        f"# {title}",
        "",
        f"- Source file: `{html_path.name}`",
        f"- Generated (UTC): `{generated_at}`",
    ]
    if saved_url:
        header.append(f"- Original URL: `{saved_url}`")
    header.extend(["", "---", ""])

    out_path = out_dir / f"{html_path.stem}.md"
    out_path.write_text("\n".join(header) + body_md, encoding="utf-8")
    return out_path


def build_index(out_dir: Path, converted: list[Path]) -> None:
    lines = [
        "# Systemd Manpages (Converted)",
        "",
        "Converted from local HTML files under `doc/`.",
        "",
    ]
    for path in sorted(converted):
        lines.append(f"- `{path.name}`")
    lines.append("")
    (out_dir / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--doc-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "doc",
        help="Directory containing downloaded systemd HTML files",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "references" / "systemd-manpages",
        help="Directory for converted markdown files",
    )
    args = parser.parse_args()

    if not args.doc_dir.exists():
        raise SystemExit(f"doc dir not found: {args.doc_dir}")

    html_files = sorted(args.doc_dir.glob("*.html"))
    if not html_files:
        raise SystemExit(f"no html files found in: {args.doc_dir}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    converted: list[Path] = []
    for html_path in html_files:
        converted.append(convert_one(html_path, args.out_dir))

    build_index(args.out_dir, converted)
    print(f"Converted {len(converted)} files into {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
