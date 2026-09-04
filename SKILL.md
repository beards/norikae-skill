---
name: norikae
license: MIT
compatibility: Requires Python 3 and network access to transit.yahoo.co.jp
description: Search Japanese train/transit routes, timetables, fares, and transfers via Yahoo! Transit (乗換案内). Use whenever the user asks how to get between stations or places in Japan by train, subway, Shinkansen, or bus — route planning, departure/arrival times, first/last trains (始発/終電), fares, platform numbers, airport access (Narita/Haneda/KIX) — even when asked casually in Chinese or English, e.g. "東京到新宿怎麼搭", "last train back to Shinjuku", "how do I get from Kyoto to Osaka".
---

# Norikae — Japan train route search

Run the bundled script (stdlib-only Python 3, no dependencies). Paths are
relative to this skill's base directory:

```bash
python3 scripts/norikae.py FROM TO [options]
```

## Station names MUST be Japanese kanji/kana

Convert English and Chinese names to Japanese before calling. Japanese kanji
may differ from Chinese hanzi:

- 涩谷/澀谷 → 渋谷, 横滨/橫濱 → 横浜, 浅草/淺草 → 浅草, 泽 → 沢
- Tokyo → 東京, Shinjuku → 新宿, Narita Airport → 成田空港, Haneda Airport → 羽田空港
- Landmarks work too (e.g. お台場海浜公園), but prefer station names.

If unsure of the exact Japanese name, make your best guess — when Yahoo
resolves it to a different station the output starts with a `※` line showing
what was actually searched plus other candidates; check it matches the user's
intent and re-run with the exact candidate name if not.

## Options

- `--date YYYY-MM-DD` / `--time HH:MM` — default: current date/time **in JST**
- `--when departure|arrival|first|last` — how to interpret the time
  (`arrival` = arrive-by, `first` = 始発, `last` = 終電)
- `--via 駅名` — via station, repeat up to 3 times
- `--ticket ic|cash` (default ic), `--seat free|reserved|green`
- `--sort time|fare|transfer` — earliest arrival / cheapest / fewest transfers
- `--no-shinkansen --no-express --no-air --no-highway-bus --no-local-bus --no-ferry`
- `--stops` — list intermediate stops per leg
- `--json` — structured output; `--url` — print the Yahoo page URL (give this
  to the user if they want to open the result in a browser)

## Examples

```bash
python3 scripts/norikae.py 東京 新宿                          # leave now
python3 scripts/norikae.py 新宿 成田空港 --date 2026-09-05 --time 08:00
python3 scripts/norikae.py 渋谷 吉祥寺 --when last            # 終電
python3 scripts/norikae.py 京都 大阪 --sort fare              # cheapest
python3 scripts/norikae.py 東京 名古屋 --no-shinkansen --via 熱海
```

## Reading the output

- `[早][楽][安]` = fastest / fewest transfers / cheapest of the returned routes.
- Fares: `¥8,360 +自由席¥4,960` means base fare plus express/Shinkansen
  surcharge for that seat class; the route header shows the combined total.
- `(発:3番線)` / `(着:12番線)` are departure/arrival platforms.
- Times are JST. Exit code 2 = no routes found (check the station names).

Present results to the user in their language; keep station and line names in
Japanese (optionally with a translation).
