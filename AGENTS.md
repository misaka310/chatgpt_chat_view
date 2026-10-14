# Repository instructions

このリポジトリを変更する前に、利用者向け仕様として`README.md`と`docs/`の関連文書を確認してください。個人用エクスポートや生成物を公開ツリーへ追加しないでください。

## 仕様の正本

- 仕様の正本: `README.md`
- 実装前に意図する仕様を正本へ反映し、仕様変更時は同じ変更で正本と検証を更新する。

## 公開データ境界

- `input/`、`output/`、Sitesの生成データはGit管理対象外です。
- 実会話のタイトル、本文、ID、入力パス、個人用HTML/JSON/CSVをテスト fixture 以外へ含めません。
- Sitesへ渡すデータは許可リスト方式で生成し、公開前に`python scripts/verify_sites_public.py`を実行します。
- ネストしたGitリポジトリや、ルートに定義されていないファイルを追加しません。

## 検証

変更に近いテストに加え、次を実行します。

```powershell
python -m unittest discover -s tests -v
python scripts/build_sample_output.py
python scripts/verify_sites_public.py --artifact-root sites/usage-dashboard/dist
```

仕様、実装、テスト、公開安全文書が一致するまで完了扱いにしません。
