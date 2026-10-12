# 麺処 松もり｜AI営業案内担当

**毎日09:00（JST）に、日付・曜日に応じた画像1枚付きの営業案内を、X / Instagram / Googleビジネスプロフィールへ自動投稿する仕組み。**

この一式は**設置用プログラム**です。ダウンロードしただけで自動投稿は始まりません。

## 通常の動作

1. GitHub Actionsが毎日**02:13（日本時間）**ごろ起動（GitHub側の遅延はあり得る）。
2. 当日の日付と曜日を確定：**水・土が営業、それ以外は定休日**。
3. 1080×1350のJPEGを明朝体で生成。営業日は淡く明るく、定休日は少し落ち着いた色味。
4. 公開GitHubリポジトリに**当日限定URL**の画像を保存。
5. Bufferの3つのSNSアカウントを自動識別し、**当日09:00 JST**を指定して画像付き投稿を予約。
6. 日付・本文・時間・画像が同じ既存投稿があれば重複しない。
7. 予約登録結果を `logs/YYYY-MM-DD.json` に記録。

**Googleビジネスプロフィールの投稿タイプ：最新情報（whats_new）**。実際に投稿・審査が完了したかはBufferのSent / Failed欄で確認してください。「予約できた」だけでは掲載成功を保証しません。

## 事前準備（必ず利用者自身が操作）

1. GitHubアカウントを作成：<https://github.com/signup>
2. `matsumori-ai-staff` という**Public**（公開）のリポジトリを作成する。公開されるのはコードと営業案内画像であり、**APIキーは含めない**。
3. このパッケージの**中身全部**（特に隠しフォルダ `.github/workflows/`）を、そのリポジトリにアップロードする。ZIP丸ごとのアップロードはNG（展開が必要）。
4. GitHubリポジトリの **Settings → Secrets and variables → Actions → New repository secret** に進み、Secret name `BUFFER_API_KEY` / Secret value にBufferで発行したAPIキーを貼り付けて保存。**チャットや通常のファイルに貼り付けないこと。**
5. **Settings → Actions → General** でActionsが許可されていること、Workflow permissions が **Read and write permissions** であることを確認。
6. **Actions → 麺処松もり｜毎朝9時の営業案内 → Run workflow** でまず `preview_only=true` の安全な試験実行をする（SNS投稿はされない）。
7. ログ・生成画像が正常か確認し、**ユーザーが内容を承認した場合のみ** `preview_only=false` の投稿予約テストを実行する。09:00を過ぎた日の手動予約は停止する仕様。

## 停止・変更

- **即時停止（次回からの自動予約を止める）**：リポジトリ直下に名前 `PAUSE` の空ファイルを作って保存。すでにBufferで予約済みの投稿は、Buffer側でも別途取り消してください。
- **再開**：`PAUSE` ファイルを削除。
- **個別の営業日変更**：`overrides.json` をGitHub上で編集。店主の明示的な指示がある場合だけ変更する。例：

```json
{
  "2026-10-24": {"status": "closed"},
  "2026-11-03": {"status": "open"}
}
```

*注：変更指示をチャットで伝えただけでは、GitHubの設定は自動更新されません。投稿予約前に `overrides.json` を変更する必要があります。予約済み投稿はBuffer側で別途編集・取消が必要です。*

## 投稿文章

営業日：11:00〜15:00（L.O.14:30）の案内。定休日：定休日の案内。X/Instagramのみ以下4個のタグを固定で使用します。

```
#麵処松もり
#ラーメン
#らーめん
#ラーメン好きな人と繋がりたい
```

Googleビジネスプロフィールにはタグなし。

## よくある質問

- **料金**：Buffer無料枠は3チャンネル、1チャンネルにつき予約待ち最大10件、APIリクエスト毎月3,000回まで（条件変更あり）。GitHubの公開リポジトリの標準Actionsは通常無料枠で運用可能。追加の有料画像生成APIなし。
- **時刻**：GitHubは02:13頃に「9時の予約」を作る。処理の遅延・障害やBuffer/SNS側の事情で09:00公開を保証するものではない。
- **画像公開の理由**：Buffer APIが画像ファイルの直接アップロードを受けず、インターネットからアクセスできる画像URLを要求するため。
- **APIキー期限**：発行時に設定した期限までにキーを更新し、GitHub Secretも入れ替える。
- **認証切れ**：Instagramなど連携が切れたときはBufferで再認証する。
- **失敗通知**：GitHub Actions の失敗通知（GitHub側のNotifications設定に依存）。別途メール通知や09:30掲載確認は将来拡張できる。
- **安全性**：プログラム内に秘密情報は書かない。まずは試験実行で確認し、明示承認後に本番開始。

## 技術・注意点

- Buffer GraphQL API: <https://developers.buffer.com/guides/posts-and-scheduling.html>
- Buffer image URL requirement: <https://developers.buffer.com/guides/hosting-media.html>
- GitHub Actions: <https://docs.github.com/en/actions>
- **実アカウントへの疎通・投稿テストは未実施**（Buffer APIキーは利用者だけが保持）。
- 「AI画像をその都度生成」ではなく、承認済みのデザインルールを**固定テンプレートで自動描画**する。日本語の崩れや誤字を避けるための仕様。
- 公開リポジトリは営業案内画像のみ公開する。パスワードや顧客情報を絶対に置かない。
