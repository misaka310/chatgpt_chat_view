# Dashboard Guide

`output/index.html` は、ChatGPTエクスポートの送信回数と3時間160送信チェックを見るための入口です。

## 読む順番

1. `output/index.html` を開きます。
2. まず「最新月の送信数」と「連続3時間の最大送信数」を見ます。
3. 月別・日別の送信回数を見たい場合は `dashboard.html` を開きます。
4. 3時間160送信の到達・超過候補を見たい場合は `gpt_3h_limit.html` を開きます。

## 画面の見方

- `dashboard.html` は `dashboard_summary.json` と `dashboard_daily.json` を読み込みます。
- `gpt_3h_limit.html` は3時間160送信チェックの結果を表示します。
- エラーは画面上またはPowerShellに出ます。

## 注意

- 公式のモデル別利用量ではなく、エクスポート上のユーザー送信数から作る候補値です。
- 直接HTMLを開くより、`run.bat` で起動したローカルサーバーから見るほうが安定します。
