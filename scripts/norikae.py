#!/usr/bin/env python3
"""Search Japanese train routes via Yahoo! Transit (transit.yahoo.co.jp).

Fetches the search result page, parses the embedded __NEXT_DATA__ JSON,
and prints a compact plain-text route summary. Stdlib only.

Ported from https://github.com/tysonwu/norikae-mcp (MIT).
"""

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BASE_URL = "https://transit.yahoo.co.jp/search/result"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
JST = timezone(timedelta(hours=9))

# Yahoo URL parameter mappings (see norikae-mcp src/index.ts)
WHEN_MAP = {"departure": "1", "arrival": "4", "first": "3", "last": "2", "any": "5"}
TICKET_MAP = {"ic": "ic", "cash": "normal"}
SEAT_MAP = {"free": "1", "reserved": "2", "green": "3"}
WALK_MAP = {"fast": "1", "sfast": "2", "sslow": "3", "slow": "4"}
SORT_MAP = {"time": "0", "fare": "1", "transfer": "2"}


def build_url(args):
    now = datetime.now(JST)
    if args.date:
        y, m, d = (int(x) for x in args.date.split("-"))
    else:
        y, m, d = now.year, now.month, now.day
    if args.time:
        hh, mm = (int(x) for x in args.time.split(":"))
    else:
        hh, mm = now.hour, now.minute

    params = [
        ("from", args.frm),
        ("to", args.to),
        ("y", str(y)),
        ("m", f"{m:02d}"),
        ("d", f"{d:02d}"),
        ("hh", str(hh)),
        ("m1", str(mm // 10)),
        ("m2", str(mm % 10)),
        ("type", WHEN_MAP[args.when]),
        ("ticket", TICKET_MAP[args.ticket]),
        ("expkind", SEAT_MAP[args.seat]),
        ("ws", WALK_MAP[args.walk]),
        ("s", SORT_MAP[args.sort]),
        ("al", "0" if args.no_air else "1"),
        ("shin", "0" if args.no_shinkansen else "1"),
        ("ex", "0" if args.no_express else "1"),
        ("hb", "0" if args.no_highway_bus else "1"),
        ("lb", "0" if args.no_local_bus else "1"),
        ("sr", "0" if args.no_ferry else "1"),
    ]
    for station in (args.via or [])[:3]:
        params.append(("via", station))
    return BASE_URL + "?" + urllib.parse.urlencode(params)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_next_data(html):
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        re.S,
    )
    if not m:
        return None
    return json.loads(m.group(1))


def _platform(parts):
    s = "".join(x for x in (parts or []) if x)
    return s if s and s != "情報なし" else None


def parse_routes(data, query_from, query_to):
    nav = data["props"]["pageProps"].get("naviSearchParam") or {}
    routes = []
    for feature in nav.get("featureInfoList") or []:
        s = feature["summaryInfo"]
        badges = []
        if s.get("isFast"):
            badges.append("早")
        if s.get("isEasy"):
            badges.append("楽")
        if s.get("isCheap"):
            badges.append("安")
        route = {
            "departure": s.get("departureTime"),
            "arrival": s.get("arrivalTime"),
            "total_time": s.get("totalTime"),
            "fare": s.get("totalPrice"),
            "transfers": s.get("transferCount"),
            "distance": s.get("distance"),
            "badges": badges,
            "legs": [],
        }
        edges = feature.get("edgeInfoList") or []
        for i, e in enumerate(edges):
            times = e.get("timeInfo") or []
            # indexType: 0=origin, 1=transfer point, 2=destination.
            # A transfer point carries [arrival(type2), departure(type1)].
            arr_t = dep_t = None
            if e["indexType"] == 0:
                dep_t = times[0]["time"] if times else None
            elif e["indexType"] == 2:
                arr_t = times[0]["time"] if times else None
            else:
                for t in times:
                    if t["type"] == 2:
                        arr_t = t["time"]
                    elif t["type"] == 1:
                        dep_t = t["time"]
            rp = e.get("ridingPositionInfo") or {}
            prev_rp = (edges[i - 1].get("ridingPositionInfo") or {}) if i else {}
            leg = {
                "station": e.get("stationName"),
                "arr_time": arr_t,
                "dep_time": dep_t,
                # arrival platform belongs to the leg that brought us here
                "arr_platform": _platform(prev_rp.get("arrival")),
                "dep_platform": _platform(rp.get("departure")),
                "rail": None if e["indexType"] == 2 else e.get("railName"),
                "fare": (e.get("priceInfo") or {}).get("price"),
                "fare_group": (e.get("priceInfo") or {}).get("edgeGroup"),
                "exp_fare": (e.get("priceInfo") or {}).get("expPrice"),
                "exp_type": (e.get("priceInfo") or {}).get("expType"),
                "stops": [
                    f"{st['name']} {st.get('departureTime', '')}".strip()
                    for st in e.get("stopStationList") or []
                ],
                "note": e.get("preCautionalComment") or None,
            }
            route["legs"].append(leg)
        routes.append(route)

    def resolved(key, query_val):
        # data["query"] is rewritten to the resolved name, so compare the
        # first candidate against what the user actually typed
        lst = (nav.get("otherQueryInfo") or {}).get(key) or []
        if not lst:
            return None
        first = lst[0]["name"]
        if first == query_val:
            return None
        cands = [c["name"] for c in lst[1:6] if c.get("name")]
        return {"resolved": first, "candidates": cands}

    return {
        "routes": routes,
        "from_note": resolved("fromList", query_from),
        "to_note": resolved("toList", query_to),
    }


def format_text(result, args, show_stops=False):
    out = []
    when_label = {
        "departure": "出発",
        "arrival": "到着",
        "first": "始発",
        "last": "終電",
        "any": "時刻指定なし",
    }[args.when]
    date = args.date or datetime.now(JST).strftime("%Y-%m-%d")
    time = args.time or datetime.now(JST).strftime("%H:%M")
    via = f" 経由:{','.join(args.via)}" if args.via else ""
    out.append(f"{args.frm} → {args.to}{via}  {date} {time} {when_label}"
               f"  [{'IC' if args.ticket == 'ic' else 'きっぷ'}運賃]")

    for key, label in (("from_note", "出発駅"), ("to_note", "到着駅")):
        note = result.get(key)
        if note:
            cands = "、".join(note["candidates"])
            out.append(f"※ {label}は「{note['resolved']}」で検索"
                       + (f"（他の候補: {cands}）" if cands else ""))

    if not result["routes"]:
        out.append("ルートが見つかりませんでした。駅名（日本語の漢字・かな）や日時を確認してください。")
        return "\n".join(out)

    for n, r in enumerate(result["routes"], 1):
        badges = "".join(f"[{b}]" for b in r["badges"])
        out.append("")
        out.append(f"ルート{n} {badges} {r['departure']}→{r['arrival']}"
                   f" ({r['total_time']}) ¥{r['fare']} 乗換{r['transfers']}回 {r['distance']}")
        seen_fare_groups = set()
        for leg in r["legs"]:
            t = []
            if leg["arr_time"]:
                t.append(f"{leg['arr_time']}着")
            if leg["dep_time"]:
                t.append(f"{leg['dep_time']}発")
            plat = []
            if leg["arr_platform"]:
                plat.append(f"着:{leg['arr_platform']}")
            if leg["dep_platform"] and leg["rail"] and leg["rail"] != "徒歩":
                plat.append(f"発:{leg['dep_platform']}")
            plat_s = f" ({' '.join(plat)})" if plat else ""
            out.append(f"  {' '.join(t) or '--:--'} {leg['station']}{plat_s}")
            if leg["note"]:
                out.append(f"    ※ {leg['note']}")
            if leg["rail"]:
                # legs in the same edgeGroup share one fare; print it once
                fare = ""
                if (leg["fare"] not in (None, "0")
                        and leg["fare_group"] not in seen_fare_groups):
                    seen_fare_groups.add(leg["fare_group"])
                    fare = f"  ¥{leg['fare']}"
                    if leg["exp_fare"] not in (None, "0"):
                        fare += f" +{leg['exp_type']}¥{leg['exp_fare']}"
                out.append(f"  | {leg['rail']}{fare}")
                if show_stops and leg["stops"]:
                    out.append(f"  |   停車駅: {' / '.join(leg['stops'])}")
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser(description="Yahoo! Transit route search (Japan)")
    p.add_argument("frm", metavar="FROM", help="departure station (Japanese kanji/kana)")
    p.add_argument("to", metavar="TO", help="arrival station (Japanese kanji/kana)")
    p.add_argument("--via", action="append", help="via station, repeatable up to 3")
    p.add_argument("--date", help="YYYY-MM-DD (default: today JST)")
    p.add_argument("--time", help="HH:MM (default: now JST)")
    p.add_argument("--when", choices=list(WHEN_MAP), default="departure",
                   help="interpret --time as: departure/arrival, or first/last train")
    p.add_argument("--ticket", choices=list(TICKET_MAP), default="ic")
    p.add_argument("--seat", choices=list(SEAT_MAP), default="free")
    p.add_argument("--walk", choices=list(WALK_MAP), default="sslow",
                   help="walking speed: fast/sfast/sslow/slow")
    p.add_argument("--sort", choices=list(SORT_MAP), default="time",
                   help="time=earliest arrival, fare=cheapest, transfer=fewest")
    p.add_argument("--no-air", action="store_true")
    p.add_argument("--no-shinkansen", action="store_true")
    p.add_argument("--no-express", action="store_true")
    p.add_argument("--no-highway-bus", action="store_true")
    p.add_argument("--no-local-bus", action="store_true")
    p.add_argument("--no-ferry", action="store_true")
    p.add_argument("--stops", action="store_true", help="show intermediate stops")
    p.add_argument("--json", action="store_true", help="output parsed routes as JSON")
    p.add_argument("--url", action="store_true", help="print the Yahoo URL and exit")
    args = p.parse_args()

    url = build_url(args)
    if args.url:
        print(url)
        return 0

    try:
        html = fetch(url)
    except Exception as e:
        print(f"error: fetch failed: {e}", file=sys.stderr)
        return 1

    data = extract_next_data(html)
    if data is None:
        print("error: could not find __NEXT_DATA__ in page "
              "(Yahoo! Transit may have changed its page structure)", file=sys.stderr)
        return 1

    try:
        result = parse_routes(data, args.frm, args.to)
    except (KeyError, TypeError) as e:
        print(f"error: unexpected page data shape: {e!r}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print(format_text(result, args, show_stops=args.stops))
    return 0 if result["routes"] else 2


if __name__ == "__main__":
    sys.exit(main())
