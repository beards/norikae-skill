# norikae-skill

A Claude Code skill for Japanese train route search (乗換案内), backed by
Yahoo! Transit (transit.yahoo.co.jp).

Inspired by [tysonwu/norikae-mcp](https://github.com/tysonwu/norikae-mcp) (MIT),
adapted to the skill format: fetching and parsing happen in a standalone
script outside the model context, and only a compact text summary enters the
conversation.

The script parses the `__NEXT_DATA__` JSON embedded in the result page into
structured data: per-leg times, line names, platforms, fares with express
surcharges, transfer/walk segments, and station-name disambiguation candidates.

## Usage

```bash
python3 skills/norikae/scripts/norikae.py 東京 新宿
python3 skills/norikae/scripts/norikae.py 渋谷 横浜 --when last
python3 skills/norikae/scripts/norikae.py --help
```

Python 3 stdlib only, no dependencies.

## Install

```bash
gh skill install beards/norikae-skill norikae --agent claude-code
```

`gh skill` supports many other agents — see [`gh skill install --help`](https://cli.github.com/manual/gh_skill_install)
for more details.

## Caveats

- Scrapes the Yahoo! Transit result page; breaks if the page structure changes.
- Station names must be Japanese kanji/kana (渋谷, not 澀谷).
- Default date/time is "now" in JST.
