# ChatGPT エクスポート分析ツール

このリポジトリは、ChatGPT エクスポート（`conversations.json` / `conversations-*.json` / `chat.html`）をローカルで再解析し、ダッシュボードとCSVを生成するためのものです。

## 安全ポリシー

- 生のChatGPTエクスポートはGitにコミットしません。
- 生成物（`parsed_summary.json` / `dashboard.html` / `*.csv` など）も原則コミットしません。
- `.gitignore` の方針を維持してください。

## 新しいエクスポート追加手順（Windows）

1. エクスポートファイルをリポジトリ直下（`C:\33_chatgpt_chat_view`）に置きます。  
   対象は `conversations.json` または `conversations-*.json` または `chat.html` です。
2. 基本運用は「既存ファイル置き換え」です。  
   以前の `conversations.json` や `chat.html` を新しいものに入れ替えて再実行してください。
3. `conversations-*.json` を複数置く場合は、重複会話・重複メッセージが混ざる可能性があります。  
   本ツールは `conversation_id` と `message.id`（欠損時はフォールバック署名）で重複排除して二重集計を防ぎます。
4. 解析を実行します。

```powershell
python .\analyze_chat_export.py --input-dir . --output-dir . --timezone Asia/Tokyo --rebuild
```

5. `dashboard.html` をブラウザで開いて確認します。

```powershell
start .\dashboard.html
```

## 入力ファイル優先順

1. `conversations-*.json`（複数）
2. `conversations.json`
3. `chat.html`

## 生成される主なファイル

- `parsed_summary.json`
- `dashboard.html`
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
- `monthly_summary.md`

## 重複排除仕様

- 優先キー: `conversation_id + message.id`
- `message.id` がない場合: `conversation_id + hash(role,timestamp,text,recipient)` を使用
- 同一キーは1回のみ集計します。
- これにより `conversations-*.json` の複数入力時でも数値が膨らまないようにしています。

## カテゴリ分類ルール

- ルールファイル: `rules/category_keywords.json`
- 会話ごとにキーワード辞書方式で `inferred_category` を付与します。
- ルールを編集した場合は `--rebuild` で再解析してください。

## ダッシュボードでできること

- 会話一覧テーブルの表示
- タイトル検索
- 年月フィルタ
- カテゴリフィルタ
- メッセージ数順 / 最終更新日順のソート
- 日別の上位会話から対象会話へジャンプ

## サンプルデータでの検証

- ダミーサンプル: `tests/fixtures/conversations.sample.json`
- 重複会話・重複 `message.id`・`message.id` なし重複ケースを含みます。
- テスト実行:

```powershell
python -m unittest tests.test_analyze_chat_export
```
