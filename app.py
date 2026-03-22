from flask import Flask, jsonify, send_from_directory
import yfinance as yf
from datetime import datetime
import os

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

# ── 메인 페이지 ───────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("static", "index.html")

# ── 주가 API ─────────────────────────────────────────────
@app.route("/api/quotes")
def quotes():
    tickers = [s["ticker"] for s in PORTFOLIO]
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] Fetching {len(tickers)} tickers from Yahoo Finance...")

    try:
        raw = yf.download(
            tickers,
            period="5d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    results = []
    for s in PORTFOLIO:
        t = s["ticker"]
        try:
            closes = raw["Close"][t].dropna()
            if len(closes) == 0:
                raise ValueError("no data")
            price = float(closes.iloc[-1])
            prev  = float(closes.iloc[-2]) if len(closes) >= 2 else price
            chg   = price - prev
            pct   = chg / prev * 100 if prev else 0.0
            date  = str(closes.index[-1].date())
            try:
                vol = int(raw["Volume"][t].dropna().iloc[-1])
            except Exception:
                vol = 0
            results.append({
                **s,
                "price":  round(price),
                "prev":   round(prev),
                "change": round(chg),
                "pct":    round(pct, 2),
                "volume": vol,
                "date":   date,
                "ok":     True,
            })
            print(f"  ✓ {s['code']} {s['ja']:<14} ¥{round(price):>8,}  "
                  f"({'+'if chg>=0 else ''}{round(chg):,}円 / "
                  f"{'+'if pct>=0 else ''}{pct:.2f}%)  {date}")
        except Exception as e:
            print(f"  ✗ {s['code']} {s['ja']:<14} failed: {e}")
            results.append({**s, "price":0,"prev":0,"change":0,
                            "pct":0,"volume":0,"date":"","ok":False})

    ok_n = sum(1 for r in results if r["ok"])
    print(f"  → Done: {ok_n}/{len(results)}\n")
    return jsonify(results)

# ── 헬스체크 (Render 슬립 방지용) ──────────────────────
@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
