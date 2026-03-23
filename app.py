"""
JP Portfolio Monitor — Alpha Vantage 版
=========================================
Alpha Vantage GLOBAL_QUOTE API で日本株を取得。
無料プラン: 1日25콜, 1分5콜

★ 25콜制限の対策:
  - 15銘柄を3グループ(各5銘柄)に分割
  - 1回の更新で5銘柄を取得(5콜消費)
  - 3回更新で全15銘柄をカバー
  - サーバーメモリにキャッシュ → 前回取得値を保持

環境変数 (Render ダッシュボードで設定):
  AV_API_KEY   : Alpha Vantage API キー ← 必須
  GITHUB_TOKEN : GitHub Personal Access Token
  GITHUB_REPO  : "ユーザー名/リポジトリ名"
  GITHUB_BRANCH: ブランチ名 (デフォルト: main)
"""

import os, json, base64, time, requests
from flask import Flask, jsonify, request, send_from_directory
from datetime import datetime

app = Flask(__name__, static_folder="static")

AV_API_KEY    = os.environ.get("AV_API_KEY", "")
GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO   = os.environ.get("GITHUB_REPO", "")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
PORTFOLIO_FILE = "portfolio.json"

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

# ── サーバーメモリキャッシュ ──────────────────────────────
# {code: {price, prev, change, pct, volume, date, ok, fetched_at}}
CACHE = {}

# 現在のグループインデックス (0,1,2 を順番に)
GROUP_INDEX = [0]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "jp-portfolio/1.0"})


# ════════════════════════════════════════════════════════
# Alpha Vantage GLOBAL_QUOTE
# ════════════════════════════════════════════════════════

def fetch_one_av(code: str) -> dict:
    """
    Alpha Vantage GLOBAL_QUOTE で1銘柄取得。
    日本株シンボル形式: コード.TYO (例: 7741.TYO)
    """
    symbol = f"{code}.TYO"
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "GLOBAL_QUOTE",
        "symbol":   symbol,
        "apikey":   AV_API_KEY,
    }
    try:
        r = SESSION.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # レート制限チェック
    if "Note" in data or "Information" in data:
        msg = data.get("Note") or data.get("Information", "rate limit")
        return {"ok": False, "error": f"rate_limit: {msg[:80]}"}

    gq = data.get("Global Quote", {})
    if not gq or not gq.get("05. price"):
        return {"ok": False, "error": "no data"}

    try:
        price  = float(gq["05. price"])
        prev   = float(gq["08. previous close"])
        chg    = float(gq["09. change"])
        pct    = float(gq["10. change percent"].replace("%", ""))
        vol    = int(gq.get("06. volume", 0) or 0)
        date   = gq.get("07. latest trading day", "")
        return {
            "ok":     True,
            "price":  round(price),
            "prev":   round(prev),
            "change": round(chg),
            "pct":    round(pct, 2),
            "volume": vol,
            "date":   date,
            "fetched_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"ok": False, "error": f"parse: {e}"}


def fetch_group(portfolio: list, group_idx: int) -> dict:
    """
    portfolioを3グループに分け、group_idxのグループのみ取得。
    5銘柄 × 12秒間隔 = 最大60秒 (分5콜制限対策)
    残りはキャッシュから返す。
    """
    n = len(portfolio)
    size = max(1, (n + 2) // 3)   # 3等分の切り上げ
    start = group_idx * size
    end   = min(start + size, n)
    target_codes = {s["code"] for s in portfolio[start:end]}

    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] Alpha Vantage グループ {group_idx+1}/3 "
          f"({start+1}〜{end}番目, {len(target_codes)}銘柄) 取得中...")

    results = {}
    for stock in portfolio:
        code = stock["code"]
        if code in target_codes:
            # 新規取得
            d = fetch_one_av(code)
            CACHE[code] = {**d, "meta": stock}

            if d["ok"]:
                sign = "+" if d["change"] >= 0 else ""
                print(f"  ✓ {code} {stock['ja']:<14} "
                      f"¥{d['price']:>8,}  ({sign}{d['pct']:.2f}%)  {d['date']}")
            else:
                print(f"  ✗ {code} {stock['ja']:<14} {d.get('error','')}")
                # rate_limit なら即停止
                if "rate_limit" in d.get("error", ""):
                    print("  ⚠ Rate limit 検出 — 取得を停止します")
                    break

            # 分5콜制限: 12秒待機
            time.sleep(12)
        else:
            # キャッシュから
            if code in CACHE:
                print(f"  ○ {code} {stock['ja']:<14} (キャッシュ)")

    ok_n = sum(1 for c in portfolio if CACHE.get(c["code"], {}).get("ok"))
    print(f"  → 取得済: {ok_n}/{len(portfolio)}\n")
    return CACHE


