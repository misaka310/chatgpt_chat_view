# ChatGPT Export Usage Dashboard

[![CI](https://github.com/misaka310/chatgpt_chat_view/actions/workflows/ci.yml/badge.svg)](https://github.com/misaka310/chatgpt_chat_view/actions/workflows/ci.yml)
[![Pages](https://github.com/misaka310/chatgpt_chat_view/actions/workflows/pages.yml/badge.svg)](https://github.com/misaka310/chatgpt_chat_view/actions/workflows/pages.yml)

ChatGPTのデータエクスポートを外部送信せず、ローカルで集計するWindows向けツールです。月別・日別の送信数、全件・音声除外・音声のみの内訳、推定トークン数、連続3時間の送信数候補をブラウザで確認できます。

> **非公式・非提携について**
> このプロジェクトは独立して開発された非公式ツールであり、OpenAIの公式製品、提携製品、承認製品、スポンサー製品ではありません。ChatGPT、OpenAIおよび関連する名称・商標は各権利者に帰属します。

![Synthetic dashboard sample](docs/images/dashboard.png)

公開デモ: [合成データ版を開く](https://misaka310.github.io/chatgpt_chat_view/)

## 入手方法

```powershell
git clone https://github.com/misaka310/chatgpt_chat_view.git
cd chatgpt_chat_view
```

Gitを使わない場合は、GitHubの **Code → Download ZIP** から取得して展開できます。

## 必要環境

- Windows 11
- Python 3.11
- Chromium系ブラウザ
- Node.js 22.13以降（ChatGPT Sites用フロントを使う場合）
- 初回セットアップ時のみインターネット接続

GPU、外部API、ChatGPTへのログインは不要です。会話エクスポート自体は外部送信しません。

## 使い方

1. ChatGPTのエクスポートを `input` フォルダへ置きます。
2. `start.bat` をダブルクリックします。
3. 必要な解析が終わると、個人用の詳細ダッシュボードがブラウザで開きます。

対応する入力は次のいずれかです。

```text
input/chat.html
input/conversations.json
input/conversations-*.json
```

初回だけ、`start.bat` が仮想環境の作成と依存関係のインストールを自動で行います。ダッシュボードを表示している間はローカルHTTPサーバー用のコマンドウィンドウを開いたままにし、使い終わったら閉じてください。

### ChatGPT Sites用の集計フロント

`start_sites.bat` をダブルクリックすると、通常のローカル解析に続いて次を実行します。

1. `output` の詳細結果から、許可した数値だけの本文を含まない集計を生成
2. 公開物のファイル許可リスト、JSONスキーマ、禁止文字列、既知の会話タイトル・ID・入力パスの混入を検査
3. `sites/usage-dashboard` をビルドし、生成後の配布物も再検査
4. 検査済みのローカルプレビューを開く

実集計データ `sites/usage-dashboard/public/usage-data.json`、Sitesのビルド結果、入力、個人用詳細出力はすべてGit管理対象外です。`sites/usage-dashboard` がこのリポジトリ内で唯一のSitesデプロイルートです。

**公開範囲はリポジトリでは決まりません。** Sitesの公開／Share画面で、利用可能な最も狭い対象（所有者・ワークスペース管理者のみ、または自分のアカウントのみ）を明示的に選び、公開後は未ログインのプライベートウィンドウから開けないことを確認してください。必要な非公開範囲を選べない場合はデプロイしないでください。

## 再解析を省略する仕組み

`start.bat` と `start_sites.bat` は入力ファイルのSHA-256と解析処理の内容を記録します。入力と解析処理が前回と同一で、必要な出力が揃っている場合は再解析しません。Sites用のソースと本文を含まない集計も同一なら、既存の検査済みビルドを再利用します。

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

個人用詳細画面の主な表示先は `output/dashboard.html` です。ブラウザ表示には `127.0.0.1` のローカルHTTPサーバーを使います。

主な個人用生成物:

- `output/dashboard.html`
- `output/gpt_3h_limit.html`
- `output/dashboard_summary.json`
- `output/dashboard_daily.json`
- `output/*_by_mode.csv`（全件・音声除外・音声のみ）
- `output/*.csv`

Sites用の実集計JSONは `sites/usage-dashboard/public/usage-data.json` に生成されます。このファイルはGit管理対象外で、月・日・送信回数・活動日数・会話数・推定トークン数・集計時刻だけを保持します。

## 制限事項と安全性

- 送信数やトークン数はChatGPT公式の利用量ではなく、エクスポート内容からの推定です。
- モデル別利用量、Thinking、添付、ツール利用は正確に分離できません。
- 音声判定はエクスポート内のGPT Live／双方向音声メタデータと音声文字起こし情報に基づきます。履歴に保存されない音声会話は集計できません。
- `input` と `output` はGit管理対象外です。
- 個人用生成物には会話タイトルなどが残る場合があります。第三者へ共有しないでください。
- Sites用フロントには個人用詳細画面へのリンクを設けず、外部APIや外部アセットも使用しません。
- Sitesへ配置する前に `python scripts/verify_sites_public.py --artifact-root sites/usage-dashboard/dist` を実行し、検査に合格した成果物だけを使用してください。

詳細は [PRIVACY.md](PRIVACY.md) と [SECURITY.md](SECURITY.md) を参照してください。

## 開発と検証

```powershell
python -m unittest discover -s tests -v
python scripts/build_sample_output.py
python scripts/benchmark_large_export.py --messages 100 --report-file .\benchmark-smoke.json
python scripts/start_sites_dashboard.py --no-open
cd sites\usage-dashboard
npm test
```

CIは解析CLI、重複除外、集計結果、合成データでのSitesビルド、公開成果物、ループバック限定サーバー、実会話データや秘密情報の混入防止を検証します。

実装は `src/`、補助処理は `scripts/`、表示素材は `assets/`、Sites専用フロントは `sites/usage-dashboard/` に配置しています。個人用詳細画面は `start.bat`、Sites用の本文を含まない集計画面は `start_sites.bat` から起動します。

## ライセンス

MIT
