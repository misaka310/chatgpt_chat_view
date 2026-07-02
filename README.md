# ChatGPT エクスポート解析ツール

このリポジトリは、ChatGPT エクスポートを解析して、月ごとの送信回数と選択月の日別送信回数をローカルで確認できる集計ファイルを作るためのものです。

## 安全ポリシー

- 生の ChatGPT エクスポートは Git にコミットしません。
- 解析で生成される大きな成果物も、原則 Git 管理対象にしません。
- 参照するのはソースコードと `docs/` の説明です。

## 使い方

1. 解析したいエクスポートをリポジトリ直下に置きます。
   - `chat.html`
   - `conversations.json`
   - `conversations-*.json`
2. 通常の送信回数ダッシュボードを生成します。

```powershell
python .\analyze_chat_export.py --input-dir . --output-dir . --timezone Asia/Tokyo --rebuild
```

3. 3時間160送信の超過候補も確認したい場合は、追加で実行します。

```powershell
python .\analyze_gpt_3h_limit.py --input-dir . --output-dir . --timezone Asia/Tokyo --threshold 160 --window-hours 3
```

4. `analyze_chat_export.py` が `dashboard.template.html` から `dashboard.html` を生成するので、恒久的なUI変更はこの生成元を直します。`dashboard.html` は `fetch()` で JSON を読むため、ローカルHTTPサーバー経由で開きます。

```powershell
python -m http.server 8733
```

5. ブラウザで次を開きます。

```text
http://localhost:8733/dashboard.html
```

## 3時間160送信チェック

`analyze_gpt_3h_limit.py` は、ChatGPTエクスポート内の `author.role == user` の送信時刻を並べ、任意の連続3時間に160送信へ到達・超過した候補があるかを集計します。

見るべきファイルは `gpt_3h_limit_summary.md` です。JSONで見たい場合は `gpt_3h_limit_summary.json` を見ます。

注意点:

- これは公式のモデル別利用量ではありません。
- ChatGPTエクスポート上のユーザー送信を数えるため、GPT-5.5以外、Thinking、添付、ツール利用などが混ざる可能性があります。
- そのため、結果は「公式制限を確実に超えた証拠」ではなく「160/3hを超えた可能性の確認」です。
- `reached_threshold` は160ちょうどを含みます。
- `exceeded_threshold` は161以上です。

## 生成ファイル

### ダッシュボード

- `dashboard.html`
- `dashboard_summary.json`
- `dashboard_conversations.json`
- `dashboard_daily.json`
- `dashboard_categories.json`
- `dashboard_codex_match.json`

### 3時間160送信チェック

- `gpt_3h_limit_summary.md`
- `gpt_3h_limit_summary.json`
- `gpt_3h_limit_monthly.csv`
- `gpt_3h_limit_daily.csv`
- `gpt_3h_limit_windows.csv`

### 既存の集計

- `parsed_summary.json`
- `monthly_summary.md`
- `conversations_index.csv`
- `category_monthly.csv`
- `category_daily.csv`
- `keywords_monthly.csv`
- `monthly_user_messages.csv`
- `monthly_conversations.csv`
- `monthly_active_days.csv`
- `daily_user_messages.csv`
- `daily_hourly_user_messages.csv`
- `daily_conversations.csv`
- `out/`

## どのファイルを見るか

- まず見るのは `dashboard.html` です。
- 3時間160送信の到達・超過候補は `gpt_3h_limit_summary.md` です。
- 全体サマリーだけ見たいときは `dashboard_summary.json` が元データです。
- `dashboard.html` は、月ごとの送信回数の推移、選択月サマリー、月別一覧、選択月の日別送信回数を中心に表示します。表示内容は `analyze_chat_export.py` と `dashboard.template.html` から再生成されます。
- 月別一覧で月を選ぶと、その月のサマリーと日別推移が連動します。
- 日別の元データは `dashboard_daily.json` で、日別推移の棒グラフは `daily.user_messages` を使います。
- `dashboard_conversations.json`、`dashboard_categories.json`、`dashboard_codex_match.json` は補助データで、主画面の中心には置いていません。
- `parsed_summary.json` と CSV 群は互換用の集計結果なので、通常は直接見る必要はありません。

## 補足

- 生成ファイルは `.gitignore` で除外しています。
- ローカルHTTPサーバーで開かずに `dashboard.html` を直接開くと、JSON の読み込みに失敗することがあります。
- 詳しい読み方は [`docs/dashboard_guide.md`](docs/dashboard_guide.md) を参照してください。

## テスト

```powershell
python -m unittest tests.test_analyze_chat_export tests.test_analyze_gpt_3h_limit
```
