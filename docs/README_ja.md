# ChatGPT Export Dashboard

ChatGPTエクスポートをローカルで解析し、送信回数・日別推移・連続3時間の送信数候補をブラウザで確認するダッシュボードです。

## 通常の使い方

1. `input/` に `chat.html`、`conversations.json`、または `conversations-*.json` を置きます。
2. ルートの `start.bat` をダブルクリックします。
3. 入力が前回から変わっていれば解析し、変わっていなければ既存結果を再利用してブラウザを開きます。

初回は `start.bat` が `setup.bat` を呼び、仮想環境と依存関係を準備します。

## 主な出力

- `output/dashboard.html`
- `output/gpt_3h_limit.html`
- `output/dashboard_summary.json`
- `output/dashboard_daily.json`
- `output/*.csv`

通常利用では `output` 内を直接操作する必要はありません。
