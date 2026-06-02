# ChatGPT Export Dashboard

このリポジトリは、ChatGPT エクスポートと Codex ローカルログを解析して、ローカルで使うダッシュボードと集計ファイルを生成します。

## まず開くファイル

- `dashboard.html`

`dashboard.html` は軽量なUIシェルです。初期表示では `dashboard_summary.json` だけを読み込み、会話一覧や Codex 照合などの重い詳細はボタンを押した時だけ読み込みます。

## 開き方

`dashboard.html` は `fetch()` で JSON を読むため、ローカルHTTPサーバー経由で開く必要があります。

```powershell
python -m http.server 8733
```

その後、ブラウザで次を開きます。

```text
http://localhost:8733/dashboard.html
```

## 生成ファイル

- `dashboard_summary.json`
- `dashboard_conversations.json`
- `dashboard_daily.json`
- `dashboard_categories.json`
- `dashboard_codex_match.json`
- `parsed_summary.json`
- `monthly_summary.md`
- `*.csv`
- `out/`

## 見なくてよいファイル

- `parsed_summary.json` は互換用の完全版です。
- CSV 群と `out/` は検証や再利用向けです。
- 普段の確認は `dashboard.html` だけで足ります。
