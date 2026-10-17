# Trading 212 → TradingView sync

Keeps TradingView in step with your Trading 212 portfolio:

- **Watchlist.** Your TradingView watchlist contains exactly the stocks and ETFs you hold, biggest position first. Anything you no longer hold is removed, except symbols you choose to keep.
- **Average price line.** Each holding's chart shows a yellow line at your average buy price. A yellow box in the top-right corner shows the average price and your gain or loss.
- **Holdings page.** A local web page lists every holding with its average price, current price and % change, and links to its TradingView chart.

It runs on your own computer. Nothing is hosted anywhere.

---

## Requirements

- macOS. Linux works too, but you won't get the `--watch` notifications.
- Python 3.9 or newer. Check with `python3 --version`.
- A Trading 212 **Invest** or **Stocks ISA** account. The Trading 212 API doesn't support CFD accounts.
- A TradingView account. The free plan works, with limits: 30 watchlist symbols and 2 indicators per chart.

There's nothing to install: the script uses only Python's standard library.

---

## Setup (once)

### 1. Get the code

```sh
git clone <this-repo-url>
cd tradingview-price-watcher
cp .env.example .env
```

`.env` holds your secrets. It is listed in `.gitignore`, so git never commits it.

### 2. Create a read-only Trading 212 API key

1. In the Trading 212 app or website, open **Settings → API**.
2. Click **Generate API key**.
3. Enable **only the Portfolio** permission and leave everything else off. A key with only this permission can read your positions, but it can't place trades or move money.
4. Optional: restrict the key to your home IP address.
5. Copy the **API key** and the **API secret**. The secret is shown only once.

### 3. Get your TradingView login cookie

This step lets the script update your watchlist and save the indicator for you. If you skip it, you'll have to paste the indicator by hand (see [Without the TradingView cookie](#without-the-tradingview-cookie)).

1. Log in to tradingview.com in Chrome.
2. Open **View → Developer → Developer Tools** and select the **Network** tab.
3. Reload the page (Cmd+R).
4. Click the first request in the list. Its type is `document`.
5. On the **Headers** tab, scroll to **Request Headers** and find the line `cookie:`.
6. Right-click its value and choose **Copy value**. It's one long line containing `sessionid=…`.

### 4. Fill in `.env`

Open `.env` in a text editor and fill it in. Each value goes on one line, with nothing around it:

```
T212_API_KEY=your-trading212-api-key
T212_API_SECRET=your-trading212-api-secret
TV_COOKIE=the-whole-cookie-value
TV_KEEP=BTCEUR,ETHEUR
```

| Setting | What it is |
|---|---|
| `T212_API_KEY`, `T212_API_SECRET` | Your Trading 212 key from step 2. Required. |
| `TV_COOKIE` | Your TradingView cookie from step 3. Optional. |
| `TV_KEEP` | Comma-separated symbols to keep in the watchlist even though you don't hold them on Trading 212. A bare ticker like `BTCEUR` matches any exchange; `BITSTAMP:BTCEUR` matches only that one. Optional. |

Never paste your keys into `sync.py` or any other file in the repo. Anything committed is public, and it stays in git history even after you delete it.

### 5. First run

```sh
python3 sync.py
```

You should see your holdings listed, then:

```
  Watchlist: added ...
Saved the "T212 avg buy price" indicator to your TradingView account.
```

### 6. Add the indicator to your chart (once)

In TradingView, open a chart, click **Indicators**, and add **My scripts → T212 avg buy price**. It stays on that chart layout when you switch symbols. If you use several layouts, or several charts in one layout, add it to each.

---

## Everyday use

| Command | What it does |
|---|---|
| `python3 sync.py` | Syncs once. |
| `python3 sync.py --watch` | Keeps running and re-syncs every 5 minutes. Leave it open in a terminal tab. |
| `python3 sync.py --watch 15` | Same, but every 15 minutes. |
| `open private/holdings.html` | Opens the holdings page in your browser. It refreshes itself while `--watch` runs. |

Each sync:

1. Reads your positions from Trading 212.
2. Finds each holding's TradingView symbol by ISIN and currency, and caches the result.
3. Updates the TradingView watchlist: adds what you hold and removes everything else except `TV_KEEP`.
4. Saves the indicator again whenever your holdings or average prices change. Reload a chart to see the new version.
5. Rewrites `private/holdings.html` with current prices.

