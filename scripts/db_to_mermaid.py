#!/usr/bin/env python3
"""Generate Mermaid markdown charts from ming_people.db.

First graph: total people count by province.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple


def query_count_by_province(db_path: Path) -> List[Tuple[str, int]]:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                CASE
                    WHEN province IS NULL OR TRIM(province) = '' THEN '未知'
                    ELSE province
                END AS province_name,
                COUNT(*) AS total_count
            FROM people
            GROUP BY province_name
            ORDER BY total_count DESC, province_name ASC
            """
        )
        rows = cur.fetchall()
        return [(str(name), int(count)) for name, count in rows]
    finally:
        conn.close()


def query_yearly_count_by_province(db_path: Path) -> Dict[str, List[Tuple[int, int]]]:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                CASE
                    WHEN province IS NULL OR TRIM(province) = '' THEN '未知'
                    ELSE province
                END AS province_name,
                CAST(ad_year AS INTEGER) AS year_num,
                COUNT(*) AS total_count
            FROM people
            WHERE TRIM(ad_year) != ''
            GROUP BY province_name, year_num
            ORDER BY province_name ASC, year_num ASC
            """
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    data: Dict[str, List[Tuple[int, int]]] = {}
    for province, year_num, total_count in rows:
        province_name = str(province)
        data.setdefault(province_name, []).append((int(year_num), int(total_count)))
    return data


def escape_mermaid_label(label: str) -> str:
    return label.replace('"', "'")


def graph_total_by_province_markdown(province_counts: List[Tuple[str, int]]) -> str:
    lines: List[str] = []
    lines.append("# Graph 1: Total Count by Province")
    lines.append("")
    lines.append("```mermaid")
    lines.append("pie title 明代进士省份分布")

    if province_counts:
        for province, count in province_counts:
            lines.append(f'    "{escape_mermaid_label(province)}" : {count}')
    else:
        lines.append('    "No data" : 1')

    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def graph_province_yearly_markdown(province: str, year_pairs: List[Tuple[int, int]]) -> str:
    years = [year for year, _ in year_pairs]
    counts = [count for _, count in year_pairs]
    max_count = max(counts) if counts else 1

    lines: List[str] = []
    lines.append(f"# Graph: {province} Yearly Count")
    lines.append("")
    lines.append("```mermaid")
    lines.append("xychart-beta")
    lines.append(f'    title "{escape_mermaid_label(province)}: 人数按年份"')
    lines.append("    x-axis [" + ", ".join(str(y) for y in years) + "]")
    lines.append(f"    y-axis \"count\" 0 --> {max_count}")
    lines.append("    bar [" + ", ".join(str(c) for c in counts) + "]")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def write_split_graph_files(
    split_dir: Path,
    province_counts: List[Tuple[str, int]],
    yearly_counts_by_province: Dict[str, List[Tuple[int, int]]],
) -> int:
    split_dir.mkdir(parents=True, exist_ok=True)

    file_count = 0
    total_graph_md = graph_total_by_province_markdown(province_counts)
    (split_dir / "graph_001_total_by_province.md").write_text(total_graph_md, encoding="utf-8")
    file_count += 1

    for idx, (province, year_pairs) in enumerate(sorted(yearly_counts_by_province.items()), start=2):
        graph_md = graph_province_yearly_markdown(province, year_pairs)
        filename = f"graph_{idx:03d}_province_yearly.md"
        # Keep province in filename suffix for readability.
        filename = filename.replace("province", province)
        (split_dir / filename).write_text(graph_md, encoding="utf-8")
        file_count += 1

    return file_count


def render_markdown(
    province_counts: List[Tuple[str, int]],
    yearly_counts_by_province: Dict[str, List[Tuple[int, int]]],
) -> str:
    lines: List[str] = []
    lines.append("# 明代进士")
    lines.append("")
    lines.append("## Graph 1: Total Count by Province")
    lines.append("")
    lines.append(graph_total_by_province_markdown(province_counts).strip())
    lines.append("")

    lines.append("## Graph 2: Yearly Count per Province")
    lines.append("")

    if not yearly_counts_by_province:
        lines.append("No yearly AD data available.")
        lines.append("")
        return "\n".join(lines)

    for province, year_pairs in sorted(yearly_counts_by_province.items()):
        lines.append(f"### {province}")
        lines.append("")
        lines.append(graph_province_yearly_markdown(province, year_pairs).strip())
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query ming_people.db and generate Mermaid markdown report."
    )
    parser.add_argument(
        "--db",
        default="scripts/ming_people.db",
        help="Path to SQLite database (default: scripts/ming_people.db)",
    )
    parser.add_argument(
        "--output",
        default="ming.md",
        help="Output markdown path (default: ming.md)",
    )
    parser.add_argument(
        "--split-dir",
        default="ming",
        help="Directory for one-graph-per-markdown output (default: ming)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    province_counts = query_count_by_province(db_path)
    yearly_counts_by_province = query_yearly_count_by_province(db_path)
    markdown = render_markdown(province_counts, yearly_counts_by_province)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    split_dir = Path(args.split_dir)
    graph_files = write_split_graph_files(split_dir, province_counts, yearly_counts_by_province)

    print(f"Wrote Mermaid report to {output_path}")
    print(f"Wrote {graph_files} graph markdown files to {split_dir}")


if __name__ == "__main__":
    main()
