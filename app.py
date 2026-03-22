import os, requests
from flask import Flask, jsonify, send_from_directory
from datetime import datetime

app = Flask(__name__, static_folder="static")

# ── Twelve Data API キー ───────────────────────────────────
# 環境変数から読み込む（Renderのダッシュボードで設定）
TWELVE_API_KEY = os.environ.get("TWELVE_API_KEY", "")

PORTFOLIO = [
    {"code":"7741","symbol":"7741",  "ja":"ホーヤ",              "en":"HOYA",           "sector":"テクノロジー"},
    {"code":"6740","symbol":"6740",  "ja":"ジャパンディスプレイ","en":"Japan Display",  "sector":"テクノロジー"},
    {"code":"6758","symbol":"6758",  "ja":"ソニーグループ",       "en":"Sony Group",     "sector":"テクノロジー"},
    {"code":"8136","symbol":"8136",  "ja":"サンリオ",            "en":"Sanrio",         "sector":"エンタメ"},
    {"code":"3350","symbol":"3350",  "ja":"メタプラネット",       "en":"Metaplanet",     "sector":"テクノロジー"},
    {"code":"7974","symbol":"7974",  "ja":"任天堂",              "en":"Nintendo",       "sector":"エンタメ"},
    {"code":"9984","symbol":"9984",  "ja":"ソフトバンクG",        "en":"SoftBank Group", "sector":"通信・投資"},
    {"code":"8058","symbol":"8058",  "ja":"三菱商事",            "en":"Mitsubishi Corp","sector":"商社"},
    {"code":"8031","symbol":"8031",  "ja":"三井物産",            "en":"Mitsui & Co",   "sector":"商社"},
    {"code":"8001","symbol":"8001",  "ja":"伊藤忠商事",          "en":"ITOCHU",         "sector":"商社"},
    {"code":"8002","symbol":"8002",  "ja":"丸紅",                "en":"Marubeni",       "sector":"商社"},
    {"code":"8053","symbol":"8053",  "ja":"住友商事",            "en":"Sumitomo Corp",  "sector":"商社"},
    {"code":"8306","symbol":"8306",  "ja":"三菱UFJ",             "en":"MUFG",           "sector":"銀行"},
    {"code":"8411","symbol":"8411",  "ja":"みずほFG",            "en":"Mizuho FG",      "sector":"銀行"},
    {"code":"8316","symbol":"8316",  "ja":"三井住友FG",          "en":"SMFG",           "sector":"銀行"},
]


def fetch_quotes_twelvedata():
    """
    Twelve Data /quote エンドポイントで全銘柄を一括取得。
    symbols=7741,6758,... のようにカンマ区切りで1リクエスト。
    exchange=TSE を指定して東証銘柄を明示。
    """
    symbols = ",".join(s["symbol"] for s in PORTFOLIO)
    url = "https://api.twelvedata.com/quote"
    params = {
        "symbol":   symbols,
        "exchange": "TSE",
        "apikey":   TWELVE_API_KEY,
    }

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # 1銘柄の場合はdictで返ってくる場合があるので統一
    if isinstance(data, dict) and "symbol" in data:
        data = {data["symbol"]: data}

    results = []
    for stock in PORTFOLIO:
        sym = stock["symbol"]
        q   = data.get(sym, {})

        # エラーチェック
        if q.get("status") == "error" or not q.get("close"):
            print(f"  ✗ {sym} {stock['ja']:<14} error: {q.get('message','no data')}")
            results.append({**stock, "price":0,"prev":0,"change":0,
                             "pct":0,"volume":0,"date":"","ok":False})
            continue

        try:
            price  = float(q["close"])
            prev   = float(q["previous_close"])
            chg    = price - prev
            pct    = float(q.get("percent_change", chg / prev * 100 if prev else 0))
            vol    = int(q.get("volume", 0))
            date   = q.get("datetime", "")[:10]

            results.append({
                **stock,
                "price":  round(price),
                "prev":   round(prev),
                "change": round(chg),
                "pct":    round(pct, 2),
                "volume": vol,
                "date":   date,
                "ok":     True,
            })
            sign = "+" if chg >= 0 else ""
            print(f"  ✓ {sym} {stock['ja']:<14} ¥{round(price):>8,}  "
                  f"({sign}{pct:.2f}%)  {date}")
        except Exception as e:
            print(f"  ✗ {sym} {stock['ja']:<14} parse error: {e}")
            results.append({**stock, "price":0,"prev":0,"change":0,
                             "pct":0,"volume":0,"date":"","ok":False})

    return results


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/quotes")
def quotes():
    if not TWELVE_API_KEY:
        return jsonify({"error": "TWELVE_API_KEY が設定されていません。Renderの環境変数を確認してください。"}), 500

    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] Twelve Data API で {len(PORTFOLIO)} 銘柄取得中...")

    try:
        results = fetch_quotes_twelvedata()
    except Exception as e:
        print(f"  ERROR: {e}")
        return jsonify({"error": str(e)}), 500

    ok_n = sum(1 for r in results if r["ok"])
    print(f"  → 完了: {ok_n}/{len(results)}\n")
    return jsonify(results)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
