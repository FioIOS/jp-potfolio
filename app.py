import os, time, json
from flask import Flask, jsonify, send_from_directory
from datetime import datetime

app = Flask(__name__, static_folder="static")

PORTFOLIO = [
    {"code":"7741","ticker":"7741.T","ja":"ホーヤ",              "en":"HOYA",           "sector":"テクノロジー"},
    {"code":"6740","ticker":"6740.T","ja":"ジャパンディスプレイ","en":"Japan Display",  "sector":"テクノロジー"},
    {"code":"6758","ticker":"6758.T","ja":"ソニーグループ",       "en":"Sony Group",     "sector":"テクノロジー"},
    {"code":"8136","ticker":"8136.T","ja":"サンリオ",            "en":"Sanrio",         "sector":"エンタメ"},
    {"code":"3350","ticker":"3350.T","ja":"メタプラネット",       "en":"Metaplanet",     "sector":"テクノロジー"},
    {"code":"7974","ticker":"7974.T","ja":"任天堂",              "en":"Nintendo",       "sector":"エンタメ"},
    {"code":"9984","ticker":"9984.T","ja":"ソフトバンクG",        "en":"SoftBank Group", "sector":"通信・投資"},
    {"code":"8058","ticker":"8058.T","ja":"三菱商事",            "en":"Mitsubishi Corp","sector":"商社"},
    {"code":"8031","ticker":"8031.T","ja":"三井物産",            "en":"Mitsui & Co",   "sector":"商社"},
    {"code":"8001","ticker":"8001.T","ja":"伊藤忠商事",          "en":"ITOCHU",         "sector":"商社"},
    {"code":"8002","ticker":"8002.T","ja":"丸紅",                "en":"Marubeni",       "sector":"商社"},
    {"code":"8053","ticker":"8053.T","ja":"住友商事",            "en":"Sumitomo Corp",  "sector":"商社"},
    {"code":"8306","ticker":"8306.T","ja":"三菱UFJ",             "en":"MUFG",           "sector":"銀行"},
    {"code":"8411","ticker":"8411.T","ja":"みずほFG",            "en":"Mizuho FG",      "sector":"銀行"},
    {"code":"8316","ticker":"8316.T","ja":"三井住友FG",          "en":"SMFG",           "sector":"銀行"},
]

def fetch_one(ticker, retries=3):
    """
    1銘柄を個別取得。Rate limit時はwait&retryする。
    yf.Ticker().history()はdownload()より軽量でクラウド環境に適している。
    """
    import yfinance as yf

    for attempt in range(retries):
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="5d", interval="1d", auto_adjust=True)

            if hist.empty:
                raise ValueError("empty dataframe")

            closes = hist["Close"].dropna()
            if len(closes) == 0:
                raise ValueError("no close data")

            price = float(closes.iloc[-1])
            prev  = float(closes.iloc[-2]) if len(closes) >= 2 else price
            chg   = price - prev
            pct   = chg / prev * 100 if prev else 0.0
            date  = str(closes.index[-1].date())

            try:
                vol = int(hist["Volume"].dropna().iloc[-1])
            except Exception:
                vol = 0

            return {
                "price":  round(price),
                "prev":   round(prev),
                "change": round(chg),
                "pct":    round(pct, 2),
                "volume": vol,
                "date":   date,
                "ok":     True,
            }

        except Exception as e:
            err_str = str(e).lower()
            # Rate limit → 少し待ってリトライ
            if "rate" in err_str or "429" in err_str or "too many" in err_str:
                wait = 3 * (attempt + 1)
                print(f"  ⚠ Rate limit [{ticker}], waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"  ✗ [{ticker}] attempt {attempt+1}: {e}")
                if attempt < retries - 1:
                    time.sleep(1)

    return {"price":0,"prev":0,"change":0,"pct":0,"volume":0,"date":"","ok":False}


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/quotes")
def quotes():
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] Fetching {len(PORTFOLIO)} tickers...")

    results = []
    for s in PORTFOLIO:
        data = fetch_one(s["ticker"])
        row  = {**s, **data}
        results.append(row)

        if data["ok"]:
            sign = "+" if data["change"] >= 0 else ""
            print(f"  ✓ {s['code']} {s['ja']:<14} "
                  f"¥{data['price']:>8,}  "
                  f"({sign}{data['pct']:.2f}%)  {data['date']}")
        else:
            print(f"  ✗ {s['code']} {s['ja']:<14} 取得失敗")

        # 連続リクエストの間に少し間隔を空ける（Rate limit対策）
        time.sleep(0.3)

    ok_n = sum(1 for r in results if r["ok"])
    print(f"  → Done: {ok_n}/{len(results)}\n")
    return jsonify(results)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
