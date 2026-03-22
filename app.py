"""
JP Portfolio Monitor — 超軽量版
================================
依存: flask + requests のみ (pandas/yfinance不使用)
メモリ使用量: ~60MB (Render無料 512MB制限内で余裕で動作)

Yahoo Finance v8 Chart API を直接呼び出し。
クラウドサーバーからも動作するよう適切なヘッダーを設定。
"""

import os, time, requests
from flask import Flask, jsonify, send_from_directory
from datetime import datetime

app = Flask(__name__, static_folder="static")

PORTFOLIO = [
    {"code":"7741","ja":"ホーヤ",              "en":"HOYA",           "sector":"テクノロジー"},
    {"code":"6740","ja":"ジャパンディスプレイ","en":"Japan Display",  "sector":"テクノロジー"},
    {"code":"6758","ja":"ソニーグループ",       "en":"Sony Group",     "sector":"テクノロジー"},
    {"code":"8136","ja":"サンリオ",            "en":"Sanrio",         "sector":"エンタメ"},
    {"code":"3350","ja":"メタプラネット",       "en":"Metaplanet",     "sector":"テクノロジー"},
    {"code":"7974","ja":"任天堂",              "en":"Nintendo",       "sector":"エンタメ"},
    {"code":"9984","ja":"ソフトバンクG",        "en":"SoftBank Group", "sector":"通信・投資"},
    {"code":"8058","ja":"三菱商事",            "en":"Mitsubishi Corp","sector":"商社"},
    {"code":"8031","ja":"三井物産",            "en":"Mitsui & Co",   "sector":"商社"},
    {"code":"8001","ja":"伊藤忠商事",          "en":"ITOCHU",         "sector":"商社"},
    {"code":"8002","ja":"丸紅",                "en":"Marubeni",       "sector":"商社"},
    {"code":"8053","ja":"住友商事",            "en":"Sumitomo Corp",  "sector":"商社"},
    {"code":"8306","ja":"三菱UFJ",             "en":"MUFG",           "sector":"銀行"},
    {"code":"8411","ja":"みずほFG",            "en":"Mizuho FG",      "sector":"銀行"},
    {"code":"8316","ja":"三井住友FG",          "en":"SMFG",           "sector":"銀行"},
]

# ブラウザに見せかけるヘッダー（クラウドIPの制限を回避）
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8",
    "Referer": "https://finance.yahoo.com/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def fetch_one(code: str) -> dict:
    """
    Yahoo Finance v8 Chart API で1銘柄取得。
    pandas不使用・純粋なJSON解析のみ。
    """
    ticker = f"{code}.T"
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {
        "range":           "5d",
        "interval":        "1d",
        "includePrePost":  "false",
        "events":          "div,splits",
    }

    try:
        r = SESSION.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "timeout"}
    except requests.exceptions.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    try:
        result = data["chart"]["result"][0]
        meta   = result["meta"]

        price = meta.get("regularMarketPrice") or meta.get("previousClose", 0)
        prev  = meta.get("previousClose") or meta.get("chartPreviousClose", price)

        if not price:
            return {"ok": False, "error": "no price"}

        price = float(price)
        prev  = float(prev)
        chg   = price - prev
        pct   = (chg / prev * 100) if prev else 0.0

        # 日付: タイムスタンプ配列の最後 or meta
        try:
            ts_list = result.get("timestamp", [])
            if ts_list:
                last_ts = ts_list[-1]
                date = datetime.utcfromtimestamp(last_ts).strftime("%Y-%m-%d")
            else:
                date = datetime.now().strftime("%Y-%m-%d")
        except Exception:
            date = datetime.now().strftime("%Y-%m-%d")

        vol = meta.get("regularMarketVolume", 0) or 0

        return {
            "ok":     True,
            "price":  round(price),
            "prev":   round(prev),
            "change": round(chg),
            "pct":    round(pct, 2),
            "volume": int(vol),
            "date":   date,
        }

    except (KeyError, IndexError, TypeError) as e:
        return {"ok": False, "error": f"parse error: {e}"}


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/quotes")
def quotes():
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] Fetching {len(PORTFOLIO)} stocks (no pandas)...")

    results = []
    for i, stock in enumerate(PORTFOLIO):
        d = fetch_one(stock["code"])
        row = {**stock, **d}
        results.append(row)

        if d["ok"]:
            sign = "+" if d["change"] >= 0 else ""
            print(f"  ✓ {stock['code']} {stock['ja']:<14} "
                  f"¥{d['price']:>8,}  ({sign}{d['pct']:.2f}%)  {d['date']}")
        else:
            print(f"  ✗ {stock['code']} {stock['ja']:<14} {d.get('error','')}")

        # 連続リクエストを少し間隔を空ける
        if i < len(PORTFOLIO) - 1:
            time.sleep(0.2)

    ok_n = sum(1 for r in results if r["ok"])
    print(f"  → Done: {ok_n}/{len(results)}\n")
    return jsonify(results)


@app.route("/health")
def health():
    import sys
    return jsonify({
        "status": "ok",
        "time":   datetime.now().isoformat(),
        "python": sys.version,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
