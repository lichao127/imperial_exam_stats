#!/usr/bin/env python3
"""Generate Mermaid markdown charts from ming_people.db.

First graph: total people count by province.
"""

from __future__ import annotations

import argparse
import math
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


def query_total_count_by_year(db_path: Path) -> Dict[int, int]:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                CAST(ad_year AS INTEGER) AS year_num,
                COUNT(*) AS total_count
            FROM people
            WHERE TRIM(ad_year) != ''
            GROUP BY year_num
            ORDER BY year_num ASC
            """
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    return {int(year_num): int(total_count) for year_num, total_count in rows}


def escape_mermaid_label(label: str) -> str:
    return label.replace('"', "'")


def graph_total_by_province_markdown(
    province_counts: List[Tuple[str, int]],
    include_title: bool = True,
) -> str:
    lines: List[str] = []
    if include_title:
        lines.append("# Graph 1: 明朝各省进士总人数")
        lines.append("")
    lines.append("| 省份 | 人数 | 百分比 |")
    lines.append("|---|---:|---:|")

    total = sum(count for _, count in province_counts)
    if province_counts and total > 0:
        for province, count in province_counts:
            percentage = (count / total) * 100
            lines.append(f"| {province} | {count} | {percentage:.2f}% |")
    else:
        lines.append("| No data | 0 | 0.00% |")

    lines.append("")
    return "\n".join(lines)


def graph_province_yearly_markdown(
    province: str,
    year_pairs: List[Tuple[int, int]],
    totals_by_year: Dict[int, int],
    include_title: bool = True,
    include_percentage_graph: bool = False,
) -> str:
    years = [year for year, _ in year_pairs]
    counts = [count for _, count in year_pairs]
    max_count = max(counts) if counts else 1

    lines: List[str] = []
    if include_title:
        lines.append(f"# Graph: {province} Yearly Count")
        lines.append("")
    lines.append("```mermaid")
    lines.append("xychart-beta")
    lines.append(f'    title "{escape_mermaid_label(province)}: 进士人数按年份"')
    lines.append("    x-axis [" + ", ".join(str(y) for y in years) + "]")
    lines.append(f"    y-axis \"count\" 0 --> {max_count}")
    lines.append("    bar [" + ", ".join(str(c) for c in counts) + "]")
    lines.append("```")
    lines.append("")

    if include_percentage_graph:
        percentages: List[float] = []
        for year, count in year_pairs:
            year_total = totals_by_year.get(year, 0)
            if year_total <= 0:
                percentages.append(0.0)
            else:
                percentages.append((count / year_total) * 100.0)

        max_pct = max(percentages) if percentages else 1.0
        y_max = max(1, math.ceil(max_pct))

        lines.append("```mermaid")
        lines.append("xychart-beta")
        lines.append(f'    title "{escape_mermaid_label(province)}: 占当年总进士百分比"')
        lines.append("    x-axis [" + ", ".join(str(y) for y in years) + "]")
        lines.append(f"    y-axis \"percentage\" 0 --> {y_max}")
        lines.append("    line [" + ", ".join(f"{p:.2f}" for p in percentages) + "]")
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def write_split_graph_files(
    split_dir: Path,
    province_counts: List[Tuple[str, int]],
    yearly_counts_by_province: Dict[str, List[Tuple[int, int]]],
    totals_by_year: Dict[int, int],
) -> int:
    split_dir.mkdir(parents=True, exist_ok=True)

    file_count = 0
    total_graph_md = graph_total_by_province_markdown(province_counts, include_title=True)
    (split_dir / "graph_001_total_by_province.md").write_text(total_graph_md, encoding="utf-8")
    file_count += 1

    for idx, (province, year_pairs) in enumerate(sorted(yearly_counts_by_province.items()), start=2):
        graph_md = graph_province_yearly_markdown(
            province,
            year_pairs,
            totals_by_year=totals_by_year,
            include_title=True,
            include_percentage_graph=True,
        )
        filename = f"graph_{idx:03d}_province_yearly.md"
        # Keep province in filename suffix for readability.
        filename = filename.replace("province", province)
        (split_dir / filename).write_text(graph_md, encoding="utf-8")
        file_count += 1

    return file_count


def render_markdown(
    province_counts: List[Tuple[str, int]],
    yearly_counts_by_province: Dict[str, List[Tuple[int, int]]],
    totals_by_year: Dict[int, int],
) -> str:
    lines: List[str] = []
    lines.append("# 明代进士")
    lines.append("")
    lines.append("## Graph 1: Total Count by Province")
    lines.append("")
    lines.append(graph_total_by_province_markdown(province_counts, include_title=False).strip())
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
        lines.append(
            graph_province_yearly_markdown(
                province,
                year_pairs,
                totals_by_year=totals_by_year,
                include_title=False,
                include_percentage_graph=False,
            ).strip()
        )
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query ming_people.db and generate split markdown graph files."
    )
    parser.add_argument(
        "--db",
        default="scripts/ming_people.db",
        help="Path to SQLite database (default: scripts/ming_people.db)",
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
    totals_by_year = query_total_count_by_year(db_path)

    split_dir = Path(args.split_dir)
    graph_files = write_split_graph_files(
        split_dir,
        province_counts,
        yearly_counts_by_province,
        totals_by_year,
    )

    print(f"Wrote {graph_files} graph markdown files to {split_dir}")


if __name__ == "__main__":
    main()
