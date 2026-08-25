#!/usr/bin/env python3
"""Export a frozen pack for viewer-react-static (public read-only viewer).

Reads canonical stage artifacts from output/<run>/ and slim trees + a
manifest + optionally the PDF into static-export/<doc>/. Never writes into
output/ or pdfs/. Flags, phrase/token provenance, calibration, and QA detail
are intentionally dropped; see docs/STATIC_VIEWER_CONTRACT.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from etl._shared.artifacts import STAGE_DIRS  # noqa: E402
from etl._shared.prexc import parse_prexc  # noqa: E402
from etl._shared.pap_label_anatomy import enrich_pap_label  # noqa: E402
from etl._shared.timestamps import iso_now  # noqa: E402

MANIFEST_FORMAT = 1
TREE_FORMAT = 2
AMOUNT_KEYS = ("text", "value")
TOTAL_KEYS = ("role", "text", "value")
# Semantic reading is anchored at the rightmost amount column and assigned
# leftward (root page headers only; Total is the anchor, then CO, MOOE, PS).
BY_OU_ANCHOR_ROLES = ("Total", "CO", "MOOE", "PS")
# The PAP table carries a single amount column; its root-page header text is
# the canonical name for it.
PAP_COLUMN_NAME = "AMOUNT (Php)"
TREE_STAGES = {
    "by-ou": ("by_ou_tree", "By Operating Unit"),
    "pap": ("pap_tree", "PAP"),
}
# Public downloadable data files, one JSON + CSV pair per tree. The filename
# prefix is document-specific (volume + department) and passed via
# --file-prefix; both prefix and stem are kebab-cased into the final name.
DATA_SPECS = {
    "by-ou": {
        "stem": "by-operating-units",
        "columns": [
            "row_index", "id", "kind", "page", "tier_pdf", "label", "code",
            "parent_id_pdf", "parent_id_prexc", "depth_pdf", "depth_prexc",
            "prexc_identifier", "ps", "mooe", "co", "total",
        ],
        "amount_columns": {"ps": "PS", "mooe": "MOOE", "co": "CO", "total": "Total"},
    },
    "pap": {
        "stem": "by-pap",
        "columns": [
            "row_index", "id", "kind", "page", "tier_pdf", "label", "code",
            "parent_id", "amount", "chainages", "lat", "lon",
        ],
        "amount_columns": {"amount": "AMOUNT (Php)"},
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True,
                        help="run directory name under output/")
    parser.add_argument("--doc", default=None,
                        help="public document id (defaults to the run name)")
    parser.add_argument("--title", default=None,
                        help="human-readable document title")
    parser.add_argument("--out", default="static-export",
                        help="export root directory (default: static-export)")
    parser.add_argument("--trees", default="by-ou,pap",
                        help="comma-separated tree ids to export (by-ou,pap)")
    parser.add_argument("--pdf", choices=("copy", "url", "none"), default="copy",
                        help="copy the PDF into the pack, record a remote URL, or omit")
    parser.add_argument("--pdf-url", default=None,
                        help="absolute URL used with --pdf url")
    parser.add_argument("--no-linearize", action="store_true",
                        help="with --pdf copy, skip Fast Web View rewriting "
                             "(default: linearize via qpdf or pikepdf)")
    parser.add_argument("--file-prefix", "--csv-prefix", dest="file_prefix",
                        default=None,
                        help="public data filename prefix, e.g. 'NEP-VOL2B DPWH'"
                             " (kebab-cased into both .json and .csv names;"
                             " omit for short ids)")
    return parser.parse_args()


def pdf_looks_linearized(path: Path) -> bool:
    """True when the file header advertises /Linearized (Fast Web View)."""
    with path.open("rb") as handle:
        return b"/Linearized" in handle.read(2048)


def copy_pdf_to_pack(source: Path, target: Path, *, linearize: bool = True) -> bool:
    """Write ``source`` into ``target``. Returns whether the output is linearized.

    Prefer the ``qpdf`` CLI when present; otherwise ``pikepdf``. Plain
    ``shutil.copyfile`` when ``linearize`` is false.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    if not linearize:
        shutil.copyfile(source, target)
        return pdf_looks_linearized(target)

    qpdf = shutil.which("qpdf")
    if qpdf:
        subprocess.run(
            [qpdf, "--linearize", "--", str(source), str(target)],
            check=True,
        )
        return pdf_looks_linearized(target)

    try:
        import pikepdf
    except ImportError as exc:
        raise SystemExit(
            "PDF linearization needs `qpdf` on PATH or the `pikepdf` package. "
            "Install one (e.g. `pip install pikepdf`), or pass --no-linearize."
        ) from exc

    with pikepdf.open(source) as pdf:
        pdf.save(target, linearize=True)
    return pdf_looks_linearized(target)


