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

# 動的閾値を探索するTCの範囲（UIのTCスライダー実用範囲 -5..+5 に余裕を持たせた値）
_TC_SCAN_RANGE = range(-6, 7)

# get_filtered_indexes() の結果キャッシュ（rules固有のキーで保持）。
# 同じrulesに対する結果は不変なため、シミュレーションの全ハンド・全判断で
# 毎回再計算すると非常に重くなる（数百万〜千万ハンド規模で致命的）。
_FILTERED_CACHE: dict = {}


def _rules_key(rules):
    """戦略・EV計算に影響する属性のみで構成したハッシュ可能なキーを返す。
    penetrationはシュー管理専用でEV計算には使わないため除外する。
    """
    return (rules.num_decks, rules.blackjack_pays, rules.dealer_peeks,
            rules.soft17, rules.double_allowed, rules.double_after_split,
            rules.split_aces, rules.draw_to_split_aces, rules.max_splits,
            rules.surrender, rules.surrender_vs_ace)


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


def _compute_deviations(hand_str, dealer_upcard, rules):
    """TC=0でのベーシックストラテジー（ベースアクション）から実際に
    逸脱するTCの境界を動的に計算する。

    ベースアクションと同じアクションを「逸脱」として報告しないようにする
    （例: 12 vs 6 はTC+0で既にスタンドが正解のため、TC>=-1でのスタンドを
    「逸脱プレイ」として表示するのは誤り。実際の逸脱は低TCでヒットに
    切り替わる方向のみ）。

    返り値: [(direction, threshold, action), ...]（0〜2件）
      direction "+": TC >= threshold で action に切り替わる（上昇方向の逸脱）
      direction "-": TC <= threshold で action に切り替わる（下降方向の逸脱）
    """
    args = _hand_to_args(hand_str, dealer_upcard, rules)
    base_action = best_action(rules=rules, tc=0, **args)

    results = []

    # 上昇方向: TCを上げていったとき最初にベースと異なるアクションになる点
    for tc in range(1, _TC_SCAN_RANGE[-1] + 1):
        a = best_action(rules=rules, tc=tc, **args)
        if a != base_action:
            results.append(("+", tc, a))
            break

    # 下降方向: TCを下げていったとき最初にベースと異なるアクションになる点
    for tc in range(-1, _TC_SCAN_RANGE[0] - 1, -1):
        a = best_action(rules=rules, tc=tc, **args)
        if a != base_action:
            results.append(("-", tc, a))
            break

    return results


_INSURANCE_THRESHOLD_CACHE = None
_INSURANCE_THRESHOLD_COMPUTED = False


def _insurance_threshold():
    """インシュランスの損益分岐となるTC指数を返す（EV = 3*p(10) - 1 = 0）。

    インシュランスの期待値は 3*P(テン) - 1（2:1配当）で、P(テン)=1/3 が分岐点。
    このモデルでの連続的な分岐点は約 TC=+3.3 になる。

    ここで「EV>=0 となる最初の整数」を取ると切り上げで +4 になってしまうが、
    それは実際の分岐点(+3.3)より高すぎる。カード指数の慣例どおり、連続分岐点を
    線形補間で求めて最も近い整数へ丸める（+3.3 → +3）。これは定評ある Hi-Lo の
    標準指数（Illustrious 18 の Insurance = +3）とも一致する。

    rulesに依存せず常に同じ値になるため、初回計算後はキャッシュを返す。
    """
    global _INSURANCE_THRESHOLD_CACHE, _INSURANCE_THRESHOLD_COMPUTED
    if _INSURANCE_THRESHOLD_COMPUTED:
        return _INSURANCE_THRESHOLD_CACHE
    result = None
    prev_tc, prev_ev = None, None
    for tc in _TC_SCAN_RANGE:
        ev = 3 * card_prob_tc(10, tc) - 1
        if prev_ev is not None and prev_ev < 0 <= ev:
            # prev_tc..tc の間でEVが0を横切る。線形補間で連続分岐点を求めて丸める
            cross = prev_tc + (-prev_ev) / (ev - prev_ev)
            result = int(round(cross))
            break
        prev_tc, prev_ev = tc, ev
    _INSURANCE_THRESHOLD_CACHE = result
    _INSURANCE_THRESHOLD_COMPUTED = True
    return result


def get_insurance_threshold():
    """インシュランスが得になる最小のTC（UI表示用の公開関数）。"""
    return _insurance_threshold()


def get_filtered_indexes(rules):
    """現在のハウスルールで実際にベーシックストラテジーから逸脱する
    インデックス一覧を、動的に計算した閾値・方向とともに返す。

    UI（インデックスプレイタブ）とPDF出力の両方で共用する。
    ベースアクション（TC=0での最適解）と同じアクションは「逸脱」とみなさず
    除外する。

    返り値: [(hand, dealer, threshold, action, direction), ...]
      direction "+": TC >= threshold で action に切り替わる
      direction "-": TC <= threshold で action に切り替わる
    """
    cache_key = _rules_key(rules)
    cached = _FILTERED_CACHE.get(cache_key)
    if cached is not None:
        return cached

    filtered = []
    seen_hands = set()
    for (h, d, _ref_thr, _ref_act) in ILLUSTRIOUS_18 + FAB_4:
        if h == "Insurance":
            thr = _insurance_threshold()
            if thr is not None:
                filtered.append((h, d, thr, "Buy", "+"))
            continue
        key = (h, d)
        if key in seen_hands:
            continue
        seen_hands.add(key)
        for (direction, thr, act) in _compute_deviations(h, d, rules):
            filtered.append((h, d, thr, act, direction))

    _FILTERED_CACHE[cache_key] = filtered
    return filtered


def _is_triggered(true_count, threshold, direction) -> bool:
    if direction == "+":
        return true_count >= threshold
    return true_count <= threshold


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

    for (h, d, thr, act, direction) in get_filtered_indexes(rules):
        if h == "Insurance":
            continue
        if str(h) == hand_str and _normalize_upcard(d) == up:
            if _is_triggered(true_count, thr, direction):
                op = ">=" if direction == "+" else "<="
                desc = f"TC{op}{thr:+d} のため {base_action}→{act}（インデックスプレイ）"
                return act, True, desc

    return base_action, False, "インデックス該当なし（BS通り）"


def should_take_insurance(true_count) -> bool:
    """インシュランスを取るべきか（動的計算した閾値で判定）。"""
    thr = _insurance_threshold()
    return thr is not None and true_count >= thr


def get_active_indexes(true_count, rules):
    """現在のTCで発動しているインデックス一覧を返す（UI表示用）。

    返り値: [(hand, upcard, threshold, action, direction), ...]
    """
    return [(h, d, thr, act, direction)
            for (h, d, thr, act, direction) in get_filtered_indexes(rules)
            if _is_triggered(true_count, thr, direction)]


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