def build_results(portfolio: list) -> list:
    """キャッシュから全銘柄のレスポンスを構築"""
    results = []
    for stock in portfolio:
        code  = stock["code"]
        cache = CACHE.get(code, {})
        if cache.get("ok"):
            results.append({
                **stock,
                "price":  cache["price"],
                "prev":   cache["prev"],
                "change": cache["change"],
                "pct":    cache["pct"],
                "volume": cache["volume"],
                "date":   cache["date"],
                "ok":     True,
                "cached": cache.get("fetched_at", ""),
            })
        else:
            results.append({
                **stock,
                "price": 0, "prev": 0, "change": 0,
                "pct": 0, "volume": 0, "date": "", "ok": False,
                "error": cache.get("error", "未取得"),
            })
    return results


# ════════════════════════════════════════════════════════
# GitHub API
# ════════════════════════════════════════════════════════

def gh_headers():
    return {"Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"}

def github_get_file(filepath):
    url = (f"https://api.github.com/repos/{GITHUB_REPO}"
           f"/contents/{filepath}")
    r = requests.get(url, headers=gh_headers(),
                     params={"ref": GITHUB_BRANCH}, timeout=10)
    if r.status_code == 404:
        return None, None
    r.raise_for_status()
    d = r.json()
    return base64.b64decode(d["content"]).decode("utf-8"), d["sha"]

def github_put_file(filepath, content_str, sha=None,
                    message="Update portfolio"):
    url = (f"https://api.github.com/repos/{GITHUB_REPO}"
           f"/contents/{filepath}")
    payload = {
        "message": message,
        "content": base64.b64encode(
            content_str.encode("utf-8")).decode("utf-8"),
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    r = requests.put(url, headers=gh_headers(),
                     json=payload, timeout=10)
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
    """?code=9433 → 銘柄情報確認"""
    code = request.args.get("code", "").strip().zfill(4)
    if not code.isdigit() or len(code) != 4:
        return jsonify({"found": False,
                        "error": "4桁の数字で入力してください"}), 400
    if not AV_API_KEY:
        return jsonify({"found": False,
                        "error": "AV_API_KEY未設定"}), 500

    d = fetch_one_av(code)
    if not d["ok"]:
        return jsonify({"found": False, "error": d["error"]})
    return jsonify({
        "found":   True,
        "code":    code,
        "name_en": f"{code}.TYO",
        "price":   d["price"],
    })


@app.route("/api/portfolio", methods=["GET"])
def get_portfolio():
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
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return jsonify({"error": "GITHUB_TOKEN/GITHUB_REPO未設定"}), 500
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
    """
    グループ順に5銘柄ずつ取得 → 全体をキャッシュから返す。
    1日25콜制限のため:
      1回目の更新: グループ0 (5銘柄) を新規取得
      2回目の更新: グループ1 (5銘柄) を新規取得
      3回目の更新: グループ2 (5銘柄) を新規取得
      4回目〜: グループ0に戻る (ローテーション)
    """
    if not AV_API_KEY:
        return jsonify({"error":
            "AV_API_KEY が設定されていません。"
            "Renderの Environment タブで設定してください。"}), 500

    portfolio = request.json
    if not isinstance(portfolio, list) or not portfolio:
        return jsonify({"error": "銘柄リストが空です"}), 400

    # グループ取得 & インデックス進める
    gi = GROUP_INDEX[0]
    fetch_group(portfolio, gi)
    GROUP_INDEX[0] = (gi + 1) % 3

    results = build_results(portfolio)
    ok_n = sum(1 for r in results if r["ok"])
    next_gi = GROUP_INDEX[0]
    next_start = next_gi * max(1, (len(portfolio) + 2) // 3) + 1
    next_end   = min(next_start + max(1, (len(portfolio) + 2) // 3) - 1,
                     len(portfolio))

    print(f"  キャッシュ済: {ok_n}/{len(portfolio)}銘柄")
    print(f"  次回更新: グループ{next_gi+1} "
          f"({next_start}〜{next_end}番目)\n")

    return jsonify(results)


@app.route("/api/cache/clear", methods=["POST"])
def clear_cache():
    """デバッグ用: キャッシュクリア"""
    CACHE.clear()
    GROUP_INDEX[0] = 0
    return jsonify({"ok": True, "message": "キャッシュをクリアしました"})


@app.route("/health")
def health():
    import sys
    cached = sum(1 for v in CACHE.values() if v.get("ok"))
    return jsonify({
        "status":       "ok",
        "time":         datetime.now().isoformat(),
        "python":       sys.version,
        "av_ready":     bool(AV_API_KEY),
        "github_ready": bool(GITHUB_TOKEN and GITHUB_REPO),
        "cache":        f"{cached}/{len(CACHE)}銘柄キャッシュ済",
        "next_group":   f"グループ{GROUP_INDEX[0]+1}",
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
