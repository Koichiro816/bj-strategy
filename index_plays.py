"""
index_plays.py — True Count(TC)別インデックスプレイ

Illustrious 18 / Fab 4 は「カウンターが覚えるべき代表的な逸脱プレイ」を示す
ハンド・アップカードの組み合わせのシードリストとして保持するが、実際の
発動TC・推奨アクションは固定の文献値ではなく、strategy.py のEV計算ロジック
（このアプリが採用する無限デッキ近似＋TC比率調整モデル）を使って動的に
計算する。これにより、ハウスルール（HC/ENHC・サレンダー有無・S17/H17等）
や近似モデルの違いによって実際には適用されない／閾値が異なるケースを
正しく反映できる（例: サレンダー有効時は「16 vs 10 スタンド」は実際には
一度も最適にならず、常にサレンダーが優先される）。
"""

from strategy import best_action, card_prob_tc

# シードリスト: (player_hand, dealer_upcard, _参考閾値, action)
# _参考閾値 は文献上の一般的な値（コメント用途のみ）。実際の判定・表示は
# 動的計算（_dynamic_threshold）の結果を使う。
ILLUSTRIOUS_18 = [
    ("Insurance", "A", 3, "Buy"),
    ("16", 10, 0, "S"),
    ("15", 10, 4, "R"),
    ("10,10", 5, 5, "P"),
    ("10,10", 6, 4, "P"),
    ("10", 10, 4, "D"),
    ("12", 3, 2, "S"),
    ("12", 2, 3, "S"),
    ("11", "A", 1, "D"),
    ("9", 2, 1, "D"),
    ("10", "A", 4, "D"),
    ("9", 7, 3, "D"),
    ("16", 9, 5, "S"),
    ("13", 2, -1, "S"),
    ("12", 4, 0, "S"),
    ("12", 5, -2, "S"),
    ("12", 6, -1, "S"),
    ("13", 3, -2, "S"),
]

# Fab 4 Surrenders（レイトサレンダー前提）
FAB_4 = [
    ("14", 10, 3, "R"),
    ("15", 9, 2, "R"),
    ("15", "A", 1, "R"),
    ("16", 8, 4, "R"),
]

# 動的閾値を探索するTCの範囲
_TC_SCAN_RANGE = range(-10, 11)


def _normalize_upcard(up):
    """アップカード表現を正規化する。文字'A'と数値11を相互に許容。"""
    if up in ("A", 11):
        return "A"
    return str(up)


def _hand_to_args(hand_str, dealer_upcard, rules):
    """インデックスのhand文字列をbest_action()用の引数辞書に変換する。"""
    up = 11 if dealer_upcard in ("A", 11) else dealer_upcard
    if "," in hand_str:
        rank = int(hand_str.split(",")[0])
        total = rank * 2 if rank != 11 else 12
        can_split = rules.split_aces if rank == 11 else True
        can_surrender = rules.surrender != "none" and (up != 11 or rules.surrender_vs_ace)
        return dict(player_total=total, soft=(rank == 11), is_pair=True,
                   dealer_upcard=up, can_double=(rank != 11), can_split=can_split,
                   can_surrender=can_surrender, pair_rank=rank)
    total = int(hand_str)
    can_surrender = rules.surrender != "none" and total in (14, 15, 16)
    return dict(player_total=total, soft=False, is_pair=False,
               dealer_upcard=up, can_double=True, can_split=False,
               can_surrender=can_surrender, pair_rank=0)


def _dynamic_threshold(hand_str, dealer_upcard, action, rules):
    """指定アクションが実際に最適となる最小のTCを動的に計算する。

    現在のハウスルールの下でそのアクションが他の候補（特にサレンダーなど）
    に常に劣る場合は None を返す（=このインデックスは適用不可）。
    """
    args = _hand_to_args(hand_str, dealer_upcard, rules)
    for tc in _TC_SCAN_RANGE:
        if best_action(rules=rules, tc=tc, **args) == action:
            return tc
    return None


def _insurance_threshold():
    """インシュランスが得になる最小のTCを動的に計算する（EV = 3*p(10) - 1 >= 0）。"""
    for tc in _TC_SCAN_RANGE:
        if 3 * card_prob_tc(10, tc) - 1 >= 0:
            return tc
    return None


def get_filtered_indexes(rules):
    """現在のハウスルールで実際に適用可能なインデックス一覧を、
    動的に計算した正しい閾値とともに返す。

    UI（インデックスプレイタブ）とPDF出力の両方で共用する。
    H17限定プレイ（15 vs A）はS17では除外し、それ以外は
    _dynamic_threshold() の結果（None=適用不可）でフィルタする。
    """
    filtered = []
    for (h, d, _ref_thr, act) in ILLUSTRIOUS_18 + FAB_4:
        if h == "Insurance":
            thr = _insurance_threshold()
            if thr is not None:
                filtered.append((h, d, thr, act))
            continue
        if h == "15" and d == "A" and rules.soft17 == "S17":
            continue
        thr = _dynamic_threshold(h, d, act, rules)
        if thr is None:
            continue
        filtered.append((h, d, thr, act))
    return filtered


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

    for (h, d, thr, act) in get_filtered_indexes(rules):
        if h == "Insurance":
            continue
        if str(h) == hand_str and _normalize_upcard(d) == up:
            if true_count >= thr:
                desc = f"TC>={thr:+d} のため {base_action}→{act}（Illustrious18/Fab4）"
                return act, True, desc

    return base_action, False, "インデックス該当なし（BS通り）"


def should_take_insurance(true_count) -> bool:
    """インシュランスを取るべきか（動的計算した閾値で判定）。"""
    thr = _insurance_threshold()
    return thr is not None and true_count >= thr


def get_active_indexes(true_count, rules):
    """現在のTCで発動しているインデックス一覧を返す（UI表示用）。

    返り値: [(hand, upcard, threshold, action), ...]
    """
    return [(h, d, thr, act) for (h, d, thr, act) in get_filtered_indexes(rules)
            if true_count >= thr]


def apply_tc_overlay(base_table: dict, tc, rules) -> tuple:
    """TCに応じてBSテーブルを調整する（UI・PDF共用）。

    strategy.generate_strategy_table(rules, tc=tc) で当該TCの正しい戦略
    テーブルを直接計算し、base_table（通常はTC=0のベース戦略）との差分を
    変更セルとして返す。固定のインデックスリストに頼らないため、
    ハウスルールや近似モデルに関わらず常に内部ロジックと一致する。

    返り値:
      (adjusted_table, changed_cells)
      changed_cells: set of ("hard"|"pair"|"soft", row_key, upcard_int)
    """
    from strategy import generate_strategy_table
    tc_table = generate_strategy_table(rules, tc=tc)

    adj = {k: dict(v) for k, v in base_table.items()}
    changed: set = set()
    for table_type in ("hard", "soft", "pair"):
        for key, new_act in tc_table[table_type].items():
            if base_table[table_type].get(key) != new_act:
                adj[table_type][key] = new_act
                changed.add((table_type, key[0], key[1]))

    return adj, changed


if __name__ == "__main__":
    from rules import HouseRules
    r = HouseRules()
    print(get_tc_adjusted_action("16", 10, 0, "H", r))
    print(get_tc_adjusted_action("16", 10, -1, "H", r))
    print("Insurance threshold:", _insurance_threshold())
