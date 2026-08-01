# Repository Layout

## Root

通常のローカル集計は `start.bat`、Sites用の安全な集計・プレビューは `start_sites.bat` が入口です。README、ライセンス、プライバシー／セキュリティ文書、依存関係定義以外の実装ファイルはルートに置きません。

## Directories

- `input/`: ユーザーがChatGPTエクスポートを置く場所。実データはGit管理外。
- `output/`: 解析結果と再解析判定状態。Git管理外。
- `src/`: 解析処理とHTMLテンプレート。
- `scripts/`: 起動、初回セットアップ、補助処理、ベンチマーク。
- `assets/`: faviconなどの静的素材。
- `tests/`: 自動テスト。
- `docs/`: 補足文書。
- `sites/usage-dashboard/`: ChatGPT Sites向けフロント。親リポの一部として管理し、入れ子Gitリポジトリにはしません。

## Public Safety

- 生のエクスポートと生成されたHTML／JSON／CSVはコミットしません。
- `input/.keep` だけを追跡します。
- Sitesへ渡す `usage-data.json` はGit管理外で、月日と数値だけを許可リスト方式で生成します。
- Sitesのソースとビルド成果物は `scripts/verify_sites_public.py` で漏えい検査します。
- 公開前に `python -m unittest` と Sites側のテストを実行します。