def kebab_slug(value: str) -> str:
    """Lowercase, drop commas, collapse non-alnum runs into single hyphens."""
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return value


def slim_amount(amount: Any) -> dict[str, Any] | None:
    if not isinstance(amount, dict):
        return None
    slim = {key: amount.get(key) for key in AMOUNT_KEYS}
    return slim if any(slim.values()) else None


def slim_total(total: Any) -> dict[str, Any] | None:
    if not isinstance(total, dict):
        return None
    slim = {key: total.get(key) for key in TOTAL_KEYS}
    return slim if slim.get("text") else None


def resolve_by_ou_columns(nodes: list[dict[str, Any]]) -> dict[int, dict[str, str]]:
    """Map generic `Amount N` keys to semantic roles per page.

    `Amount N` ordinals encode left-to-right column order on each page. The
    semantic reading is anchored at the rightmost data-carrying column and
    assigned leftward: Total, CO, MOOE, PS (root-page headers only exist on
    the seed page, so every other page is resolved by this anchor rule).
    Ordinals that carry no data on the page are placeholders and are ignored,
    which handles terminal pages with detected-but-empty OCR columns.
    """
    ordinal = lambda role: (int(role.rsplit(" ", 1)[-1]) if role.rsplit(" ", 1)[-1].isdigit() else 0)
    per_page: dict[int, set[str]] = {}
    for node in nodes:
        page = node.get("page")
        if not isinstance(page, int):
            continue
        for role in (node.get("amounts") or {}):
            if role not in BY_OU_ANCHOR_ROLES:
                per_page.setdefault(page, set()).add(role)
    pages: dict[int, dict[str, str]] = {}
    for page, roles in per_page.items():
        ordered = sorted(roles, key=ordinal)
        mapping = {role: BY_OU_ANCHOR_ROLES[offset]
                   for offset, role in enumerate(reversed(ordered))
                   if offset < len(BY_OU_ANCHOR_ROLES)}
        pages[page] = mapping
    return pages


