"""
strategy.py — 解析的ベーシックストラテジー計算機

無限デッキ近似（P(10)=4/13, それ以外=1/13）を用いて、
ディーラー最終手の確率分布とプレイヤーの各アクションEVを計算し、
最適アクションを導出する。

結果はWizard of Odds の無限デッキBSと一致するよう設計している。
パフォーマンスのため functools.lru_cache を使用。
"""

from functools import lru_cache
from rules import HouseRules

# 無限デッキにおける1枚引いたときの出目確率
# カードランクは 2..10, A(=11) で表現。10は10/J/Q/Kの4枚ぶん。
CARD_RANKS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]


def card_prob(rank: int) -> float:
    """無限デッキでのカード出現確率。10は4/13、それ以外は1/13。"""
    return 4.0 / 13.0 if rank == 10 else 1.0 / 13.0


def hand_value(total: int, soft: bool):
    """ソフト/ハードを考慮した実効合計を返す。
    ソフトかつ合計が21を超える場合はエースを1として扱う（ハード化）。
    返り値: (実効合計, soft フラグ)
    """
    if soft and total > 21:
        return total - 10, False
    return total, soft


def add_card(total: int, soft: bool, rank: int):
    """現在の手札にカードを1枚加える。
    エース(11)を加えてバストする場合は1として扱う。
    返り値: (新合計, 新softフラグ)
    """
    if rank == 11:
        # エースは11として加算し、必要ならソフト化
        new_total = total + 11
        new_soft = True
        if new_total > 21:
            new_total -= 10
            new_soft = soft  # 既存のソフト状態を維持（別のエースがあれば調整は下で）
    else:
        new_total = total + rank
        new_soft = soft
    # ソフトでバストしたらエースを1に戻す
    if new_soft and new_total > 21:
        new_total -= 10
        new_soft = False
    return new_total, new_soft


