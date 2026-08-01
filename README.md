# ChatGPT Export Usage Dashboard

[![CI](https://github.com/misaka310/chatgpt_chat_view/actions/workflows/ci.yml/badge.svg)](https://github.com/misaka310/chatgpt_chat_view/actions/workflows/ci.yml)
[![Pages](https://github.com/misaka310/chatgpt_chat_view/actions/workflows/pages.yml/badge.svg)](https://github.com/misaka310/chatgpt_chat_view/actions/workflows/pages.yml)

ChatGPTのデータエクスポートを外部送信せず、ローカルで集計するWindows向けツールです。月別・日別の送信数、推定トークン数、連続3時間の送信数候補をブラウザで確認できます。

> **非公式・非提携について**
> このプロジェクトは独立して開発された非公式ツールであり、OpenAIの公式製品、提携製品、承認製品、スポンサー製品ではありません。ChatGPT、OpenAIおよび関連する名称・商標は各権利者に帰属します。

![Synthetic dashboard sample](docs/images/dashboard.png)

公開デモ: `https://misaka310.github.io/chatgpt_chat_view/`（合成データのみ）

## 必要環境

- Windows 11
- Python 3.11
- Chromium系ブラウザ
- 初回セットアップ時のみインターネット接続

GPU、外部API、ChatGPTへのログインは不要です。会話エクスポート自体は外部送信しません。

## 使い方

1. ChatGPTのエクスポートを `input` フォルダへ置きます。
2. `start.bat` をダブルクリックします。
3. 必要な解析が終わると、ダッシュボードがブラウザで開きます。

対応する入力は次のいずれかです。

```text
input/chat.html
input/conversations.json
input/conversations-*.json
```

初回だけ、`start.bat` が仮想環境の作成と依存関係のインストールを自動で行います。ダッシュボードを表示している間はローカルHTTPサーバー用のコマンドウィンドウを開いたままにし、使い終わったら閉じてください。

## 再解析を省略する仕組み

`start.bat` は入力ファイルのSHA-256と解析処理の内容を記録します。入力と解析処理が前回と同一で、必要な出力が揃っている場合は再解析せず、既存のダッシュボードをそのまま開きます。

再解析が行われる条件:

- 入力ファイルの内容または構成が変わった
- 解析コードやHTMLテンプレートが変わった
- 必要な出力ファイルが不足している
- 初回実行

手動で必ず再解析する場合:

```powershell
.\.venv\Scripts\python.exe scripts\start_dashboard.py --force
```

## 出力

主な表示先は `output/dashboard.html` です。ブラウザ表示には `127.0.0.1` のローカルHTTPサーバーを使います。

主な生成物:

- `output/dashboard.html`
- `output/gpt_3h_limit.html`
- `output/dashboard_summary.json`
- `output/dashboard_daily.json`
- `output/*.csv`

## 制限事項と安全性

- 送信数やトークン数はChatGPT公式の利用量ではなく、エクスポート内容からの推定です。
- モデル別利用量、Thinking、添付、ツール利用は正確に分離できません。
- `input` と `output` はGit管理対象外です。
- 生成物には会話タイトルなどが残る場合があります。第三者へ共有する前に内容を確認してください。

詳細は [PRIVACY.md](PRIVACY.md) と [SECURITY.md](SECURITY.md) を参照してください。

## 開発と検証

```powershell
python -m unittest discover -s tests -v
python scripts/build_sample_output.py
python scripts/benchmark_large_export.py --messages 100 --report-file .\benchmark-smoke.json
```

CIは解析CLI、重複除外、集計結果、公開成果物、ループバック限定サーバー、実会話データや秘密情報の混入防止を検証します。

実装は `src/`、補助処理は `scripts/`、表示素材は `assets/` に配置しています。通常利用時にルートで操作するのは `start.bat` だけです。

## ライセンス

MIT
