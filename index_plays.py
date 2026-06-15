"""
index_plays.py — True Count(TC)別インデックスプレイ

Hi-Lo カウンティングにおける Illustrious 18 / Fab 4 のインデックスを定義し、
TCに応じてベーシックストラテジーのアクションを調整する。

インデックス値は6デッキ、Hi-Loに基づく一般的な公開値。
H17/S17 で一部のプレイ（特にA関連）が変わる点に注意。
"""

# 形式: (player_hand, dealer_upcard, tc_threshold, action_at_threshold)
# TC >= tc_threshold のとき action_at_threshold を採用する（BSから逸脱）。
ILLUSTRIOUS_18 = [
    ("Insurance", "A", 3, "Buy"),          # TC>=+3でインシュランス購入
    ("16", 10, 0, "S"),                     # TC>=0でスタンド（BSはヒット）
    ("15", 10, 4, "R"),                     # TC>=+4でサレンダー
    ("10,10", 5, 5, "P"),                   # TC>=+5でスプリット
    ("10,10", 6, 4, "P"),                   # TC>=+4でスプリット
    ("10", 10, 4, "D"),                     # TC>=+4でダブル
    ("12", 3, 2, "S"),                      # TC>=+2でスタンド
    ("12", 2, 3, "S"),                      # TC>=+3でスタンド
    ("11", "A", 1, "D"),                    # TC>=+1でダブル
    ("9", 2, 1, "D"),                       # TC>=+1でダブル
    ("10", "A", 4, "D"),                    # TC>=+4でダブル
    ("9", 7, 3, "D"),                       # TC>=+3でダブル
    ("16", 9, 5, "S"),                      # TC>=+5でスタンド
    ("13", 2, -1, "S"),                     # TC>=-1でスタンド
    ("12", 4, 0, "S"),                      # TC>=0でスタンド
    ("12", 5, -2, "S"),                     # TC>=-2でスタンド
    ("12", 6, -1, "S"),                     # TC>=-1でスタンド
    ("13", 3, -2, "S"),                     # TC>=-2でスタンド
]

# Fab 4 Surrenders（レイトサレンダー前提）
FAB_4 = [
    ("14", 10, 3, "R"),     # TC>=+3でサレンダー
    ("15", 9, 2, "R"),      # TC>=+2でサレンダー
    ("15", "A", 1, "R"),    # TC>=+1でサレンダー（H17）
    ("16", 8, 4, "R"),      # TC>=+4でサレンダー
]


def _normalize_upcard(up):
    """アップカード表現を正規化する。文字'A'と数値11を相互に許容。"""
    if up in ("A", 11):
        return "A"
    return str(up)


def get_tc_adjusted_action(hand, dealer_upcard, true_count, base_action, rules):
    """TCに応じてBSアクションを調整する。

    引数:
      hand          : プレイヤーハンド表現（例 "16", "10,10", "11"）
      dealer_upcard : ディーラーアップカード（2..10 または "A"/11）
      true_count    : 現在のTrue Count（float）
      base_action   : ベーシックストラテジーのアクション（"H"/"S"/"D"/"P"/"R"）
      rules         : HouseRules

    返り値:
      (調整後アクション, インデックスが適用されたか bool, 説明文字列)
    """
    up = _normalize_upcard(dealer_upcard)
    hand_str = str(hand)

    # Illustrious 18 + Fab 4 を統合して走査
    all_indexes = ILLUSTRIOUS_18 + FAB_4

    for (h, d, thr, act) in all_indexes:
        if h == "Insurance":
            continue  # インシュランスは別途扱う
        if str(h) == hand_str and _normalize_upcard(d) == up:
            # H17依存のFab4（15 vs A）はS17では無効
            if h == "15" and d == "A" and rules.soft17 == "S17":
                continue
            # サレンダー不可ならRインデックスはスキップ
            if act == "R" and rules.surrender == "none":
                continue
            # ENHC: dealer 10/A は BJ リスクあり → D インデックスは不適用
            if not rules.dealer_peeks and act == "D" and _normalize_upcard(d) in ("10", "A"):
                continue
            if true_count >= thr:
                desc = f"TC>={thr:+d} のため {base_action}→{act}（Illustrious18/Fab4）"
                return act, True, desc

    return base_action, False, "インデックス該当なし（BS通り）"


