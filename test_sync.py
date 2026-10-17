import tempfile
from base64 import b64encode
from pathlib import Path

import sync
from sync import SAFE_SYMBOL, pick, plan, render

HITS = [
    {"symbol": "VUSA", "exchange": "Euronext Amsterdam", "prefix": "EURONEXT", "currency_code": "EUR", "isin": "IE00B3XXRP09"},
    {"symbol": "VUSA", "exchange": "LSE", "currency_code": "GBP", "isin": "IE00B3XXRP09"},
    {"symbol": "VUSA", "exchange": "XETR", "currency_code": "EUR", "isin": "IE00B3XXRP09"},
    {"symbol": "BPE5", "exchange": "XETR", "currency_code": "EUR", "isin": "GB0007980591"},
    {"symbol": "BP.", "exchange": "LSE", "currency_code": "GBX", "isin": "GB0007980591", "is_primary_listing": True},
    {"symbol": "BP", "exchange": "NYSE", "currency_code": "USD", "isin": "US0556221044"},
]


def test_pick():
    assert pick(HITS, "IE00B3XXRP09", "GBP") == "LSE:VUSA"
    assert pick(HITS, "IE00B3XXRP09", "EUR") == "EURONEXT:VUSA"
    assert pick(HITS, "GB0007980591", "GBX") == "LSE:BP."
    assert pick(HITS, "GB0007980591", "GBP") == "LSE:BP."
    assert pick(HITS, "GB0007980591", "USD") is None
    assert pick(HITS, "IE00B3XXRP09", "USD") is None


def test_render():
    page, pine = render({"NASDAQ:AAPL": ("AAPL_US_EQ", "Apple <Inc>", 170.25, 187.28, "USD"),
                         "LSE:BP.": ("BPl_EQ", "BP", 412, 400, "GBX"),
                         "NYSE:KO": ("KO_US_EQ", "Free share", 0, 60, "USD")})
    assert ('    "LSE:BP." => 412.00000000\n    "NASDAQ:AAPL" => 170.25000000\n'
            '    "NYSE:KO" => 0.00000000\n    => float(na)\n') in pine
    assert 'indicator("T212 avg buy price", overlay = true)' in pine
    assert 'href="https://www.tradingview.com/chart/?symbol=NASDAQ%3AAAPL"' in page
    assert "Apple &lt;Inc&gt;" in page and '">+10.0%' in page and '">-2.9%' in page


def test_symbols_cannot_inject_pine():
    assert SAFE_SYMBOL.fullmatch("LSE:BP.") and SAFE_SYMBOL.fullmatch("EURONEXT:VUSA-ETFP")
    assert not SAFE_SYMBOL.fullmatch('LSE:X" => 1\nalert("x')
    assert not SAFE_SYMBOL.fullmatch("NASDAQ:AAPL,NYSE:KO")


def test_plan():
    current = ["###Crypto", "BITSTAMP:BTCEUR", "KRAKEN:ETHEUR", "NASDAQ:TSLA", "LSE:VUSA", "TVC:GOLD"]
    remove, add = plan(current, ["NASDAQ:AAPL", "LSE:VUSA", "LSE:BP."], {"BTCEUR", "ETHEUR", "TVC:GOLD"})
    assert remove == ["###Crypto", "NASDAQ:TSLA"]
    assert add == ["NASDAQ:AAPL", "LSE:BP."]


def test_save_pine():
    sent = {}
    real = sync.get_json
    sync.get_json = lambda url, headers, data: sent.update(url=url, headers=headers, data=data) or {"success": True}
    try:
        assert sync.save_pine("sessionid=s; csrftoken=t", '//@version=6\nindicator("x")')
    finally:
        sync.get_json = real
    assert sent["url"].endswith("save/new?name=T212+avg+buy+price&allow_overwrite=true")
    assert sent["headers"]["Cookie"] == "sessionid=s; csrftoken=t"
    assert sent["headers"]["Content-Type"] == "multipart/form-data; boundary=t212-sync-boundary-7f3a9c"
    assert b'name="source"\r\n\r\n//@version=6\nindicator("x")\r\n--t212-sync-boundary-7f3a9c--' in sent["data"]


def test_env_file():
    with tempfile.TemporaryDirectory() as d:
        sync.ENV_FILE = Path(d) / ".env"
        sync.ENV_FILE.write_text('# comment\nT212_API_KEY = "abc"\nT212_API_SECRET=x=y\nTV_COOKIE=a=1; b="2"\n')
        env = sync.read_env()
        assert sync.auth_header(env) == "Basic " + b64encode(b"abc:x=y").decode()
        assert env["TV_COOKIE"] == 'a=1; b="2"'


if __name__ == "__main__":
    test_pick(), test_render(), test_symbols_cannot_inject_pine(), test_plan(), test_save_pine(), test_env_file()
    print("ok")
