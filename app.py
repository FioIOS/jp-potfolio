"""
JP Portfolio Monitor — 完全版
=================================
機能:
  GET  /                    → ダッシュボード
  GET  /api/quotes          → 保有銘柄の株価取得
  GET  /api/search?code=    → 銘柄コード確認 (名称自動取得)
  GET  /api/portfolio       → 保有銘柄リスト取得 (GitHubから)
  POST /api/portfolio       → 保有銘柄リスト保存 (GitHubへ)
  GET  /health              → ヘルスチェック

環境変数 (Renderダッシュボードで設定):
  GITHUB_TOKEN   : GitHub Personal Access Token
  GITHUB_REPO    : "ユーザー名/リポジトリ名" 例: "FioIOS/jp-potfolio"
  GITHUB_BRANCH  : ブランチ名 (デフォルト: main)
"""

import os, time, json, base64, requests
from flask import Flask, jsonify, request, send_from_directory
from datetime import datetime

app = Flask(__name__, static_folder="static")

# ── 環境変数 ──────────────────────────────────────────────
GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO   = os.environ.get("GITHUB_REPO", "")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
PORTFOLIO_FILE = "portfolio.json"   # GitHubリポジトリ内のファイル名

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

# ── HTTPヘッダー ──────────────────────────────────────────
YF_HEADERS = {
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
SESSION.headers.update(YF_HEADERS)


# ════════════════════════════════════════════════════════
# GitHub API ヘルパー
# ════════════════════════════════════════════════════════

def gh_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

def github_get_file(filepath):
    """GitHubからファイルを取得。(content, sha) を返す。"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filepath}"
    r = requests.get(url, headers=gh_headers(),
                     params={"ref": GITHUB_BRANCH}, timeout=10)
    if r.status_code == 404:
        return None, None
    r.raise_for_status()
    data = r.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return content, data["sha"]

def github_put_file(filepath, content_str, sha=None, message="Update portfolio"):
    """GitHubにファイルを保存（新規作成 or 更新）。"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filepath}"
    payload = {
        "message": message,
        "content": base64.b64encode(content_str.encode("utf-8")).decode("utf-8"),
        "branch":  GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    r = requests.put(url, headers=gh_headers(),
                     json=payload, timeout=10)
    r.raise_for_status()
    return r.json()


# ════════════════════════════════════════════════════════
# 株価取得 (Yahoo Finance v8 API)
# ════════════════════════════════════════════════════════

def fetch_quote(code: str) -> dict:
    ticker = f"{code}.T"
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"range": "5d", "interval": "1d",
              "includePrePost": "false", "events": "div,splits"}
    try:
        r = SESSION.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    try:
        result = data["chart"]["result"][0]
        meta   = result["meta"]
        price  = float(meta.get("regularMarketPrice") or meta.get("previousClose", 0))
        prev   = float(meta.get("previousClose") or meta.get("chartPreviousClose", price))
        if not price:
            return {"ok": False, "error": "no price"}
        chg = price - prev
        pct = (chg / prev * 100) if prev else 0.0
        try:
            ts_list = result.get("timestamp", [])
            date = datetime.utcfromtimestamp(ts_list[-1]).strftime("%Y-%m-%d") if ts_list else datetime.now().strftime("%Y-%m-%d")
        except Exception:
            date = datetime.now().strftime("%Y-%m-%d")
        vol = int(meta.get("regularMarketVolume", 0) or 0)
        return {"ok": True, "price": round(price), "prev": round(prev),
                "change": round(chg), "pct": round(pct, 2),
                "volume": vol, "date": date}
    except Exception as e:
        return {"ok": False, "error": f"parse: {e}"}


# ════════════════════════════════════════════════════════
# Routes
# ════════════════════════════════════════════════════════

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ── 1. 銘柄コード確認 ──────────────────────────────────
@app.route("/api/search")
def search():
    """
    ?code=9433 → Yahoo Finance から銘柄情報を取得して返す
    レスポンス: {code, name_ja, name_en, found}
    """
    code = request.args.get("code", "").strip().zfill(4)
    if not code.isdigit() or len(code) != 4:
        return jsonify({"found": False, "error": "コードは4桁の数字で入力してください"}), 400

    ticker = f"{code}.T"
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"range": "1d", "interval": "1d"}
    try:
        r = SESSION.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        result = data["chart"]["result"][0]
        meta   = result["meta"]

        name_raw = meta.get("longName") or meta.get("shortName") or ""
        price    = meta.get("regularMarketPrice") or meta.get("previousClose")

        if not price:
            return jsonify({"found": False, "error": "データが見つかりません"})

        # 英語名をそのまま使い、日本語名は入力してもらう
        return jsonify({
            "found":    True,
            "code":     code,
            "name_en":  name_raw,
            "price":    round(float(price)),
        })
    except Exception as e:
        return jsonify({"found": False, "error": str(e)})


# ── 2. 銘柄リスト取得 ─────────────────────────────────
@app.route("/api/portfolio", methods=["GET"])
def get_portfolio():
    """GitHubからportfolio.jsonを取得。なければデフォルトを返す。"""
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


# ── 3. 銘柄リスト保存 ─────────────────────────────────
@app.route("/api/portfolio", methods=["POST"])
def save_portfolio():
    """portfolio.jsonをGitHubに保存。"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return jsonify({"error": "GITHUB_TOKEN / GITHUB_REPO が未設定です"}), 500

    portfolio = request.json
    if not isinstance(portfolio, list):
        return jsonify({"error": "無効なデータ形式"}), 400

    try:
        _, sha = github_get_file(PORTFOLIO_FILE)
        ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        github_put_file(
            PORTFOLIO_FILE,
            json.dumps(portfolio, ensure_ascii=False, indent=2),
            sha=sha,
            message=f"Update portfolio ({len(portfolio)} stocks) {ts}",
        )
        return jsonify({"ok": True, "count": len(portfolio)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── 4. 株価一括取得 ──────────────────────────────────
@app.route("/api/quotes", methods=["POST"])
def quotes():
    """
    POSTボディ: [{code, ja, en, sector}, ...]
    保存済みポートフォリオの株価を返す。
    """
    portfolio = request.json
    if not isinstance(portfolio, list):
        return jsonify({"error": "invalid body"}), 400

    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] Fetching {len(portfolio)} stocks...")

    results = []
    for i, stock in enumerate(portfolio):
        d   = fetch_quote(stock["code"])
        row = {**stock, **d}
        results.append(row)
        if d["ok"]:
            sign = "+" if d["change"] >= 0 else ""
            print(f"  ✓ {stock['code']} {stock['ja']:<14} "
                  f"¥{d['price']:>8,}  ({sign}{d['pct']:.2f}%)  {d['date']}")
        else:
            print(f"  ✗ {stock['code']} {stock['ja']:<14} {d.get('error','')}")
        if i < len(portfolio) - 1:
            time.sleep(0.2)

    ok_n = sum(1 for r in results if r["ok"])
    print(f"  → Done: {ok_n}/{len(results)}\n")
    return jsonify(results)


@app.route("/health")
def health():
    import sys
    return jsonify({
        "status":       "ok",
        "time":         datetime.now().isoformat(),
        "python":       sys.version,
        "github_ready": bool(GITHUB_TOKEN and GITHUB_REPO),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
