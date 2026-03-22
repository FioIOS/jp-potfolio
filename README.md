# JP Portfolio Monitor

Yahoo Finance (yfinance) でリアルタイム株価を取得する  
日本株ポートフォリオダッシュボードです。

---

## デプロイ手順

### Step 1: GitHubにアップロード

1. https://github.com/new でリポジトリを作成
   - Repository name: `jp-portfolio`
   - Public または Private どちらでもOK
   - 「Create repository」をクリック

2. 次の画面で「uploading an existing file」をクリック

3. 以下のファイルをドラッグ&ドロップでアップロード:
   ```
   app.py
   requirements.txt
   Procfile
   static/index.html
   ```
   ※ static フォルダごとアップロードしてください

4. 「Commit changes」をクリック

---

### Step 2: Renderにデプロイ

1. https://render.com にアクセスし、無料アカウントを作成
   (GitHubアカウントでサインアップすると連携が楽です)

2. ダッシュボードで「New +」→「Web Service」をクリック

3. 「Connect a repository」でGitHubを連携し、
   `jp-portfolio` リポジトリを選択

4. 以下の設定を入力:
   | 項目 | 値 |
   |------|-----|
   | Name | jp-portfolio (任意) |
   | Runtime | Python 3 |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `gunicorn app:app --timeout 120 --workers 1` |
   | Instance Type | **Free** を選択 |

5. 「Create Web Service」をクリック

6. ビルドが完了すると URL が発行されます:
   `https://jp-portfolio-xxxx.onrender.com`

---

## ファイル構成

```
jp-portfolio/
├── app.py              ← Flaskサーバー (株価取得ロジック)
├── requirements.txt    ← 必要なパッケージ
├── Procfile            ← Renderの起動コマンド
├── static/
│   └── index.html      ← ダッシュボードUI
└── README.md           ← このファイル
```

---

## 注意事項

- Render無料プランは **15分間未使用でスリープ** します
- 次のアクセス時に自動復帰しますが **30〜60秒** かかります
- スリープ中はダッシュボードに「サーバー起動中...」と表示されます

---

## ローカル実行

```bash
pip install -r requirements.txt
python app.py
# → http://127.0.0.1:5000 で起動
```
