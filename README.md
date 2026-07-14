# ChatGPT Export Usage Dashboard

ChatGPT のエクスポートを外部送信せずにローカルで集計し、月別・日別の送信数や、連続3時間の送信数候補をブラウザで確認できる Windows 向けツールです。

![Synthetic dashboard sample](docs/images/dashboard.png)

[合成データの公開デモを見る](https://misaka310.github.io/chatgpt_chat_view/)

## できること

- 月別・日別のユーザー送信数を確認
- 推定トークン数を確認
- 任意の連続3時間で送信数が多かった時間帯を確認
- `chat.html`、`conversations.json`、`conversations-*.json`を解析
- 大きなJSONをチャンク単位で読み込み、重複メッセージを除外

## 必要環境

- Windows 11
- Python 3.11
- Chromium系ブラウザで動作確認済み
- GPU、外部API、ChatGPTアカウントは不要

初回セットアップ時は、Pythonパッケージの取得にインターネット接続が必要です。会話エクスポート自体は外部送信しません。

## 使い方

### 1. セットアップ

```powershell
git clone https://github.com/misaka310/chatgpt_chat_view.git
cd chatgpt_chat_view
.\setup.bat
```

Gitを使用しない場合は、GitHubの **Download ZIP** から取得できます。

### 2. エクスポートを配置

`input`フォルダに、次のいずれかを置きます。

```text
input/chat.html
input/conversations.json
input/conversations-*.json
```

### 3. 解析して表示

```powershell
.\run_analyze.bat
.\run_front.bat
```

通常は次のURLが開きます。

```text
http://127.0.0.1:8733/dashboard.html
```

## 画面

- `dashboard.html`: 月別・日別の送信数と推定トークン数
- `gpt_3h_limit.html`: 連続3時間で送信数が多かった時間帯

両画面はリンクで相互に移動できます。

## 制限事項

- 送信数とトークン数はChatGPT公式の利用量ではなく、エクスポート内容からの推定です。
- モデル別利用量、Thinking、添付、ツール利用は正確に分離できません。
- ChatGPTのエクスポート形式が変わると、解析できなくなる可能性があります。
- 生成したHTML、JSON、CSVには会話タイトルなどが残る場合があります。第三者へ共有する前に内容を確認してください。

## プライバシーと安全性

解析はローカルで行い、表示サーバーは`127.0.0.1`だけで待ち受けます。

詳細:

- [PRIVACY.md](PRIVACY.md)
- [SECURITY.md](SECURITY.md)

## 大規模入力

10万メッセージの合成データによる計測結果は、[docs/BENCHMARKS.md](docs/BENCHMARKS.md)に記載しています。

## ライセンス

MIT