def should_take_insurance(true_count) -> bool:
    """インシュランスを取るべきか（Hi-Lo: TC>=+3）。"""
    return true_count >= 3


def get_active_indexes(true_count, rules):
    """現在のTCで発動しているインデックス一覧を返す（UI表示用）。

    返り値: [(hand, upcard, threshold, action), ...]
    """
    active = []
    for (h, d, thr, act) in ILLUSTRIOUS_18 + FAB_4:
        if h == "Insurance":
            if true_count >= thr:
                active.append((h, d, thr, act))
            continue
        if h == "15" and d == "A" and rules.soft17 == "S17":
            continue
        if act == "R" and rules.surrender == "none":
            continue
        # ENHC: dealer 10/A は BJ リスクあり → D インデックスは不適用
        if not rules.dealer_peeks and act == "D" and _normalize_upcard(d) in ("10", "A"):
            continue
        if true_count >= thr:
            active.append((h, d, thr, act))
    return active


def _up_to_int(d) -> int:
    """インデックスエントリのディーラーカード表現を整数キーに変換する。"""
    if d == "A":
        return 11
    return int(d) if isinstance(d, str) else d


def apply_tc_overlay(base_table: dict, tc, rules) -> tuple:
    """TCに応じてBSテーブルを調整する（UI・PDF共用）。

    引数:
      base_table: generate_strategy_table の出力 {'hard':…, 'soft':…, 'pair':…}
      tc:         True Count (int or float)
      rules:      HouseRules

    返り値:
      (adjusted_table, changed_cells)
      changed_cells: set of ("hard"|"pair", row_key, upcard_int)

    ルール:
    - R（サレンダー）を S（スタンド）に格下げしない
    - 負TC時の逆転は現在 S のセルのみ H に変更
    """
    adj = {k: dict(v) for k, v in base_table.items()}
    changed: set = set()

    for (h, d, thr, act) in ILLUSTRIOUS_18 + FAB_4:
        if h == "Insurance":
            continue
        if h == "15" and d == "A" and rules.soft17 == "S17":
            continue
        if act == "R" and rules.surrender == "none":
            continue
        if act == "R" and not rules.surrender_vs_ace and d == "A":
            continue
        if not rules.dealer_peeks and act == "D" and _up_to_int(d) in (10, 11):
            continue

        up = _up_to_int(d)
        hand_str = str(h)

        if "," in hand_str:
            rank = int(hand_str.split(",")[0])
            k = (rank, up)
            if k not in adj["pair"]:
                continue
            current = adj["pair"][k]
            if tc >= thr:
                if current == "R" and act == "S":
                    continue
                if current != act:
                    adj["pair"][k] = act
                    changed.add(("pair", rank, up))
            elif act == "S" and current == "S":
                adj["pair"][k] = "H"
                changed.add(("pair", rank, up))
        else:
            total = int(hand_str)
            k = (total, up)
            if k not in adj["hard"]:
                continue
            current = adj["hard"][k]
            if tc >= thr:
                if current == "R" and act == "S":
                    continue
                if current != act:
                    adj["hard"][k] = act
                    changed.add(("hard", total, up))
            elif act == "S" and current == "S":
                adj["hard"][k] = "H"
                changed.add(("hard", total, up))

    return adj, changed


if __name__ == "__main__":
    from rules import HouseRules
    r = HouseRules()
    print(get_tc_adjusted_action("16", 10, 0, "H", r))
    print(get_tc_adjusted_action("16", 10, -1, "H", r))
    print("Insurance @ TC+3:", should_take_insurance(3))
