#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV_FILE = HERE / ".env"
PRIVATE = HERE / "private"
SYMBOLS = PRIVATE / "symbols.json"
PAGE = PRIVATE / "holdings.html"
PINE = PRIVATE / "avg_price_lines.pine"

T212_POSITIONS = "https://live.trading212.com/api/v0/equity/positions"
TV_SEARCH = "https://symbol-search.tradingview.com/symbol_search/v3/?"
TV_LISTS = "https://www.tradingview.com/api/v1/symbols_list/custom/"
TV_LIST_NAME = "Trading 212"
PINE_SAVE = "https://pine-facade.tradingview.com/pine-facade/save/new?"
PINE_NAME = "T212 avg buy price"

SAFE_SYMBOL = re.compile(r"[A-Z0-9_]+:[\w.&/!-]+")
HINTS = {401: "Trading 212 rejected the key: check T212_API_KEY and T212_API_SECRET in .env (must be a LIVE key).",
         403: "The Trading 212 key is missing the 'Portfolio' permission.",
         429: "Rate limited, try again in a few seconds."}

PINE_TEMPLATE = """//@version=6
indicator("{name}", overlay = true)
float avg = switch syminfo.prefix + ":" + syminfo.ticker
{cases}    => float(na)
plot(avg, "Avg buy price", color.yellow, 2, trackprice = true)
var table box = table.new(position.top_right, 1, 1)
if barstate.islast and avg > 0
    pct = (close / avg - 1) * 100
    table.cell(box, 0, 0, "Avg " + str.tostring(avg, format.mintick) + "   " + (pct >= 0 ? "+" : "") +
         str.tostring(pct, "0.0") + "%", text_color = color.black, bgcolor = color.yellow)
"""

PAGE_TEMPLATE = """<!doctype html>
<meta charset="utf-8"><meta name="color-scheme" content="light dark"><meta http-equiv="refresh" content="300">
<title>Trading 212 holdings</title>
<style>body {{ font: 14px system-ui; margin: 2em }} td, th {{ padding: 4px 12px; text-align: right }}
td:nth-child(-n+2), th:nth-child(-n+2) {{ text-align: left }} .up {{ color: #2da44e }} .down {{ color: #e5534b }}</style>
<p>Updated {updated}. Click a symbol to open its chart on TradingView.</p>
<table><tr><th>Symbol<th>Name<th>Avg price<th>Price<th>vs avg
{rows}</table>
"""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


open_url = urllib.request.build_opener(NoRedirect).open


def get_json(url, headers, data=None):
    with open_url(urllib.request.Request(url, data, headers), timeout=20) as r:
        return json.load(r)


def read_env():
    env = {}
    for line in ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []:
        name, _, value = line.partition("=")
        value = value.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        env[name.strip()] = value
    return env


def auth_header(env):
    key, secret = env.get("T212_API_KEY"), env.get("T212_API_SECRET")
    if not (key and secret):
        sys.exit(
            f"Paste your Trading 212 API key and secret into {ENV_FILE} (see README).")
    return "Basic " + b64encode(f"{key}:{secret}".encode()).decode()


def tv_headers(cookie):
    headers = {"Cookie": cookie, "Origin": "https://www.tradingview.com", "Referer": "https://www.tradingview.com/",
               "Content-Type": "application/json"}
    if csrf := re.search(r"(?:^|;\s*)csrftoken=([^;]+)", cookie):
        headers["X-CSRFToken"] = csrf[1]
    return headers


def pick(hits, isin, currency):
    hits = [h for h in hits if h.get("isin") == isin]
    same = ([h for h in hits if h.get("currency_code") == currency]
            or [h for h in hits if currency == "GBP" and h.get("currency_code") == "GBX"])
    best = next((h for h in same if h.get("is_primary_listing")),
                same[0] if same else None)
    return f"{best.get('prefix') or best['exchange']}:{best['symbol']}" if best else None


def resolve(isin, currency):
    query = urllib.parse.urlencode(
        {"text": isin, "hl": 0, "lang": "en", "domain": "production"})
    try:
        return pick(get_json(TV_SEARCH + query, {"Origin": "https://www.tradingview.com"})["symbols"], isin, currency)
    except (OSError, ValueError, KeyError) as e:
        print(f"  TradingView lookup for {isin} failed: {e}")


def render(holdings):
    cases = table = ""
    for tv, (_, name, avg, price, cur) in sorted(holdings.items()):
        cases += f'    "{tv}" => {avg:.8f}\n'
        change = f"{price / avg - 1:+.1%}" if avg else ""
        chart = "https://www.tradingview.com/chart/?symbol=" + \
            urllib.parse.quote(tv, safe="")
        cur = escape(cur)
        table += (f'<tr><td><a href="{chart}" target="tradingview">{escape(tv)}</a><td>{escape(name)}'
                  f'<td>{avg:g} {cur}<td>{price:g} {cur}<td class="{"up" if price >= avg else "down"}">{change}\n')
    return (PAGE_TEMPLATE.format(rows=table, updated=time.strftime("%Y-%m-%d %H:%M")),
            PINE_TEMPLATE.format(name=PINE_NAME, cases=cases))


def plan(current, wanted, keep):
    remove = [s for s in current if s not in wanted and s not in keep and s.partition(":")[
        2] not in keep]
    return remove, [s for s in wanted if s not in current]


