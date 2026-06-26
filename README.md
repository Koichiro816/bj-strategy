# ブラックジャック ストラテジー & シミュレーター

ハウスルールを入力するだけで、**解析的に最適なベーシックストラテジー**を生成し、
**モンテカルロシミュレーション**で還元率・破産確率を検証し、
**色分けPDF**として出力できるツールです。スマホブラウザにも対応しています。

副業プロジェクトのコンテンツ検証ツール（インタビュー内容の数字を統計的に裏付ける）として構築されています。

---

## 機能

| ファイル | 役割 |
|---|---|
| `rules.py` | ハウスルール定義（デッキ数・H17/S17・配当・サレンダー等） |
| `strategy.py` | 無限デッキ近似による解析的ベーシックストラテジー計算 |
| `index_plays.py` | Illustrious 18 + Fab 4（Hi-Lo TC別インデックス） |
| `simulator.py` | 有限デッキ モンテカルロ シミュレーター |
| `pdf_export.py` | 3テーブル色分けPDF出力（A4/A5/Letter） |
| `app.py` | Streamlit WebUI（5タブ構成・フリーミアム ゲーティング付き） |

---

## 起動方法 / How to Run

```bash
cd tools/blackjack
pip install -r requirements.txt
streamlit run app.py
```

ブラウザで http://localhost:8501 にアクセスします。

**スマホからのアクセス**：PCとスマホを同一WiFiに接続し、PCのローカルIP（例 `http://192.168.x.x:8501`）にアクセスします。Streamlit起動時に表示される `Network URL` を使ってください。

---

## 各タブの使い方

1. **ベーシックストラテジー（無料）**：ルールに応じた最適表を色分け表示。
   末尾に **勝敗内訳（スタンド時の win/push/lose）** セクションを搭載（#113機能）。
   任意のプレイヤー最終手×ディーラーアップカードの勝率・引き分け率・負け率を解析表示。
2. **インデックスプレイ（PRO）**：True Count スライダーで発動中のインデックスを確認
3. **シミュレーター（PRO）**：手数・カウンティングON/OFF・ベットスプレッドを設定して実行 → 還元率・PF・P値・破産確率・収支推移グラフ
4. **PDF出力（PRO）**：用紙サイズ・カラー/モノクロ・TCを指定してダウンロード
5. **ルール＆用語集（無料）**：初心者向けガイド

### フリーミアム（無料 / PRO）

- **無料**：ベーシックストラテジー表（＋勝敗内訳）・用語集
- **PRO**：シミュレーター・インデックスプレイ・PDF出力
- 解放方法：サイドバーの「PROアクセスコード」に購入コードを入力（`secrets` の
  `PRO_CODE` / `PRO_CODES` で設定）。決済連携は未実装（`DEPLOY.md` の TODO 参照）。

---

## アルゴリズム概要

- **ベーシックストラテジー**：無限デッキ近似（P(10)=4/13, 他=1/13）。ディーラー最終手分布を再帰＋`lru_cache`メモ化で計算し、スタンド/ヒット/ダブル/スプリット/サレンダーのEVを比較して最高EVを採用。結果はWizard of Oddsの無限デッキBSと整合します。
- **シミュレーター**：実際の有限シューでカードを配り、ペネトレーション到達でシャッフル。Hi-Loランニングカウント→True Count換算でベット・インデックスを調整。
- **破産確率**：Risk of Ruin の解析近似 `RoR = exp(-2·edge·bankroll/variance)` を使用。

---

## 検証目安（CEO実績データ）

- カウンティング時の還元率 ≈ **102%**（エッジ ≈ +2%）
- min×100バンクロール、TC+1→2倍 / TC+2→4倍 / TC+3→6倍 のスプレッドで破産確率 ≈ **75%**

手数が少ないと分散で値がぶれます。1,000万手以上を推奨します。

---

## English Summary

A professional Blackjack **Basic Strategy generator** (analytic, infinite-deck), **Monte-Carlo simulator** (finite shoe, Hi-Lo counting, bet spread), and **color-coded PDF exporter**. Mobile-friendly Streamlit UI.

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501 — accessible from a phone on the same WiFi via the Network URL.

---

## 個別モジュールのテスト

```bash
python strategy.py      # ディーラー確率と代表的なBS判定を表示
python index_plays.py   # インデックス調整の動作確認
python simulator.py     # 小規模シミュレーション（BS）
python pdf_export.py    # bs_test.pdf を生成
```