def rewrite_amounts(node: dict[str, Any],
                    mapping: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    amounts = {mapping.get(role, role): slim
               for role, value in (node.get("amounts") or {}).items()
               if (slim := slim_amount(value))}
    total = slim_total(node.get("total"))
    if total and total.get("role"):
        total["role"] = mapping.get(total["role"], total["role"])
    return amounts, total


def tier_pdf_value(node: dict[str, Any]) -> Any:
    if "tier_pdf" in node:
        return node.get("tier_pdf")
    return node.get("tier")


def slim_node(node: dict[str, Any], mapping: dict[str, str] | None = None,
              *, dual_hierarchy: bool = False, row_index: int = 0) -> dict[str, Any]:
    key_map = mapping or {}
    amounts, total = rewrite_amounts(node, key_map)
    code = node.get("code")
    slim: dict[str, Any] = {
        "row_index": row_index,
        "id": node.get("id"),
        "kind": node.get("kind"),
        "page": node.get("page"),
        "tier_pdf": tier_pdf_value(node),
        "label": node.get("label"),
        "code": code,
        "bbox": node.get("bbox"),
        "amounts": amounts,
        "total": total,
    }
    if dual_hierarchy:
        slim["parent_pdf"] = node.get("parent_pdf")
        slim["parent_prexc"] = node.get("parent_prexc")
        parsed = parse_prexc(code) if code else None
        if parsed:
            slim["prexc"] = parsed
    else:
        slim["parent"] = node.get("parent")
        slim["children"] = node.get("children") or []
        if node.get("label_ocr"):
            slim["label_ocr"] = node["label_ocr"]
        if node.get("description"):
            slim["description"] = node["description"]
        if node.get("chainages"):
            slim["chainages"] = node["chainages"]
        if node.get("coordinates"):
            slim["coordinates"] = node["coordinates"]
    return slim


def pap_node_anatomy(node: dict[str, Any]) -> dict[str, Any]:
    """Return stripped label + anatomy fields, enriching from OCR when needed."""
    source = node.get("label_ocr") or str(node.get("label") or "")
    enriched = enrich_pap_label(
        source,
        label_raw=node.get("label_raw"),
        line_metrics=node.get("label_line_metrics"),
    )
    if enriched["label_ocr"]:
        return enriched
    return {
        "label": node.get("label"),
        "label_ocr": node.get("label_ocr"),
        "description": node.get("description"),
        "chainages": node.get("chainages"),
        "coordinates": node.get("coordinates"),
    }


def compute_depths(nodes: list[dict[str, Any]], parent_key: str) -> dict[str, int]:
    by_id = {node["id"]: node for node in nodes}
    depth: dict[str, int] = {}

    def depth_of(nid: str, seen: set[str] | None = None) -> int:
        if nid in depth:
            return depth[nid]
        seen = seen or set()
        if nid in seen:
            return 0
        seen.add(nid)
        node = by_id.get(nid)
        parent = node.get(parent_key) if node else None
        value = 0 if not parent or parent not in by_id else depth_of(parent, seen) + 1
        depth[nid] = value
        return value

    for node in nodes:
        depth_of(node["id"])
    return depth


def validate_tree(slim: dict[str, Any], source: Path) -> None:
    nodes = slim["nodes"]
    ids = {node["id"] for node in nodes}
    if len(ids) != len(nodes):
        raise ValueError(f"Duplicate node ids in {source}")
    indices = [node.get("row_index") for node in nodes]
    if indices != list(range(len(nodes))):
        raise ValueError(f"row_index must be 0..{len(nodes) - 1} in document order in {source}")
    roots = slim["roots"]
    if not roots:
        raise ValueError(f"Tree has no roots: {source}")
    by_id = {node["id"]: node for node in nodes}
    dual = bool(slim.get("hierarchy_modes"))
    parent_fields = ("parent_pdf", "parent_prexc") if dual else ("parent",)
    for node in nodes:
        if "tier_pdf" not in node:
            raise ValueError(f"Node {node['id']} missing tier_pdf in {source}")
        if node["id"] in roots:
            for field in parent_fields:
                if node.get(field) is not None:
                    raise ValueError(f"Root {node['id']} has {field} in {source}")
            continue
        for field in parent_fields:
            parent = node.get(field)
            if parent not in ids:
                raise ValueError(f"Node {node['id']} has unresolvable {field} "
                                 f"{parent!r} in {source}")
        if dual:
            if node.get("parent") is not None:
                raise ValueError(f"Node {node['id']} must not carry parent in format 2 dual tree")
            if node["bbox"] is not None and node["page"] is None:
                raise ValueError(f"Node {node['id']} has bbox without page in {source}")
            continue
        for child in node.get("children") or []:
            if child not in ids:
                raise ValueError(f"Node {node['id']} references missing child "
                                 f"{child!r} in {source}")
            if by_id[child]["parent"] != node["id"]:
                raise ValueError(f"Child {child!r} disagrees about its parent "
                                 f"in {source}")
        if node["bbox"] is not None and node["page"] is None:
            raise ValueError(f"Node {node['id']} has bbox without page in {source}")


def csv_amount(node: dict[str, Any], amount_role: str) -> Any:
    """Numeric value of one amount role, preferring the row's total if it
    carries the same role (OCR sometimes splits a row into several)."""
    total = node.get("total")
    if isinstance(total, dict) and total.get("role") == amount_role:
        value = total.get("value")
        if value is not None:
            return value
    amount = (node.get("amounts") or {}).get(amount_role)
    return amount.get("value") if isinstance(amount, dict) else None


def csv_row_values(node: dict[str, Any], tree_id: str,
                   depth_pdf: dict[str, int] | None = None,
                   depth_prexc: dict[str, int] | None = None) -> dict[str, Any]:
    spec = DATA_SPECS[tree_id]
    row: dict[str, Any] = {
        "row_index": node.get("row_index"),
        "id": node.get("id"),
        "kind": node.get("kind") or "",
        "page": node.get("page"),
        "tier_pdf": node.get("tier_pdf"),
        "label": node.get("label") or "",
        "code": node.get("code") or "",
    }
    if tree_id == "by-ou":
        row.update({
            "parent_id_pdf": node.get("parent_pdf") or "",
            "parent_id_prexc": node.get("parent_prexc") or "",
            "depth_pdf": depth_pdf.get(node["id"], "") if depth_pdf else "",
            "depth_prexc": depth_prexc.get(node["id"], "") if depth_prexc else "",
            "prexc_identifier": (node.get("prexc") or {}).get("identifier", ""),
        })
    else:
        row["parent_id"] = node.get("parent") or ""
        chainages = node.get("chainages")
        row["chainages"] = json.dumps(chainages, ensure_ascii=False) if chainages else ""
        coords = node.get("coordinates") or []
        first = coords[0] if coords else {}
        row["lat"] = first.get("lat", "")
        row["lon"] = first.get("lon", "")
    for column, role in spec["amount_columns"].items():
        row[column] = csv_amount(node, role)
    return row


def write_tree_csv(slim: dict[str, Any], tree_id: str, basename: str,
                   out_dir: Path) -> str:
    """Write the public CSV companion for one tree; returns its pack path."""
    spec = DATA_SPECS[tree_id]
    nodes = slim["nodes"]
    depth_pdf = compute_depths(nodes, "parent_pdf") if tree_id == "by-ou" else None
    depth_prexc = compute_depths(nodes, "parent_prexc") if tree_id == "by-ou" else None
    target = out_dir / "trees" / f"{basename}.csv"
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(spec["columns"])
        for node in nodes:
            if node.get("kind") == "table_root":
                continue
            row = csv_row_values(node, tree_id, depth_pdf, depth_prexc)
            writer.writerow([row.get(column) for column in spec["columns"]])
    return f"trees/{target.name}"


def tree_basename(tree_id: str, prefix: str | None) -> str:
    """Public filename stem for one tree (no extension), kebab-case."""
    if prefix and tree_id in DATA_SPECS:
        return f"{kebab_slug(prefix)}-{DATA_SPECS[tree_id]['stem']}"
    return tree_id


def export_tree(tree_id: str, stage_name: str, run_root: Path, out_dir: Path,
                label: str, file_prefix: str | None = None) -> dict[str, Any]:
    source = run_root / STAGE_DIRS[stage_name] / "tree.json"
    tree = read_json(source)
    raw_nodes = tree.get("nodes") or []
    if tree_id == "by-ou":
        raw_nodes = [node for node in raw_nodes if not node.get("synthetic")]
    column_map = (resolve_by_ou_columns(raw_nodes) if tree_id == "by-ou" else {})
    pap_name = PAP_COLUMN_NAME if tree_id == "pap" else None
    dual_hierarchy = tree_id == "by-ou"
    nodes = []
    for row_index, node in enumerate(raw_nodes):
        mapping = column_map.get(int(node.get("page") or -1), {}) if node.get("page") else {}
        if pap_name:
            mapping = {role: pap_name for role in (node.get("amounts") or {})}
        slim = slim_node(node, mapping, dual_hierarchy=dual_hierarchy, row_index=row_index)
        if pap_name:
            anatomy = pap_node_anatomy(node)
            slim["label"] = anatomy["label"]
            if anatomy.get("label_ocr"):
                slim["label_ocr"] = anatomy["label_ocr"]
            if anatomy.get("description"):
                slim["description"] = anatomy["description"]
            if anatomy.get("chainages"):
                slim["chainages"] = anatomy["chainages"]
            if anatomy.get("coordinates"):
                slim["coordinates"] = anatomy["coordinates"]
        if pap_name and slim["total"] and slim["total"].get("role"):
            slim["total"]["role"] = pap_name
        nodes.append(slim)
    slim = {
        "format": TREE_FORMAT,
        "id": tree_id,
        "title": tree.get("table", {}).get("title") or label,
        "roots": tree.get("roots") or [],
        "nodes": nodes,
    }
    if dual_hierarchy:
        slim["hierarchy_modes"] = ["pdf", "prexc"]
        slim["default_hierarchy"] = "prexc"
    present = {role for node in nodes for role in (node.get("amounts") or {})}
    present.update(node["total"]["role"] for node in nodes
                   if node.get("total") and node["total"].get("role"))
    slim["columns"] = [role for role in (*BY_OU_ANCHOR_ROLES[::-1], *sorted(
        present - set(BY_OU_ANCHOR_ROLES), key=str)) if role in present]
    validate_tree(slim, source)
    trees_dir = out_dir / "trees"
    trees_dir.mkdir(parents=True, exist_ok=True)
    basename = tree_basename(tree_id, file_prefix)
    target = trees_dir / f"{basename}.json"
    target.write_text(json.dumps(slim, ensure_ascii=False, separators=(",", ":")),
                      encoding="utf-8")
    csv_file = (write_tree_csv(slim, tree_id, basename, out_dir)
                if file_prefix and tree_id in DATA_SPECS else None)
    return {
        "id": tree_id,
        "label": label,
        "title": slim["title"],
        "file": f"trees/{target.name}",
        "csv": csv_file,
        "schema_format": TREE_FORMAT,
        "pages": sorted({node["page"] for node in slim["nodes"]
                         if isinstance(node["page"], int)}),
        "n_nodes": len(slim["nodes"]),
    }


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def main() -> int:
    args = parse_args()
    run_root = PROJECT / "output" / args.run
    if not run_root.is_dir():
        raise SystemExit(f"Run not found: {run_root}")
    doc = args.doc or args.run
    pack_dir = (PROJECT / args.out).expanduser().resolve() / doc
    if pack_root_conflict(pack_dir, run_root):
        raise SystemExit("Refusing to export into the pipeline output tree")

    requested = [item.strip() for item in args.trees.split(",") if item.strip()]
    unknown = [item for item in requested if item not in TREE_STAGES]
    if unknown:
        raise SystemExit(f"Unknown tree ids: {', '.join(unknown)}")

    pack_dir.mkdir(parents=True, exist_ok=True)
    trees = []
    for tree_id in requested:
        stage_name, label = TREE_STAGES[tree_id]
        trees.append(export_tree(tree_id, stage_name, run_root, pack_dir, label,
                                 file_prefix=args.file_prefix))
    prune_stale_tree_files(pack_dir / "trees", trees)

    viewer = read_json(run_root / "viewer.json")
    pages = sorted({page for tree in trees for page in (tree.get("pages") or [])})
    for tree in trees:
        tree_pages = tree.pop("pages") or []
        if tree_pages:
            tree["page_span"] = [tree_pages[0], tree_pages[-1]]
    pdf_name = Path(viewer.get("pdf", "")).name
    pdf_href, pdf_remote, n_pdf_pages = "pdf/document.pdf", None, None
    pdf_linearized = None
    pdf_source = PROJECT / "pdfs" / pdf_name
    if args.pdf == "copy":
        if not pdf_source.is_file():
            raise SystemExit(f"PDF not found: {pdf_source}")
        target = pack_dir / "pdf" / "document.pdf"
        pdf_linearized = copy_pdf_to_pack(
            pdf_source, target, linearize=not args.no_linearize)
        n_pdf_pages = len(viewer.get("pages") or [])
        if not args.no_linearize and not pdf_linearized:
            raise SystemExit(
                f"Linearization produced a PDF without /Linearized: {target}")
    elif args.pdf == "url":
        if not args.pdf_url:
            raise SystemExit("--pdf url requires --pdf-url")
        pdf_href, pdf_remote = None, args.pdf_url
    else:
        pdf_href = None

    pdf_meta: dict[str, Any] = {
        "href": pdf_href, "remote": pdf_remote, "pages": n_pdf_pages,
    }
    if pdf_linearized is not None:
        pdf_meta["linearized"] = pdf_linearized

    manifest = {
        "format": MANIFEST_FORMAT,
        "doc": doc,
        "title": args.title or doc,
        "run": args.run,
        "generated_at": iso_now(),
        "source": {tree_id: f"{STAGE_DIRS[stage]}/tree.json"
                   for tree_id, (stage, _label) in TREE_STAGES.items()
                   if tree_id in requested},
        "pages": pages,
        "trees": trees,
        "pdf": pdf_meta,
    }
    (pack_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    write_index((PROJECT / args.out).expanduser().resolve(), doc, manifest)

    total = sum(path.stat().st_size for path in pack_dir.rglob("*") if path.is_file())
    print(f"Exported {doc} -> {pack_dir.relative_to(PROJECT)}")
    for tree in trees:
        size = (pack_dir / tree["file"]).stat().st_size
        print(f"  {tree['file']}  {tree['n_nodes']} nodes  {human_size(size)}")
        if tree.get("csv"):
            print(f"  {tree['csv']}  {human_size((pack_dir / tree['csv']).stat().st_size)}")
    if pdf_href:
        pdf_size = human_size((pack_dir / "pdf" / "document.pdf").stat().st_size)
        linear_note = " linearized" if pdf_linearized else (
            " (not linearized)" if pdf_linearized is False else "")
        print(f"  pdf/document.pdf  {pdf_size}{linear_note}")
    print(f"  pages: {len(pages)} ({pages[0]}..{pages[-1]})" if pages else "  pages: none")
    print(f"  pack total: {human_size(total)}")
    return 0


def pack_root_conflict(pack_dir: Path, run_root: Path) -> bool:
    return pack_dir == run_root or run_root in pack_dir.parents


def prune_stale_tree_files(trees_dir: Path, trees: list[dict[str, Any]]) -> None:
    """Remove leftover tree artifacts that are not part of this export."""
    if not trees_dir.is_dir():
        return
    keep = set()
    for tree in trees:
        for key in ("file", "csv"):
            relative = tree.get(key)
            if relative:
                keep.add((trees_dir.parent / relative).resolve())
    for path in trees_dir.iterdir():
        if path.is_file() and path.suffix in {".json", ".csv"} and path.resolve() not in keep:
            path.unlink()


def write_index(root: Path, doc: str, manifest: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    index_path = root / "index.json"
    entries = {}
    if index_path.exists():
        try:
            existing = json.loads(index_path.read_text(encoding="utf-8"))
            entries = {entry["doc"]: entry for entry in existing.get("docs", [])}
        except (json.JSONDecodeError, KeyError, TypeError):
            entries = {}
    entries[doc] = {
        "doc": doc,
        "title": manifest["title"],
        "generated_at": manifest["generated_at"],
        "trees": [tree["id"] for tree in manifest["trees"]],
    }
    index = {"format": 1, "docs": [entries[doc] for doc in sorted(entries)]}
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    (root / doc / "index.json").write_text(
        json.dumps({"format": 1, "docs": [entries[doc]]}, ensure_ascii=False,
                   indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
