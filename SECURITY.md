# Security Policy

## Scope and data handling

このツールは ChatGPT 会話エクスポートという機密性の高いデータを扱います。通常の解析処理は外部へデータを送信しません。個人用表示の HTTP サーバーは `127.0.0.1` にだけバインドします。

ただし、入力はローカルで実行される Python によって解析されます。悪意がある、破損している、または信頼できないエクスポートを入力しないでください。

生のエクスポートと、個人用に生成された HTML / JSON / CSV を Git に追加してはいけません。生成物にはタイトルなど会話由来の情報が残ることがあります。個人用生成 HTML を第三者に公開・送付しないでください。

`sites/usage-dashboard` は別の公開専用ルートです。実集計JSONとビルド結果はGit管理外で、許可リスト方式の生成処理と `scripts/verify_sites_public.py` の両方に合格した成果物だけをChatGPT Sitesへ配置します。Sites成果物へ会話本文、タイトル、識別子、入力名、ローカルパス、ログ、認証情報を含めてはいけません。

ChatGPT Sitesを利用する場合、許可された匿名集計値はリモート表示のためSitesへ送信されます。共有設定は利用者自身で決める必要があります。本リポジトリの個人用運用では、所有者だけを許可し、ユーザー・グループ・外部訪問者を追加しない構成を前提とします。

日常的なデータ取り扱いと公開前確認は [PRIVACY.md](PRIVACY.md) に記載しています。この文書は脆弱性報告と安全な利用上の境界を扱います。

## Supported versions

セキュリティ修正は `main` ブランチの最新コミットに対して行います。過去のコミット、fork、ローカルで改変した版は対象外です。

## Reporting a vulnerability

脆弱性は公開Issueへ詳細を書かず、GitHubのPrivate Vulnerability Reportingを使用してください。

- 非公開報告: https://github.com/misaka310/chatgpt_chat_view/security/advisories/new
- Security overview: https://github.com/misaka310/chatgpt_chat_view/security

利用できない場合は、公開Issueにエクスポート、生成物、個人情報、認証情報、攻撃手順、再現データを投稿しないでください。公開Issueには「非公開連絡手段が必要」であることだけを書いてください。

報告には、影響するcommit、再現条件、期待した挙動と実際の挙動、影響範囲、合成データだけを使った最小再現を含めてください。

## Response and disclosure

- 受領後できるだけ早く再現可否と影響範囲を確認します。
- 修正が必要な場合は、再現テストを追加してから修正し、`main` へ反映します。
- 修正公開前に攻撃手順や実データを公開しないでください。公開時期は報告者と調整します。
- 影響が確認できなかった場合も、判断理由をPrivate Vulnerability Reporting上で返します。
