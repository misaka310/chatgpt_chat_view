# ChatGPT Export Dashboard

このリポジトリは、ChatGPT エクスポートをローカルで解析して、送信回数・日別推移・3時間160送信チェックをブラウザで確認するためのダッシュボードを生成します。

## 使うbat

- `run_analyze.bat`: `input/` の実データを解析して `output/` を作ります。
- `run_front.bat`: フロントを開きます。`output/` があれば実データ、なければサンプルを開きます。

## 開き方

```powershell
.\setup.bat
.\run_analyze.bat
.\run_front.bat
```

## まず開くファイル

- `output/index.html`

`run_front.bat` がローカルサーバーを起動してブラウザで開きます。

## 生成ファイル

- `output/index.html`
- `output/dashboard.html`
- `output/gpt_3h_limit.html`
- `output/dashboard_summary.json`
- `output/dashboard_daily.json`
- `output/gpt_3h_limit_summary.json`
- `output/*.csv`

## 見なくてよいファイル

- `parsed_summary.json` は互換用の完全版です。
- CSV 群は検証や再利用向けです。
- 普段の確認は `output/index.html` だけで足ります。