def sync_watchlist(headers, wanted, keep):
    lists = [w for w in get_json(TV_LISTS, headers) if w["id"]]
    wl = lists[0] if len(lists) == 1 else next(
        (w for w in lists if w["name"] == TV_LIST_NAME), None)
    if not wl:
        print("! TradingView watchlist not synced: " + (f'rename the watchlist to sync to "{TV_LIST_NAME}".' if lists
              else "not logged in. Copy a fresh TV_COOKIE into .env."))
        return
    remove, add = plan(wl["symbols"], wanted, keep)
    url = f"{TV_LISTS}{wl['id']}/"
    if remove:
        get_json(url + "remove/", headers, json.dumps(remove).encode())
        print("  Watchlist: removed", ", ".join(remove))
    added = []
    for s in add:
        try:
            get_json(url + "append/", headers, json.dumps([s]).encode())
        except urllib.error.HTTPError as e:
            print(f"! TradingView refused {s} ({e.code}: {e.read()[:150].decode(errors='replace')}). "
                  f"Not in the watchlist: {', '.join(add[len(added):])}")
            break
        added.append(s)
    if added:
        print("  Watchlist: added", ", ".join(added))


def save_pine(cookie, source):
    boundary = "t212-sync-boundary-7f3a9c"
    body = f'--{boundary}\r\nContent-Disposition: form-data; name="source"\r\n\r\n{source}\r\n--{boundary}--\r\n'
    headers = tv_headers(cookie) | {
        "Content-Type": f"multipart/form-data; boundary={boundary}"}
    url = PINE_SAVE + \
        urllib.parse.urlencode({"name": PINE_NAME, "allow_overwrite": "true"})
    try:
        result = get_json(url, headers, body.encode())
    except (OSError, ValueError) as e:
        print(
            f"! Couldn't save the indicator to TradingView: {e}. A 401 means TV_COOKIE in .env has expired.")
        return False
    if not result.get("success"):
        print(
            f"! TradingView rejected the indicator: {result.get('reason2') or result.get('reason') or result}")
    return bool(result.get("success"))


def write(path, text):
    if path.exists() and path.read_text() == text:
        return False
    path.write_text(text)
    return True


def sync(auth, env):
    positions = get_json(T212_POSITIONS, {"Authorization": auth})
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    symbols = json.loads(SYMBOLS.read_text()) if SYMBOLS.exists() else {}
    holdings = {}
    for p in sorted(positions, key=lambda p: p["walletImpact"]["currentValue"], reverse=True):
        i = p["instrument"]
        tv = symbols.get(i["ticker"]) or resolve(i["isin"], i["currency"])
        if not (tv and SAFE_SYMBOL.fullmatch(tv)):
            print(f'! No valid TradingView symbol for {i["ticker"]} ({i["name"]}, {i["isin"]}). '
                  f'Set it in {SYMBOLS}, e.g. "{i["ticker"]}": "LSE:VUSA"')
            continue
        symbols[i["ticker"]] = tv
        holdings[tv] = (i["ticker"], i["name"],
                        p["averagePricePaid"], p["currentPrice"], i["currency"])
    write(SYMBOLS, json.dumps(symbols, indent=2, sort_keys=True) + "\n")
    if not holdings:
        print("No positions to sync.")
        return False
    page, pine = render(holdings)
    write(PAGE, page)
    cookie = env.get("TV_COOKIE")
    if cookie:
        keep = {s.strip()
                for s in env.get("TV_KEEP", "").split(",") if s.strip()}
        try:
            sync_watchlist(tv_headers(cookie), list(holdings), keep)
        except (OSError, ValueError, KeyError) as e:
            print(
                f"! TradingView watchlist not synced: {e}. A 403 usually means TV_COOKIE in .env has expired.")
    if not write(PINE, pine):
        print(time.strftime("%H:%M"), "holdings unchanged")
        return False
    for tv, (ticker, _, avg, _, currency) in sorted(holdings.items()):
        print(f"  {ticker:<14} -> {tv:<22} avg {avg:g} {currency}")
    if cookie and save_pine(cookie, pine):
        print(
            f'Saved the "{PINE_NAME}" indicator to your TradingView account. Your holdings: {PAGE}')
        return False
    print(
        f"Updated {PINE}: paste it into TradingView's Pine Editor. Your holdings: {PAGE}")
    return True


def main():
    ap = argparse.ArgumentParser(
        description="Sync your Trading 212 holdings into TradingView.")
    ap.add_argument("--watch", type=float, nargs="?", const=5, metavar="MIN",
                    help="keep running and re-check every MIN minutes (default 5)")
    args = ap.parse_args()
    env = read_env()
    auth = auth_header(env)
    while True:
        try:
            if sync(auth, env) and args.watch:
                subprocess.run(["/usr/bin/osascript", "-e", 'display notification "Paste the new Pine script '
                                'into TradingView." with title "Trading 212 holdings changed"'])
        except OSError as e:
            msg = f"Sync failed: {e}. {HINTS.get(getattr(e, 'code', None), '')}"
            if not args.watch:
                sys.exit(msg)
            print(msg)
        if not args.watch:
            return
        time.sleep(args.watch * 60)


if __name__ == "__main__":
    main()
