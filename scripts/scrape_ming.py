#!/usr/bin/env python3
"""Iterate templates in a category, then print intro line for each linked person page.

Target use case:
- Category: Category:明朝进士模板 on Chinese Wikipedia.
- For each template page in that category, collect linked main-namespace pages.
- Treat those links as person pages and print each page's intro line.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import ssl
import time
import urllib.parse
import urllib.error
import urllib.request
from typing import Dict, Iterable, List, Optional, Set, Tuple

API_URL = "https://zh.wikipedia.org/w/api.php"
DEFAULT_CATEGORY = "Category:明朝进士模板"
USER_AGENT = "imperial-exam-script/1.0 (https://github.com; contact: local-script)"
SSL_CONTEXT: Optional[ssl.SSLContext] = None

ERA_START_YEAR: Dict[str, int] = {
    "洪武": 1368,
    "建文": 1399,
    "永乐": 1403,
    "永樂": 1403,
    "洪熙": 1425,
    "宣德": 1426,
    "正统": 1436,
    "正統": 1436,
    "景泰": 1450,
    "天顺": 1457,
    "天順": 1457,
    "成化": 1465,
    "弘治": 1488,
    "正德": 1506,
    "嘉靖": 1522,
    "隆庆": 1567,
    "隆慶": 1567,
    "万历": 1573,
    "萬曆": 1573,
    "泰昌": 1620,
    "天启": 1621,
    "天啟": 1621,
    "崇祯": 1628,
    "崇禎": 1628,
}

YEAR_RE = re.compile(
    r"(洪武|建文|永乐|永樂|洪熙|宣德|正统|正統|景泰|天顺|天順|成化|弘治|正德|嘉靖|隆庆|隆慶|万历|萬曆|泰昌|天启|天啟|崇祯|崇禎)([元〇零一二三四五六七八九十百廿卅]+)年"
)

PROVINCE_RE = re.compile(
    r"(南直隸|北直隸|直隸|山東|山西|河南|陝西|陕西|浙江|江西|福建|湖廣|湖广|四川|廣東|广东|廣西|广西|雲南|云南|貴州|贵州)"
)

PROVINCE_NORMALIZE: Dict[str, str] = {
    "南直隸": "南直隶",
    "北直隸": "北直隶",
    "直隸": "直隶",
    "山東": "山东",
    "山东": "山东",
    "山西": "山西",
    "河南": "河南",
    "陝西": "陕西",
    "陕西": "陕西",
    "浙江": "浙江",
    "江西": "江西",
    "福建": "福建",
    "湖廣": "湖广",
    "湖广": "湖广",
    "四川": "四川",
    "廣東": "广东",
    "广东": "广东",
    "廣西": "广西",
    "广西": "广西",
    "雲南": "云南",
    "云南": "云南",
    "貴州": "贵州",
    "贵州": "贵州",
}

S2T_CHAR_MAP: Dict[str, str] = {
    "縣": "县",
    "隸": "隶",
    "東": "东",
    "廣": "广",
    "雲": "云",
    "貴": "贵",
    "陝": "陕",
    "號": "号",
    "衛": "卫",
    "寧": "宁",
    "蘇": "苏",
    "臺": "台",
    "壽": "寿",
    "溫": "温",
    "興": "兴",
    "長": "长",
    "豐": "丰",
    "樂": "乐",
    "萬": "万",
    "啟": "启",
    "禎": "祯",
    "統": "统",
}


def api_get(params: Dict[str, str], max_retries: int = 3, timeout: int = 20) -> Dict:
    """Call MediaWiki API and return decoded JSON."""
    query = urllib.parse.urlencode(params)
    url = f"{API_URL}?{query}"
    headers = {"User-Agent": USER_AGENT}

    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CONTEXT) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            if (
                isinstance(exc.reason, ssl.SSLCertVerificationError)
                and SSL_CONTEXT is None
            ):
                raise RuntimeError(
                    "SSL certificate verification failed. "
                    "Try --insecure, or fix local CA certificates."
                ) from exc

            if attempt == max_retries:
                raise
            time.sleep(1.0 * attempt)
        except Exception:
            if attempt == max_retries:
                raise
            time.sleep(1.0 * attempt)

    raise RuntimeError("Unreachable")


def get_templates_in_category(category_title: str) -> List[str]:
    """Fetch all template pages in a category (namespace 10)."""
    templates: List[str] = []
    cmcontinue: Optional[str] = None

    while True:
        params = {
            "action": "query",
            "format": "json",
            "list": "categorymembers",
            "cmtitle": category_title,
            "cmnamespace": "10",
            "cmlimit": "max",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue

        data = api_get(params)
        members = data.get("query", {}).get("categorymembers", [])
        templates.extend(m.get("title", "") for m in members if m.get("title"))

        cont = data.get("continue", {})
        cmcontinue = cont.get("cmcontinue")
        if not cmcontinue:
            break

    return templates


def get_template_links(template_title: str) -> List[str]:
    """Get all main-namespace links from a template page via parse API."""
    links: List[str] = []
    plcontinue: Optional[str] = None

    while True:
        params = {
            "action": "parse",
            "format": "json",
            "page": template_title,
            "prop": "links",
        }
        if plcontinue:
            params["plcontinue"] = plcontinue

        data = api_get(params)
        parse_obj = data.get("parse", {})

        for link in parse_obj.get("links", []):
            # ns=0 means main namespace (article pages, often person pages here).
            # Existing pages include the "exists" key (often with empty-string value).
            if link.get("ns") == 0 and "exists" in link:
                title = link.get("*")
                if title:
                    links.append(title)

        cont = data.get("continue", {})
        plcontinue = cont.get("plcontinue")
        if not plcontinue:
            break

    # Preserve order while deduplicating.
    seen: Set[str] = set()
    ordered_unique: List[str] = []
    for t in links:
        if t not in seen:
            seen.add(t)
            ordered_unique.append(t)
    return ordered_unique


def get_intro_line(page_title: str) -> str:
    """Return first non-empty line from page intro text."""
    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts",
        "exintro": "1",
        "explaintext": "1",
        "redirects": "1",
        "titles": page_title,
    }
    data = api_get(params)
    pages = data.get("query", {}).get("pages", {})

    for _, page in pages.items():
        extract = page.get("extract", "") or ""
        for line in extract.splitlines():
            line = line.strip()
            if line:
                return line

    return ""


def chinese_numeral_to_int(text: str) -> Optional[int]:
    if not text:
        return None
    if text == "元":
        return 1

    normalized = text.replace("廿", "二十").replace("卅", "三十").replace("〇", "零")
    digits = {
        "零": 0,
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    units = {"十": 10, "百": 100}

    total = 0
    current = 0
    for ch in normalized:
        if ch in digits:
            current = digits[ch]
        elif ch in units:
            unit = units[ch]
            if current == 0:
                current = 1
            total += current * unit
            current = 0
        else:
            return None

    return total + current


def parse_template_year(template_title: str) -> Tuple[str, Optional[int]]:
    match = YEAR_RE.search(template_title)
    if not match:
        return "", None

    era, regnal_cn = match.group(1), match.group(2)
    regnal_year = chinese_numeral_to_int(regnal_cn)
    if regnal_year is None:
        return f"{era}{regnal_cn}年", None

    start = ERA_START_YEAR.get(era)
    ad_year = None if start is None else start + regnal_year - 1
    return f"{era}{regnal_cn}年", ad_year


def extract_courtesy_names(intro: str) -> List[str]:
    names: List[str] = []
    for pattern in (r"[號号]\s*([^，。；]+)", r"[别別]号\s*([^，。；]+)"):
        match = re.search(pattern, intro)
        if not match:
            continue
        raw = re.sub(r"\s+", "", match.group(1))
        for part in re.split(r"[、/,，]", raw):
            part = part.strip()
            if part and part not in names:
                names.append(part)
    return names


def extract_hometown(intro: str) -> Tuple[str, str]:
    prefix = intro.split("人", 1)[0]

    province_match = PROVINCE_RE.search(prefix)
    province = province_match.group(1) if province_match else ""

    # Use the location phrase immediately before "人" to avoid matching earlier text.
    hometown_phrase = ""
    matches = re.findall(r"，([^，。；]{1,40})人", intro)
    if matches:
        hometown_phrase = matches[-1]
    else:
        hometown_phrase = prefix[-40:]

    county = ""
    county_candidates = re.findall(r"([\u4e00-\u9fff]{1,8}(?:縣|县))", hometown_phrase)
    if county_candidates:
        county = county_candidates[-1]
    else:
        state_candidates = re.findall(r"([\u4e00-\u9fff]{1,8}州)", hometown_phrase)
        for candidate in reversed(state_candidates):
            if candidate not in {"貴州", "贵州", "廣州", "广州", "湖州", "泉州", "蘇州", "苏州"}:
                county = candidate
                break

    if province and county.startswith(province):
        county = county[len(province) :]

    return province, county


def clean_person_name(title: str) -> str:
    name = title.split("(", 1)[0].split("（", 1)[0]
    return re.sub(r"\s+", "", name).strip()


def to_simplified(text: str) -> str:
    if not text:
        return ""
    return "".join(S2T_CHAR_MAP.get(ch, ch) for ch in text)


def normalize_province(province: str) -> str:
    if not province:
        return ""
    if province in PROVINCE_NORMALIZE:
        return PROVINCE_NORMALIZE[province]
    return to_simplified(province)


def iter_template_people_data(
    category_title: str,
    delay_sec: float = 0.1,
) -> Iterable[Tuple[str, str, Optional[int], str, List[str], str, str, str]]:
    templates = get_templates_in_category(category_title)

    for template in templates:
        imperial_year, ad_year = parse_template_year(template)
        people = get_template_links(template)
        for person in people:
            intro = get_intro_line(person)
            name = clean_person_name(person)
            courtesy_names = extract_courtesy_names(intro)
            province, county = extract_hometown(intro)
            yield template, imperial_year, ad_year, name, courtesy_names, province, county, intro
            if delay_sec > 0:
                time.sleep(delay_sec)


def main() -> None:
    global SSL_CONTEXT

    parser = argparse.ArgumentParser(
        description=(
            "Iterate templates in a category and print imperial/AD year + person fields "
            "from Chinese Wikipedia."
        )
    )
    parser.add_argument(
        "--category",
        default=DEFAULT_CATEGORY,
        help="Category title, e.g. Category:明朝进士模板",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.1,
        help="Delay in seconds between person intro requests (default: 0.1)",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate verification (only use if your local cert chain is broken).",
    )
    parser.add_argument(
        "--output",
        default="ming_people.db",
        help="SQLite database output path (default: ming_people.db)",
    )
    args = parser.parse_args()

    if args.insecure:
        SSL_CONTEXT = ssl._create_unverified_context()

    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    conn = sqlite3.connect(args.output)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS people (
            template TEXT,
            imperial_year TEXT,
            ad_year TEXT,
            name TEXT,
            courtesy_name TEXT,
            province TEXT,
            county TEXT
        )
    """)
    conn.commit()

    record_count = 0
    try:
        for template, imperial_year, ad_year, name, courtesy_names, province, county, intro in iter_template_people_data(
            args.category,
            args.delay,
        ):
            courtesy = "、".join(courtesy_names) if courtesy_names else ""
            ad_text = str(ad_year) if ad_year is not None else ""
            province_s = normalize_province(province)
            county_s = to_simplified(county)

            row = (template, imperial_year, ad_text, name, courtesy, province_s, county_s)

            # Check if record already exists in database
            cursor.execute(
                "SELECT 1 FROM people WHERE template = ? AND imperial_year = ? AND ad_year = ? AND name = ? AND courtesy_name = ? AND province = ? AND county = ?",
                row
            )
            if cursor.fetchone():
                continue

            # Insert new record
            cursor.execute(
                "INSERT INTO people (template, imperial_year, ad_year, name, courtesy_name, province, county) VALUES (?, ?, ?, ?, ?, ?, ?)",
                row
            )
            conn.commit()
            record_count += 1

            print(
                f"[{template}] imperial={imperial_year} ad={ad_text} | "
                f"name={name} | courtesy_name={courtesy} | province={province_s} | county={county_s}"
            )
    except BrokenPipeError:
        # Allow piping to tools like `head` without noisy traceback.
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), 1)
        except OSError:
            pass
    finally:
        conn.close()

    print(f"\nSaved {record_count} records to {args.output}")


if __name__ == "__main__":
    main()
