"""
JP Portfolio Monitor — Twelve Data 版
=======================================
Twelve Data /quote エンドポイントで全銘柄を1リクエストで一括取得。
Yahoo Finance スクレイピング不使用のため Render クラウドで安定動作。

環境変数 (Render ダッシュボードで設定):
  TWELVE_API_KEY : Twelve Data API キー  ← 必須
  GITHUB_TOKEN   : GitHub Personal Access Token
  GITHUB_REPO    : "ユーザー名/リポジトリ名"
  GITHUB_BRANCH  : ブランチ名 (デフォルト: main)
"""

import os, time, json, base64, requests
from flask import Flask, jsonify, request, send_from_directory
from datetime import datetime

app = Flask(__name__, static_folder="static")

TWELVE_API_KEY = os.environ.get("TWELVE_API_KEY", "")
GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO    = os.environ.get("GITHUB_REPO", "")
GITHUB_BRANCH  = os.environ.get("GITHUB_BRANCH", "main")
PORTFOLIO_FILE = "portfolio.json"

# ── デフォルト銘柄リスト ──────────────────────────────────
DEFAULT_PORTFOLIO = [
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

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "jp-portfolio-monitor/1.0"})


# ════════════════════════════════════════════════════════
# Twelve Data API
# ════════════════════════════════════════════════════════

def fetch_quotes_twelvedata(portfolio: list) -> list:
    """
    /quote エンドポイントで全銘柄を1リクエストで一括取得。
    symbol=7741:TSE,6758:TSE,... のように exchange=TSE を明示。
    無料プラン: 分 8リクエスト / 月 800リクエスト
    15銘柄を1回のバッチで取得 → 1リクエスト消費。
    """
    # TSE シンボル形式: "コード:TSE"
    symbols = ",".join(f"{s['code']}:TSE" for s in portfolio)

    url = "https://api.twelvedata.com/quote"
    params = {
        "symbol":   symbols,
        "apikey":   TWELVE_API_KEY,
        "dp":       2,          # 小数点以下2桁
    }

    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] Twelve Data /quote — {len(portfolio)}銘柄 一括取得...")

    try:
        r = SESSION.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  ERROR: {e}")
        # 全銘柄エラー
        return [{**s, "price":0,"prev":0,"change":0,
                 "pct":0,"volume":0,"date":"","ok":False,
                 "error":str(e)} for s in portfolio]

    # 1銘柄の場合はdictで返ることがある → 統一
    if isinstance(data, dict) and "symbol" in data:
        key = data["symbol"].split(":")[0]   # "7741:TSE" → "7741"
        data = {key: data}
    elif isinstance(data, dict):
        # キーが "7741:TSE" 形式の場合は "7741" に正規化
        data = {k.split(":")[0]: v for k, v in data.items()}

    results = []
    for stock in portfolio:
        code = stock["code"]
        q    = data.get(code, {})

        # Twelve Data エラーチェック
        if not q or q.get("status") == "error":
            msg = q.get("message", "no data") if q else "not in response"
            print(f"  ✗ {code} {stock['ja']:<14} error: {msg}")
            results.append({**stock, "price":0,"prev":0,"change":0,
                             "pct":0,"volume":0,"date":"","ok":False,"error":msg})
            continue

        try:
            price   = float(q["close"])
            prev    = float(q["previous_close"])
            chg     = price - prev
            pct     = float(q.get("percent_change", 0))
            vol     = int(q.get("volume", 0) or 0)
            date    = str(q.get("datetime", ""))[:10]

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
            print(f"  ✓ {code} {stock['ja']:<14} "
                  f"¥{round(price):>8,}  ({sign}{pct:.2f}%)  {date}")

        except Exception as e:
            print(f"  ✗ {code} {stock['ja']:<14} parse error: {e}  raw={q}")
            results.append({**stock, "price":0,"prev":0,"change":0,
                             "pct":0,"volume":0,"date":"","ok":False,
                             "error":str(e)})

    ok_n = sum(1 for r in results if r["ok"])
    print(f"  → Done: {ok_n}/{len(results)}\n")
    return results


