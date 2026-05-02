# Dashboard Guide

`dashboard.html` は、ChatGPT export と Codex ログの活動量を「読むための画面」です。

## 用語
- 会話スレッド: ChatGPT の conversation 単位
- Codexセッション: `rollout-*.jsonl` 単位
- プロンプト数: user が送った入力数
- メッセージ数: user / assistant / tool / system を含む総数

## 見る順番
1. 全体サマリーで全期間の傾向を見る
2. 2026年4月カードで対象月の利用量を見る
3. 月別サマリーで重い月を特定する
4. 会話スレッド一覧で重い会話を掘る
5. Codex突合で ChatGPT 作成プロンプトと Codex 実投入の一致状況を確認する

## 注意
- 推定トークンはローカル概算値です
- OpenAI の課金トークンや公式利用量とは一致しません
