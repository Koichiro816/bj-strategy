# デプロイ手順書（Streamlit Community Cloud）

本ツールを Web 公開するための手順です。無料の **Streamlit Community Cloud** を前提に、
最小コスト・最小操作で公開できるよう整理しています。実際のクラウド操作（GitHub 連携・
デプロイボタン押下）は CEO のアカウントで実施してください。

---

## 0. 公開前チェックリスト

- [ ] `requirements.txt` が最新（下記§1で確認）
- [ ] `.streamlit/secrets.toml` が **Git に含まれていない**（`.gitignore` 済み）
- [ ] ローカルで `streamlit run app.py` が起動し、5タブが表示される
- [ ] 無料/PRO ゲーティングが想定どおり動く（§3）
- [ ] `python strategy.py` がエラーなく実行できる（ロジック健全性）

---

## 1. requirements.txt の確認

現在の依存パッケージ（`tools/blackjack/requirements.txt`）：

```
streamlit>=1.28.0
numpy>=1.24.0
scipy>=1.10.0
reportlab>=4.0.0
pandas>=2.0.0
matplotlib>=3.7.0
japanize-matplotlib>=1.1.3
plotly>=5.15.0
```

追加ライブラリを使い始めた場合は、必ずここに追記してから push すること
（Community Cloud はこのファイルだけを見て環境を構築する）。

---

## 2. GitHub への配置

Streamlit Community Cloud は **GitHub リポジトリ** からデプロイする。

1. このプロジェクトを GitHub に push（**`.streamlit/secrets.toml` は push しない**）
2. デプロイ時に指定する情報：
   - Repository: `<your-account>/<repo>`
   - Branch: `main`
   - **Main file path: `tools/blackjack/app.py`**

> リポジトリのサブディレクトリにアプリがあるため、Main file path に
> `tools/blackjack/app.py` を必ず指定する。`requirements.txt` も同じ
> `tools/blackjack/` 配下にあるため、Community Cloud が自動検出する。

---

## 3. シークレット管理（PASSWORD と PROコード）

**`.streamlit/secrets.toml` は Git に含めない。** 代わりに Community Cloud の
管理画面（App settings → Secrets）に同じ内容を貼り付ける。

```toml
# サイト全体のアクセス制限（任意。設定すると入口でパスワードを要求）
PASSWORD = "（公開時に決める強固なパスワード）"

# PRO（有料）機能の解放コード
PRO_CODE = "（購入者に渡すコード）"
# 複数コードを使う場合（カンマ区切り）
# PRO_CODES = "PRO-A1B2, PRO-C3D4"
```

### 認証の挙動（コードを読まなくても分かるように）

| シークレット | 未設定時の挙動 | 設定時の挙動 |
|---|---|---|
| `PASSWORD` | 入口認証なし（誰でも閲覧可） | 入口でパスワード要求 |
| `PRO_CODE` / `PRO_CODES` | フォールバック `DEMO-PRO` が有効（ローカル検証用） | 指定コードのみ PRO 解放 |

- **無料プラン**：ベーシックストラテジー表タブのみ利用可（勝敗内訳セクション含む）
- **PRO プラン**：サイドバーに正しいPROコードを入力すると、
  シミュレーター・インデックスプレイ・PDF出力が解放される

> 本番公開時は `PRO_CODE` を必ず推測されにくい値に設定すること
> （未設定だと `DEMO-PRO` で誰でも解放できてしまう）。

### 【決済連携TODO（未実装）】

現状は「アクセスコード入力で解放」する簡易ゲート。決済バックエンドは未接続。
本番の自動化フローは以下を想定（CTO ロードマップ Phase2 相当）：

1. Stripe / Gumroad の決済リンクをサイドバー／ロック画面に設置
2. 決済完了 Webhook で一意のPROコードを発行
3. 購入者にコードを自動送付（メール/LINE）
4. ユーザーがサイドバーに入力 → `app.py` の `_get_pro_codes()` が照合
5. （将来）コードを secrets ではなく外部DB/KVで管理し、発行・失効を自動化

`app.py` 内の `_get_pro_codes()` / `_render_pro_gate()` / `_pro_locked_notice()`
に該当 TODO コメントを記載済み。決済連携時はこの3関数を差し替える。

---

## 4. 無料枠の制約（Community Cloud）

- **リソース**：1 アプリあたり RAM 約1GB。重いシミュレーション（1,000万手）は
  時間がかかるため、無料枠では手数を抑えるか、必要に応じて有料ホスティングを検討。
- **スリープ**：一定時間アクセスがないとアプリがスリープし、次回アクセス時に
  数十秒のウェイクアップ時間が発生する（無料枠の仕様）。
- **同時実行**：アクセス集中時はレスポンスが低下する可能性あり。
- **公開範囲**：`PASSWORD` 未設定だと URL を知る全員が閲覧可能。
  限定公開したい場合は `PASSWORD` を設定する。

> スケール（有料転換が伸びた）段階で、Streamlit の有料プランや
> 他ホスティング（Render / Fly.io / 自前VPS）への移行を CFO と検討する。

---

## 5. 公開後の動作確認

1. 公開 URL にアクセス → `PASSWORD` 設定時はログイン
2. 「ベーシックストラテジー」タブが無料で表示されること
3. 「シミュレーター」「インデックスプレイ」「PDF出力」タブが
   **ロック表示**になっていること（無料状態）
4. サイドバーで PRO コードを入力 → 上記3タブが解放されること
5. PDF が正しくダウンロードできること（reportlab 依存の動作確認）

---

## 6. ローカルでの最終確認コマンド

```bash
cd tools/blackjack
pip install -r requirements.txt
python strategy.py        # ロジック健全性（ディーラー分布・BS判定・勝敗内訳）
streamlit run app.py      # WebUI 起動確認
```
