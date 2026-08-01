# Repository Layout

## Root

通常利用の入口は `start.bat` だけです。README、ライセンス、プライバシー／セキュリティ文書、依存関係定義以外の実装ファイルはルートに置きません。

## Directories

- `input/`: ユーザーがChatGPTエクスポートを置く場所。実データはGit管理外。
- `output/`: 解析結果と再解析判定状態。Git管理外。
- `src/`: 解析処理とHTMLテンプレート。
- `scripts/`: 起動、初回セットアップ、補助処理、ベンチマーク。
- `assets/`: faviconなどの静的素材。
- `tests/`: 自動テスト。
- `docs/`: 補足文書。

## Public Safety

- 生のエクスポートと生成されたHTML／JSON／CSVはコミットしません。
- `input/.keep` だけを追跡します。
- 公開前に `python -m unittest` を実行します。
