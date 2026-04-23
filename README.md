# Imperial Exam Scraper

从中文维基扒一些科举数据

## Requirements

- Python 3.9+
- Network access to `https://zh.wikipedia.org`

## Run

From the repository root:

```bash
python3 scripts/scrape_ming.py --delay 0.1 --output scripts/ming_people.db
```

If your local Python has TLS certificate issues, use:

```bash
python3 scripts/scrape_ming.py --delay 0.1 --insecure --output scripts/ming_people.db
```

## CLI Options

- `--category` category title, default: `Category:明朝进士模板`
- `--delay` seconds between person requests, default: `0.1`
- `--insecure` disable TLS cert verification (use only if needed)
- `--output` SQLite DB path, default: `scripts/ming_people.db`

## SQLite Schema

Table: `people`

- `template` TEXT
- `imperial_year` TEXT
- `ad_year` TEXT
- `name` TEXT
- `courtesy_name` TEXT
- `province` TEXT
- `county` TEXT

## Quick Queries

Count all rows:

```bash
sqlite3 scripts/ming_people.db "SELECT COUNT(*) FROM people;"
```

Count rows for AD year 1397 ([洪武三十年南北榜案](https://zh.wikipedia.org/wiki/Template:%E6%B4%AA%E6%AD%A6%E4%B8%89%E5%8D%81%E5%B9%B4%E4%B8%81%E4%B8%91%E7%A7%91%E6%AE%BF%E8%A9%A6%E9%87%91%E6%A6%9C)):

```bash
sqlite3 scripts/ming_people.db "SELECT COUNT(*) FROM people WHERE ad_year = '1397';"
```

Show first 10 rows:

```bash
sqlite3 scripts/ming_people.db ".mode column" ".headers on" "SELECT * FROM people LIMIT 10;"
```

Check duplicate exact rows:

```bash
sqlite3 scripts/ming_people.db "
SELECT template, imperial_year, ad_year, name, courtesy_name, province, county, COUNT(*) c
FROM people
GROUP BY template, imperial_year, ad_year, name, courtesy_name, province, county
HAVING c > 1;
"
```

## Limitations

- 如果一个人没有维基词条，或者词条有多于一个相关页面，省份为未知
