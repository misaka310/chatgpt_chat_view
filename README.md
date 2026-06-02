# ChatGPT エクスポート解析ツール

このリポジトリは、ChatGPT エクスポートと Codex ローカルログを解析して、ローカルで確認できる集計ファイルを作るためのものです。

## 安全ポリシー

- 生の ChatGPT エクスポートは Git にコミットしません。
- 解析で生成される大きな成果物も、原則 Git 管理対象にしません。
- 参照するのはソースコードと `docs/` の説明です。

## 使い方

1. 解析したいエクスポートをリポジトリ直下に置きます。
   - `chat.html`
   - `conversations.json`
   - `conversations-*.json`
2. 解析を実行します。

```powershell
python .\analyze_chat_export.py --input-dir . --output-dir . --timezone Asia/Tokyo --rebuild
```

3. `dashboard.html` は `fetch()` で JSON を読むため、ローカルHTTPサーバー経由で開きます。

```powershell
python -m http.server 8733
```

4. ブラウザで次を開きます。

```text
http://localhost:8733/dashboard.html
```

## 生成ファイル

### ダッシュボード

- `dashboard.html`
- `dashboard_summary.json`
- `dashboard_conversations.json`
- `dashboard_daily.json`
- `dashboard_categories.json`
- `dashboard_codex_match.json`

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
- 全体サマリーだけ見たいときは `dashboard_summary.json` が元データです。
- 会話一覧を見たいときは `dashboard_conversations.json` を `dashboard.html` から読み込みます。
- 日別詳細は `dashboard_daily.json`、カテゴリとキーワードは `dashboard_categories.json`、Codex 照合は `dashboard_codex_match.json` です。
- `parsed_summary.json` と CSV 群は互換用の集計結果なので、通常は直接見る必要はありません。

## 補足

- 生成ファイルは `.gitignore` で除外しています。
- ローカルHTTPサーバーで開かずに `dashboard.html` を直接開くと、JSON の読み込みに失敗することがあります。
- 詳しい読み方は [`docs/dashboard_guide.md`](/C:/33_chatgpt_chat_view/docs/dashboard_guide.md) を参照してください。

## テスト

```powershell
python -m unittest tests.test_analyze_chat_export
```