---

## How the watchlist is handled

- If you have one watchlist, the script manages that one. If you have several, it only touches the one named **Trading 212**, so rename the list you want synced.
- **It removes everything you don't hold**, section headers included, except `TV_KEEP`. Take a screenshot of the list before your first run if you want to remember what was in it.
- Holdings are added biggest first, so if your plan's symbol limit is reached, only the smallest positions are left out. The script prints which ones, and the holdings page still lists all of them.
- If your portfolio comes back empty, the script leaves the watchlist untouched.

---

## Without the TradingView cookie

Without the cookie, the watchlist isn't synced. You save the indicator yourself whenever your holdings change. With `--watch`, a notification tells you when that's needed.

1. Run `pbcopy < private/avg_price_lines.pine` to copy the script.
2. In TradingView, open **Pine Editor**, the panel under the chart.
3. Create a new indicator, replace its code with the copied script, and click **Save**.
4. **Add to chart.**

Saved scripts are private. Never click **Publish**, because the script contains your average prices.

---

## Troubleshooting

| Message | What to do |
|---|---|
| `Paste your Trading 212 API key and secret into .env` | Fill in `T212_API_KEY` and `T212_API_SECRET`. |
| `Sync failed: HTTP Error 401` | The Trading 212 key or secret is wrong, or it was made for the demo account. Create a new live key. |
| `Sync failed: HTTP Error 403` | The key lacks the **Portfolio** permission. |
| `Sync failed: HTTP Error 429` | Too many requests. Wait a few seconds. |
| `TradingView watchlist not synced: not logged in` or a `403` / `401` from TradingView | Your cookie has expired, for example because you logged out of TradingView. Repeat setup step 3 and replace `TV_COOKIE`. |
| `rename the watchlist to sync to "Trading 212"` | You have several watchlists. Rename the one to sync. |
| `TradingView refused … Not in the watchlist: …` | Your plan's watchlist limit is reached. Those holdings stay off the list. |
| `TradingView rejected the indicator: …` | TradingView couldn't compile the script. Open an issue and include the message. |
| `No valid TradingView symbol for …` | The holding couldn't be matched. Add it to `private/symbols.json` by hand, e.g. `"VUSAl_EQ": "LSE:VUSA"`. |
| A chart has no yellow line | Check for the yellow box in the corner. If you see the box, the line is off-screen: right-click the price scale and choose **Auto (Fits data to screen)**. If there's no box either, the indicator isn't on that chart, so add it (setup step 6). |
| A symbol maps to the wrong exchange | Edit its entry in `private/symbols.json`. Your edits are kept. |

---

## Security

- **The Trading 212 key is read-only.** With only the Portfolio permission, a leaked key exposes your positions, but it can't trade, and the API has no way to withdraw money.
- **The TradingView cookie is a login.** Anyone who has it can use your TradingView account until you log out, though they can't touch your Trading 212 money. Treat it like a password. Logging out of TradingView cancels it.
- **Secrets stay out of git.** They live only in `.env`, which is gitignored.
- **Your portfolio data stays out of git.** Everything about your holdings goes into `private/`, which is gitignored and readable only by your user account.
- **No third-party packages.** With only Python's standard library, there's no dependency to compromise.
- **Fixed destinations.** The key is sent only to `live.trading212.com`, and the cookie only to `www.tradingview.com` and `pine-facade.tradingview.com`. Redirects are refused, so neither can be forwarded elsewhere. TradingView's public symbol search receives only ISINs.
- **Unofficial TradingView endpoints.** The watchlist and indicator saving use the endpoints TradingView's own website calls. They aren't documented, so they may change, and automating your account may conflict with TradingView's terms. Use at your own risk.

Before you push, check that nothing private is staged:

```sh
git status --ignored
```

`.env` and `private/` must appear under "Ignored files", never under "Changes to be committed".

---

## Development

```sh
python3 test_sync.py
```

| File | Purpose |
|---|---|
| `sync.py` | The whole tool. |
| `test_sync.py` | Tests. They make no network calls. |
| `.env.example` | Settings template. Copy it to `.env`. |
| `private/` | Generated per user and gitignored: `symbols.json` (symbol cache), `holdings.html` and `avg_price_lines.pine`. |
