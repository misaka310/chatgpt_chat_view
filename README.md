# ChatGPT Export Usage Dashboard

ChatGPT のエクスポートをローカルで解析し、送信回数・日別推移・3時間160送信チェックをブラウザで確認するためのダッシュボードです。

生データは外部送信しません。解析は手元のPCだけで実行します。

## スクリーンショット

![Dashboard sample](docs/images/dashboard.png)

## できること

- 月ごとのChatGPT送信回数を確認
- 選択した月の日別送信回数を確認
- 任意の連続3時間で160送信に近づいたかを確認

3時間160チェックは、Plus / Go などで時間あたりの利用制限があるため、エクスポート上の送信履歴から「制限に近い使い方をしていた可能性」を見るための目安です。

これは公式のモデル別利用量ではありません。モデル種別、Thinking、添付、ツール利用などが混ざる可能性があります。

## 最短手順 Windows / PowerShell

```powershell
git clone https://github.com/misaka310/chatgpt_chat_view.git
cd chatgpt_chat_view
.\setup.bat
.\run_analyze.bat
.\run_front.bat
```

## 入力ファイル

`input/` に次のどれか1種類を置きます。

```text
input/chat.html
input/conversations.json
input/conversations-*.json
```

その後、解析と表示を実行します。

```powershell
.\run_analyze.bat
.\run_front.bat
```

ブラウザが自動で開かない場合は、PowerShell に表示されるURLを開いてください。

```text
http://127.0.0.1:8733/dashboard.html
```

## 画面

- `dashboard.html`: 月別・日別の送信回数ダッシュボード
- `gpt_3h_limit.html`: 任意の連続3時間で160送信に到達・超過した候補の確認

`dashboard.html` から `gpt_3h_limit.html` に移動できます。

## プライバシー

生のエクスポートと生成物は `.gitignore` で除外しています。

公開前に確認してください。

```powershell
git status --ignored
```

関連ドキュメント:

- [`PRIVACY.md`](PRIVACY.md)
- [`docs/release_checklist.md`](docs/release_checklist.md)

## テスト

```powershell
python -m unittest
```

## ライセンス

MIT