def search_twelvedata(code: str) -> dict:
    """銘柄コード確認: /quote で1銘柄取得"""
    url = "https://api.twelvedata.com/quote"
    params = {"symbol": f"{code}:TSE", "apikey": TWELVE_API_KEY, "dp": 2}
    try:
        r = SESSION.get(url, params=params, timeout=10)
        r.raise_for_status()
        q = r.json()
        if q.get("status") == "error":
            return {"found": False, "error": q.get("message", "not found")}
        price = float(q.get("close", 0))
        if not price:
            return {"found": False, "error": "価格データがありません"}
        return {
            "found":   True,
            "code":    code,
            "name_en": q.get("name", ""),
            "price":   round(price),
        }
    except Exception as e:
        return {"found": False, "error": str(e)}


# ════════════════════════════════════════════════════════
# GitHub API
# ════════════════════════════════════════════════════════

def gh_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

def github_get_file(filepath):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filepath}"
    r = requests.get(url, headers=gh_headers(),
                     params={"ref": GITHUB_BRANCH}, timeout=10)
    if r.status_code == 404:
        return None, None
    r.raise_for_status()
    d = r.json()
    return base64.b64decode(d["content"]).decode("utf-8"), d["sha"]

def github_put_file(filepath, content_str, sha=None, message="Update portfolio"):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filepath}"
    payload = {
        "message": message,
        "content": base64.b64encode(content_str.encode("utf-8")).decode("utf-8"),
        "branch":  GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    r = requests.put(url, headers=gh_headers(), json=payload, timeout=10)
    r.raise_for_status()
    return r.json()


# ════════════════════════════════════════════════════════
# Routes
# ════════════════════════════════════════════════════════

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/search")
def search():
    """?code=9433 → 銘柄情報を返す"""
    code = request.args.get("code", "").strip().zfill(4)
    if not code.isdigit() or len(code) != 4:
        return jsonify({"found": False, "error": "4桁の数字で入力してください"}), 400
    if not TWELVE_API_KEY:
        return jsonify({"found": False, "error": "TWELVE_API_KEY未設定"}), 500
    result = search_twelvedata(code)
    return jsonify(result)


@app.route("/api/portfolio", methods=["GET"])
def get_portfolio():
    """GitHubからportfolio.json取得。なければデフォルト。"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return jsonify(DEFAULT_PORTFOLIO)
    try:
        content, _ = github_get_file(PORTFOLIO_FILE)
        if content is None:
            return jsonify(DEFAULT_PORTFOLIO)
        return jsonify(json.loads(content))
    except Exception as e:
        print(f"GitHub get error: {e}")
        return jsonify(DEFAULT_PORTFOLIO)


@app.route("/api/portfolio", methods=["POST"])
def save_portfolio():
    """portfolio.jsonをGitHubに保存。"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return jsonify({"error": "GITHUB_TOKEN / GITHUB_REPO が未設定"}), 500
    portfolio = request.json
    if not isinstance(portfolio, list):
        return jsonify({"error": "無効なデータ形式"}), 400
    try:
        _, sha = github_get_file(PORTFOLIO_FILE)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        github_put_file(
            PORTFOLIO_FILE,
            json.dumps(portfolio, ensure_ascii=False, indent=2),
            sha=sha,
            message=f"Update portfolio ({len(portfolio)} stocks) {ts}",
        )
        return jsonify({"ok": True, "count": len(portfolio)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/quotes", methods=["POST"])
def quotes():
    """POSTボディ: [{code, ja, en, sector}, ...] → 株価を返す"""
    if not TWELVE_API_KEY:
        return jsonify({"error": "TWELVE_API_KEY が設定されていません。Renderの環境変数を確認してください。"}), 500

    portfolio = request.json
    if not isinstance(portfolio, list) or len(portfolio) == 0:
        return jsonify({"error": "銘柄リストが空です"}), 400

    results = fetch_quotes_twelvedata(portfolio)
    return jsonify(results)


@app.route("/health")
def health():
    import sys
    return jsonify({
        "status":          "ok",
        "time":            datetime.now().isoformat(),
        "python":          sys.version,
        "twelve_ready":    bool(TWELVE_API_KEY),
        "github_ready":    bool(GITHUB_TOKEN and GITHUB_REPO),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