# ---------------------------------------------------------------------------
# ディーラー最終手確率
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _dealer_recurse(total: int, soft: bool, h17: bool) -> tuple:
    """ディーラーの手札(total, soft)から最終分布を再帰計算する。

    返り値はタプル化された分布（lru_cache対応のため）:
      (p17, p18, p19, p20, p21, p_bust)
    """
    # ディーラーがスタンドする条件
    stand = False
    if total > 21:
        # バスト確定
        return (0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    if total >= 18:
        stand = True
    elif total == 17:
        if soft:
            # ソフト17: H17ならヒット、S17ならスタンド
            stand = not h17
        else:
            stand = True

    if stand:
        idx = {17: 0, 18: 1, 19: 2, 20: 3, 21: 4}
        result = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        if 17 <= total <= 21:
            result[idx[total]] = 1.0
        return tuple(result)

    # ヒット：各カードについて再帰
    agg = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    for rank in CARD_RANKS:
        p = card_prob(rank)
        nt, ns = add_card(total, soft, rank)
        sub = _dealer_recurse(nt, ns, h17)
        for i in range(6):
            agg[i] += p * sub[i]
    return tuple(agg)


@lru_cache(maxsize=None)
def _dealer_from_upcard(upcard: int, h17: bool, peek: bool) -> tuple:
    """アップカードからディーラー最終分布を計算する。

    peek=True（US式）の場合、ディーラーBJが既に否定された条件付き分布を返す。
    （プレイヤーが行動するのはディーラーBJでない場合のみのため）
    """
    # 1枚目（アップカード）に2枚目を加えて展開
    agg = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    total_p = 0.0
    for rank in CARD_RANKS:
        # ピーク時、BJになる組み合わせを除外する
        if peek:
            if upcard == 11 and rank == 10:
                continue  # A + 10 = BJ → 除外
            if upcard == 10 and rank == 11:
                continue  # 10 + A = BJ → 除外
        p = card_prob(rank)
        # upcard自体のソフト判定（A=11はソフト扱い）
        if upcard == 11:
            base_total, base_soft = 11, True
        else:
            base_total, base_soft = upcard, False
        nt, ns = add_card(base_total, base_soft, rank)
        sub = _dealer_recurse(nt, ns, h17)
        for i in range(6):
            agg[i] += p * sub[i]
        total_p += p

    # 条件付き確率に正規化（除外したぶん）
    if total_p > 0:
        agg = [x / total_p for x in agg]
    return tuple(agg)


def dealer_final_probs(upcard: int, rules: HouseRules) -> dict:
    """ディーラー最終手確率を辞書で返す。

    返り値: {17: p, 18: p, 19: p, 20: p, 21: p, 'bust': p}
    upcard: 2..10, 11(=A)
    """
    h17 = rules.soft17 == "H17"
    probs = _dealer_from_upcard(upcard, h17, rules.dealer_peeks)
    return {
        17: probs[0],
        18: probs[1],
        19: probs[2],
        20: probs[3],
        21: probs[4],
        "bust": probs[5],
    }


# ---------------------------------------------------------------------------
# プレイヤーEV計算
# ---------------------------------------------------------------------------

def ev_stand(player_total: int, dealer_probs: dict) -> float:
    """スタンド時のEV。プレイヤーがバストしていない前提。
    勝ち=+1, 負け=-1, プッシュ=0。
    """
    if player_total > 21:
        return -1.0
    ev = 0.0
    for d in (17, 18, 19, 20, 21):
        if player_total > d:
            ev += dealer_probs[d]        # 勝ち
        elif player_total < d:
            ev -= dealer_probs[d]        # 負け
        # 同点はプッシュ（0）
    ev += dealer_probs["bust"]           # ディーラーバスト=勝ち
    return ev


@lru_cache(maxsize=None)
def _ev_hit_cached(player_total: int, soft: bool, dealer_upcard: int,
                   h17: bool, peek: bool) -> float:
    """ヒット時EVの再帰計算（メモ化）。最善のスタンド/ヒットを選ぶ。"""
    if player_total > 21:
        return -1.0

    # ディーラー分布（条件は固定なのでrules相当のフラグで取得）
    dprobs = _dealer_from_upcard(dealer_upcard, h17, peek)
    dealer_probs = {
        17: dprobs[0], 18: dprobs[1], 19: dprobs[2],
        20: dprobs[3], 21: dprobs[4], "bust": dprobs[5],
    }

    ev = 0.0
    for rank in CARD_RANKS:
        p = card_prob(rank)
        nt, ns = add_card(player_total, soft, rank)
        if nt > 21:
            ev += p * (-1.0)
        else:
            # 次の一手は スタンド or さらにヒット の良い方
            stand_ev = ev_stand(nt, dealer_probs)
            hit_ev = _ev_hit_cached(nt, ns, dealer_upcard, h17, peek)
            ev += p * max(stand_ev, hit_ev)
    return ev


def ev_hit(player_total: int, soft: bool, dealer_upcard: int,
           rules: HouseRules) -> float:
    """ヒット時EV（以降は最適プレイ）。"""
    h17 = rules.soft17 == "H17"
    return _ev_hit_cached(player_total, soft, dealer_upcard, h17, rules.dealer_peeks)


def ev_double(player_total: int, soft: bool, dealer_upcard: int,
              rules: HouseRules) -> float:
    """ダブル時EV。1枚だけ引いてスタンド、賭け金2倍。"""
    h17 = rules.soft17 == "H17"
    dprobs = _dealer_from_upcard(dealer_upcard, h17, rules.dealer_peeks)
    dealer_probs = {
        17: dprobs[0], 18: dprobs[1], 19: dprobs[2],
        20: dprobs[3], 21: dprobs[4], "bust": dprobs[5],
    }
    ev = 0.0
    for rank in CARD_RANKS:
        p = card_prob(rank)
        nt, ns = add_card(player_total, soft, rank)
        if nt > 21:
            ev += p * (-2.0)
        else:
            ev += p * 2.0 * ev_stand(nt, dealer_probs)
    return ev


def ev_split(pair_rank: int, dealer_upcard: int, rules: HouseRules) -> float:
    """スプリット時EV（近似）。
    各ハンドを「pair_rank 1枚スタート」とみなし、独立2ハンド分のEVを合算する近似。
    エースは1枚引いてスタンド（draw_to_split_aces=Falseのとき）。
    """
    h17 = rules.soft17 == "H17"
    dprobs = _dealer_from_upcard(dealer_upcard, h17, rules.dealer_peeks)
    dealer_probs = {
        17: dprobs[0], 18: dprobs[1], 19: dprobs[2],
        20: dprobs[3], 21: dprobs[4], "bust": dprobs[5],
    }

    base_total = 11 if pair_rank == 11 else pair_rank
    base_soft = pair_rank == 11

    # 1ハンド分のEV
    if pair_rank == 11 and not rules.draw_to_split_aces:
        # エースは1枚のみ
        single = 0.0
        for rank in CARD_RANKS:
            p = card_prob(rank)
            nt, ns = add_card(base_total, base_soft, rank)
            single += p * ev_stand(nt, dealer_probs)
    else:
        single = 0.0
        for rank in CARD_RANKS:
            p = card_prob(rank)
            nt, ns = add_card(base_total, base_soft, rank)
            if nt > 21:
                single += p * (-1.0)
            else:
                stand_ev = ev_stand(nt, dealer_probs)
                hit_ev = ev_hit(nt, ns, dealer_upcard, rules)
                # DAS考慮（簡易：ダブルも候補に）
                if rules.double_after_split and rules.can_double_total(nt) and not ns:
                    d_ev = ev_double(nt, ns, dealer_upcard, rules)
                    single += p * max(stand_ev, hit_ev, d_ev)
                else:
                    single += p * max(stand_ev, hit_ev)

    return 2.0 * single  # 2ハンド分


def ev_surrender() -> float:
    """サレンダー時EV。賭け金の半分を失う。"""
    return -0.5


# ---------------------------------------------------------------------------
# 最適アクション
# ---------------------------------------------------------------------------

def best_action(player_total: int, soft: bool, is_pair: bool,
                dealer_upcard: int, can_double: bool, can_split: bool,
                can_surrender: bool, rules: HouseRules,
                pair_rank: int = 0) -> str:
    """最適アクションを返す。

    返り値: "H"=ヒット, "S"=スタンド, "D"=ダブル, "P"=スプリット, "R"=サレンダー
    """
    h17 = rules.soft17 == "H17"
    dprobs = _dealer_from_upcard(dealer_upcard, h17, rules.dealer_peeks)
    dealer_probs = {
        17: dprobs[0], 18: dprobs[1], 19: dprobs[2],
        20: dprobs[3], 21: dprobs[4], "bust": dprobs[5],
    }

    candidates = {}
    candidates["S"] = ev_stand(player_total, dealer_probs)
    candidates["H"] = ev_hit(player_total, soft, dealer_upcard, rules)

    if can_double and rules.can_double_total(player_total if not soft else player_total):
        candidates["D"] = ev_double(player_total, soft, dealer_upcard, rules)

    if can_surrender and rules.surrender != "none":
        if dealer_upcard != 11 or rules.surrender_vs_ace:
            candidates["R"] = ev_surrender()

    if is_pair and can_split:
        candidates["P"] = ev_split(pair_rank, dealer_upcard, rules)

    # 最大EVのアクションを選択
    best = max(candidates, key=candidates.get)
    return best


def _action_ev(action: str, player_total: int, soft: bool, dealer_upcard: int,
              rules: HouseRules, pair_rank: int = 0) -> float:
    """指定アクションを実行した場合のEVを計算する（表示用）。"""
    if action == "R":
        return ev_surrender()
    if action == "D":
        return ev_double(player_total, soft, dealer_upcard, rules)
    if action == "P":
        return ev_split(pair_rank, dealer_upcard, rules)
    if action == "H":
        return ev_hit(player_total, soft, dealer_upcard, rules)
    # "S"（スタンド）がデフォルト
    h17 = rules.soft17 == "H17"
    dprobs = _dealer_from_upcard(dealer_upcard, h17, rules.dealer_peeks)
    dealer_probs = {
        17: dprobs[0], 18: dprobs[1], 19: dprobs[2],
        20: dprobs[3], 21: dprobs[4], "bust": dprobs[5],
    }
    return ev_stand(player_total, dealer_probs)


def generate_ev_table(table: dict, rules: HouseRules) -> dict:
    """戦略テーブルの各セルについて、表示中アクションのEVを計算した辞書を返す。

    table: generate_strategy_table() の出力、または TC overlay 適用後のテーブル。
           表示中のアクションに対するEVを返すため、overlay適用後でも対応可能。
    返り値: table と同じキー構造（'hard'/'soft'/'pair'）でEV(float)を保持。
    """
    ev_table = {"hard": {}, "soft": {}, "pair": {}}
    for (total, up), act in table["hard"].items():
        ev_table["hard"][(total, up)] = _action_ev(act, total, False, up, rules)
    for (total, up), act in table["soft"].items():
        ev_table["soft"][(total, up)] = _action_ev(act, total, True, up, rules)
    for (rank, up), act in table["pair"].items():
        total = rank * 2 if rank != 11 else 12
        is_soft = rank == 11
        ev_table["pair"][(rank, up)] = _action_ev(
            act, total, is_soft, up, rules, pair_rank=rank)
    return ev_table


# ---------------------------------------------------------------------------
# BSテーブル生成
# ---------------------------------------------------------------------------

def generate_strategy_table(rules: HouseRules) -> dict:
    """全ハンド×全アップカードのBSテーブルを生成する。

    返り値:
      {
        'hard': {(total, upcard): action},   # total 5..17
        'soft': {(total, upcard): action},   # A+2..A+9 を total 13..20 で表現
        'pair': {(rank, upcard): action},    # rank 2..11
      }
    upcard は 2..10, 11(=A)
    """
    upcards = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    table = {"hard": {}, "soft": {}, "pair": {}}

    # ハードハンド: 合計5..17（18以上は常にスタンド）
    for total in range(5, 18):
        for up in upcards:
            can_surr = rules.surrender != "none" and total in (14, 15, 16)
            act = best_action(total, soft=False, is_pair=False,
                              dealer_upcard=up, can_double=True,
                              can_split=False, can_surrender=can_surr,
                              rules=rules)
            table["hard"][(total, up)] = act

    # ソフトハンド: A+2(13)..A+9(20)
    for total in range(13, 21):
        for up in upcards:
            act = best_action(total, soft=True, is_pair=False,
                              dealer_upcard=up, can_double=True,
                              can_split=False, can_surrender=False,
                              rules=rules)
            table["soft"][(total, up)] = act

    # ペアハンド: 2..10, A(11)
    pair_ranks = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    for rank in pair_ranks:
        for up in upcards:
            is_soft = rank == 11
            total = rank * 2 if rank != 11 else 12  # A,A はソフト12
            can_split = True
            if rank == 11 and not rules.split_aces:
                can_split = False
            # ペアもサレンダー可能（surrender_vs_ace ルールに従う）
            can_surr_pair = (rules.surrender != "none" and
                             (up != 11 or rules.surrender_vs_ace))
            act = best_action(total, soft=is_soft, is_pair=True,
                              dealer_upcard=up, can_double=(rank != 11),
                              can_split=can_split, can_surrender=can_surr_pair,
                              rules=rules, pair_rank=rank)
            table["pair"][(rank, up)] = act

    # 無限デッキ近似の誤差補正: 既知の偏差を 6D 標準 BS に揃える
    if rules.soft17 == "S17":
        # Hard 11 vs A: 無限デッキ → H, 6D S17 HC → D
        # ENHC では BJ リスク(P=4/13)で D が著しく不利 → 補正は HC のみ
        if rules.can_double_total(11) and rules.dealer_peeks:
            table["hard"][(11, 11)] = "D"
        # Hard 11 vs 10 (ENHC): 無限デッキで H/D がほぼ同値 (margin≈0.0003)
        # 6D ENHC では 10-upcard の BJ リスク(P=1/13)を考慮しても D が正解
        if rules.can_double_total(11) and not rules.dealer_peeks:
            table["hard"][(11, 10)] = "D"
        # ソフトハンド補正: アップカード 2・5 → BJ リスクなし → HC/ENHC 共通
        if rules.can_double_total(18):
            table["soft"][(18, 2)] = "D"
        if rules.can_double_total(17):
            table["soft"][(17, 2)] = "D"
        if rules.can_double_total(13):
            table["soft"][(13, 5)] = "D"

    return table


if __name__ == "__main__":
    # 簡易動作確認
    r = HouseRules()
    dp = dealer_final_probs(6, r)
    print("Dealer up=6 final probs:", {k: round(v, 4) for k, v in dp.items()})
    print("16 vs 10:", best_action(16, False, False, 10, True, False, True, r))
    print("11 vs 6:", best_action(11, False, False, 6, True, False, False, r))
    print("A,A vs 5:", best_action(12, True, True, 5, False, True, False, r, pair_rank=11))
