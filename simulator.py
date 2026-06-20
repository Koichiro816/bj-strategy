"""
simulator.py — ブラックジャック モンテカルロシミュレーター

実際のシュー（有限デッキ）でカードを配り、ベーシックストラテジーまたは
Hi-Loカウンティング戦略でプレイして統計を集計する。

検証目標:
  - カウンティング時の還元率 ≈ 102%（エッジ ≈ +2%）
  - min×100バンクロール、TC+1→2倍/TC+2→4倍/TC+3→6倍 で破産確率 ≈ 75%
"""

import math
import random
from dataclasses import dataclass, field
from typing import Optional

from rules import HouseRules
from strategy import generate_strategy_table
from index_plays import get_tc_adjusted_action, should_take_insurance


# Hi-Lo カウント値
HILO = {2: 1, 3: 1, 4: 1, 5: 1, 6: 1,
        7: 0, 8: 0, 9: 0,
        10: -1, 11: -1}


@dataclass
class SimConfig:
    rules: HouseRules
    num_hands: int = 1_000_000
    use_counting: bool = False
    bet_spread: Optional[dict] = None   # {TC_threshold: 賭け額（絶対値、開始時バンクロール基準）} 例 {1:2,2:4,3:6}
    min_bet: float = 1.0                # ミニマムベット（絶対値、開始時バンクロール基準）
    max_bet: float = 1_000_000.0        # マックスベット（絶対値）。賭け額はこれを超えない
    bankroll: float = 100.0             # バンクロール（絶対値、シミュレーション開始時の値）
    bankroll_scaling: bool = False      # True: 各ハンドの賭け額を「現在のバンクロール/開始時バンクロール」の比率で動的にスケールする
    strategy: str = "basic"             # "basic" or "counting"
    seed: Optional[int] = None


@dataclass
class SimResult:
    num_hands: int
    net_profit: float          # 純利益（min_bet単位）
    win_rate: float
    push_rate: float
    house_edge: float          # ハウスエッジ（%、マイナスならプレイヤー有利）
    std_dev: float
    profit_factor: float       # PF = 総利益/総損失
    ruin_probability: float    # 破産確率
    p_value: float             # 勝ちが偶然でない確率（片側）
    max_drawdown: float        # 最大ドローダウン
    total_wagered: float = 0.0
    return_pct: float = 0.0    # 還元率(%)
    bankroll_curve: list = field(default_factory=list)
    curve_sample_every: int = 1  # bankroll_curveの各点が何ハンドおきのサンプルか
    stopped_early: bool = False  # バンクロール枯渇により設定手数に達する前に終了したか


class Shoe:
    """有限デッキのシュー。ペネトレーション到達でシャッフル。"""

    def __init__(self, num_decks: int, penetration: float, rng: random.Random):
        self.num_decks = num_decks
        self.penetration = penetration
        self.rng = rng
        self.cards = []
        self.pos = 0
        self.running_count = 0
        self._build()

    def _build(self):
        # 各デッキ: 2..9 が各4枚、10が16枚(10/J/Q/K)、A(11)が4枚
        single = []
        for rank in range(2, 10):
            single += [rank] * 4
        single += [10] * 16
        single += [11] * 4
        self.cards = single * self.num_decks
        self.rng.shuffle(self.cards)
        self.pos = 0
        self.running_count = 0
        self._cut = int(len(self.cards) * self.penetration)

    def needs_shuffle(self) -> bool:
        return self.pos >= self._cut

    def deal(self) -> int:
        if self.pos >= len(self.cards):
            self._build()
        card = self.cards[self.pos]
        self.pos += 1
        self.running_count += HILO[card]
        return card

    def true_count(self) -> float:
        remaining_decks = (len(self.cards) - self.pos) / 52.0
        if remaining_decks < 0.25:
            remaining_decks = 0.25
        return self.running_count / remaining_decks


def _tier_bet(tc: float, config: SimConfig) -> float:
    """TCに応じた「設定上の」賭け額を返す（bankroll_scalingによる調整前の値）。

    bet_spread/min_betの閾値テーブルそのものを参照する、開始時バンクロール
    基準の固定値。破産確率の算出で、実現したバンクロールの経路（運の良し悪し）
    に依存しない安定した基準値として使う。
    """
    if not config.use_counting or not config.bet_spread:
        return min(config.max_bet, config.min_bet)
    bet = config.min_bet
    # 閾値の高い順に評価して最大のものを採用
    for thr in sorted(config.bet_spread.keys()):
        if tc >= thr:
            bet = config.bet_spread[thr]
    # TCが閾値未満（負の局面）はミニマムベット
    # マックスベットを超えないようにクリップ
    return min(config.max_bet, bet)


def _bet_size(tc: float, config: SimConfig, current_bankroll: float) -> float:
    """TCに応じたベット額（絶対値）を返す。

    bankroll_scaling=True の場合、bet_spread/min_betは「開始時バンクロール」
    基準の値として扱い、現在のバンクロールが開始時から増減した比率で
    実際のベット額を動的にスケールする（バンクロール比例ベット）。
    """
    bet = _tier_bet(tc, config)

    if config.bankroll_scaling and config.bankroll > 0:
        bet *= current_bankroll / config.bankroll

    # テーブルの実質的な最低ベット(config.min_bet)を下回らないようにする
    # （スケール後の値をハードコードの1で下限にすると、min_bet>1設定時に
    # 設定した最低ベットより小さい賭け額になってしまう）。
    # 同様に、自動スケールでバンクロールが増えてもマックスベットを超えない
    # ようにクリップする。
    return min(config.max_bet, max(config.min_bet, bet))


def _hand_total(cards):
    """手札の(合計, soft)を返す。"""
    total = 0
    aces = 0
    for c in cards:
        if c == 11:
            aces += 1
            total += 11
        else:
            total += c
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    soft = aces > 0
    return total, soft


def _is_blackjack(cards):
    return len(cards) == 2 and _hand_total(cards)[0] == 21


def _lookup_action(player_cards, dealer_up, strat_table, rules,
                   can_double, can_split, can_surrender, tc):
    """戦略テーブル＋TCインデックスからアクションを引く。"""
    total, soft = _hand_total(player_cards)
    is_pair = len(player_cards) == 2 and player_cards[0] == player_cards[1]

    # ベースアクション取得
    if is_pair and can_split:
        rank = player_cards[0]
        act = strat_table["pair"].get((rank, dealer_up), "H")
    elif soft:
        act = strat_table["soft"].get((total, dealer_up), "H")
    else:
        # ハード18以上はスタンド
        if total >= 18:
            act = "S"
        elif total <= 4:
            act = "H"
        else:
            act = strat_table["hard"].get((total, dealer_up), "H")

    # 不可能なアクションのフォールバック
    if act == "D" and not can_double:
        act = "H"
    if act == "P" and not can_split:
        # スプリット不可ならハード/ソフトの代替を引く
        if soft:
            act = strat_table["soft"].get((total, dealer_up), "H")
        else:
            act = strat_table["hard"].get((total, dealer_up), "H") if total < 18 else "S"
    if act == "R" and not can_surrender:
        act = "H"

    # TCインデックス調整（カウンティング時のみ）
    if tc is not None:
        hand_str = _hand_to_index_str(player_cards, total, is_pair)
        adj, applied, _ = get_tc_adjusted_action(hand_str, dealer_up, tc, act, rules)
        if applied:
            cand = adj
            if cand == "D" and not can_double:
                cand = "H"
            if cand == "P" and not can_split:
                cand = act
            if cand == "R" and not can_surrender:
                cand = act
            act = cand

    return act


def _hand_to_index_str(cards, total, is_pair):
    """インデックス検索用のハンド文字列を作る。"""
    if is_pair and cards[0] == 10:
        return "10,10"
    return str(total)


def _play_dealer(dealer_cards, shoe, rules):
    """ディーラーをルールに従ってプレイし最終合計を返す。"""
    while True:
        total, soft = _hand_total(dealer_cards)
        if total > 21:
            return total
        if total >= 18:
            return total
        if total == 17:
            if soft and rules.soft17 == "H17":
                dealer_cards.append(shoe.deal())
                continue
            return total
        dealer_cards.append(shoe.deal())


def _play_player_hand(cards, dealer_up, shoe, strat_table, rules, tc,
                      bet, is_split_hand=False, split_aces=False, depth=0):
    """1ハンドをプレイして (最終手札リスト, 賭け金, surrendered) を返す。

    スプリットは再帰的に処理し、複数ハンドのリストを返す。
    返り値: [(cards, bet, surrendered), ...]
    """
    results = []

    # スプリットしたエースは1枚で打ち止め（draw_to_split_aces=False時）
    if split_aces and not rules.draw_to_split_aces:
        cards.append(shoe.deal())
        return [(cards, bet, False)]

    while True:
        total, soft = _hand_total(cards)
        if total >= 21:
            return [(cards, bet, False)]

        num_cards = len(cards)
        is_pair = num_cards == 2 and cards[0] == cards[1]
        can_double = num_cards == 2 and (not is_split_hand or rules.double_after_split)
        can_split = (is_pair and depth < rules.max_splits)
        if is_pair and cards[0] == 11 and not rules.split_aces:
            can_split = False
        can_surrender = (num_cards == 2 and not is_split_hand
                         and rules.surrender in ("late", "early"))

        act = _lookup_action(cards, dealer_up, strat_table, rules,
                             can_double, can_split, can_surrender, tc)

        if act == "S":
            return [(cards, bet, False)]
        if act == "R":
            return [(cards, bet, True)]
        if act == "D":
            cards.append(shoe.deal())
            return [(cards, bet * 2, False)]
        if act == "P":
            rank = cards[0]
            aces = rank == 11
            hand1 = [rank, shoe.deal()]
            hand2 = [rank, shoe.deal()]
            results += _play_player_hand(hand1, dealer_up, shoe, strat_table,
                                         rules, tc, bet, is_split_hand=True,
                                         split_aces=aces, depth=depth + 1)
            results += _play_player_hand(hand2, dealer_up, shoe, strat_table,
                                         rules, tc, bet, is_split_hand=True,
                                         split_aces=aces, depth=depth + 1)
            return results
        # "H"
        cards.append(shoe.deal())


def simulate(config: SimConfig) -> SimResult:
    """シミュレーションを実行して統計結果を返す。"""
    rng = random.Random(config.seed)
    rules = config.rules
    strat_table = generate_strategy_table(rules)
    shoe = Shoe(rules.num_decks, rules.penetration, rng)

    net = 0.0
    total_wagered = 0.0
    wins = 0
    pushes = 0
    losses = 0
    sum_x = 0.0      # 1手あたり結果の和（ベット正規化、SD/P値表示用）
    sum_x2 = 0.0     # 二乗和（標準偏差用）
    # 破産確率用: 「設定上のベット額(ref_bet)」を使った場合の1手あたり結果。
    # 実現したバンクロールの経路（bankroll_scaling時の運の良し悪し）に
    # 依存しない、戦略・賭け方そのものに基づく安定した統計量とするため、
    # 実際のベット額ではなく ref_bet で重み付けする。
    sum_profit = 0.0
    sum_profit2 = 0.0
    gross_win = 0.0   # プロフィットファクター用: 実際の勝ちハンドの合計利益
    gross_loss = 0.0  # プロフィットファクター用: 実際の負けハンドの合計損失(絶対値)

    bankroll = config.bankroll
    peak = config.bankroll
    max_dd = 0.0
    ruined = False
    curve_sample = []
    sample_every = max(1, config.num_hands // 2000)

    use_count_strategy = config.use_counting or config.strategy == "counting"
    hands_played = config.num_hands
    stopped_early = False

    for i in range(config.num_hands):
        if shoe.needs_shuffle():
            shoe._build()

        tc = shoe.true_count() if use_count_strategy else None
        bet = _bet_size(tc if tc is not None else 0.0, config, bankroll)
        ref_bet = _tier_bet(tc if tc is not None else 0.0, config)

        # 配札
        player = [shoe.deal(), shoe.deal()]
        dealer = [shoe.deal(), shoe.deal()]
        dealer_up = dealer[0]

        total_wagered += bet
        hand_result = 0.0  # このラウンドの純損益（min_bet単位）

        # インシュランス（ディーラーアップA、カウンティング時）
        insurance_bet = 0.0
        if (dealer_up == 11 and use_count_strategy
                and should_take_insurance(tc)):
            insurance_bet = bet / 2.0
            total_wagered += insurance_bet

        player_bj = _is_blackjack(player)
        dealer_bj = _is_blackjack(dealer)

        # アーリーサレンダー（ディーラーのBJピーク前に判断する稀少ルール）。
        # ピーク後に判断するレイトサレンダーと異なり、サレンダーを選んだ場合は
        # ディーラーの手札に関わらず賭け金の半分のみを失う。
        if (rules.surrender == "early" and not player_bj
                and _lookup_action(player, dealer_up, strat_table, rules,
                                   can_double=False, can_split=False,
                                   can_surrender=True, tc=tc) == "R"):
            hand_result -= bet * 0.5
            losses += 1
            net += hand_result
            bankroll += hand_result
            ratio = hand_result / bet if bet else 0.0
            sum_x += ratio
            sum_x2 += ratio ** 2
            sum_profit += ratio * ref_bet
            sum_profit2 += (ratio * ref_bet) ** 2
            gross_loss += -hand_result
            if bankroll > peak:
                peak = bankroll
            dd = peak - bankroll
            if dd > max_dd:
                max_dd = dd
            if bankroll <= 0 and not ruined:
                ruined = True
            if i % sample_every == 0:
                curve_sample.append(net)
            if config.bankroll_scaling and bankroll <= 0:
                hands_played = i + 1
                stopped_early = True
                break
            continue

        # ピーク処理（US式: ディーラーBJを即確認）
        if rules.dealer_peeks and dealer_bj:
            # インシュランス精算
            if insurance_bet > 0:
                hand_result += insurance_bet * 2  # 2:1配当
            if player_bj:
                hand_result += 0.0  # プッシュ
                pushes += 1
            else:
                hand_result -= bet
                losses += 1
            net += hand_result
            bankroll += hand_result
            _update_stats_local = True
            ratio = hand_result / bet if bet else 0.0
            sum_x += ratio
            sum_x2 += ratio ** 2
            sum_profit += ratio * ref_bet
            sum_profit2 += (ratio * ref_bet) ** 2
            if hand_result > 0:
                gross_win += hand_result
            elif hand_result < 0:
                gross_loss += -hand_result
            # ドローダウン
            if bankroll > peak:
                peak = bankroll
            dd = peak - bankroll
            if dd > max_dd:
                max_dd = dd
            if bankroll <= 0 and not ruined:
                ruined = True
            if i % sample_every == 0:
                curve_sample.append(net)
            if config.bankroll_scaling and bankroll <= 0:
                hands_played = i + 1
                stopped_early = True
                break
            continue
        else:
            if insurance_bet > 0:
                hand_result -= insurance_bet  # インシュランス負け

        # プレイヤーBJ（ディーラーBJでない）
        if player_bj:
            hand_result += bet * rules.blackjack_pays
            wins += 1
            net += hand_result
            bankroll += hand_result
            ratio = hand_result / bet if bet else 0.0
            sum_x += ratio
            sum_x2 += ratio ** 2
            sum_profit += ratio * ref_bet
            sum_profit2 += (ratio * ref_bet) ** 2
            if hand_result > 0:
                gross_win += hand_result
            elif hand_result < 0:
                gross_loss += -hand_result
            if bankroll > peak:
                peak = bankroll
            dd = peak - bankroll
            if dd > max_dd:
                max_dd = dd
            if bankroll <= 0 and not ruined:
                ruined = True
            if i % sample_every == 0:
                curve_sample.append(net)
            if config.bankroll_scaling and bankroll <= 0:
                hands_played = i + 1
                stopped_early = True
                break
            continue

        # プレイヤーのプレイ
        hands = _play_player_hand(player, dealer_up, shoe, strat_table,
                                  rules, tc, bet)

        # サレンダー判定（単一ハンドのみ）
        if len(hands) == 1 and hands[0][2]:
            hand_result -= hands[0][1] * 0.5
            losses += 1
            net += hand_result
            bankroll += hand_result
            ratio = hand_result / bet if bet else 0.0
            sum_x += ratio
            sum_x2 += ratio ** 2
            sum_profit += ratio * ref_bet
            sum_profit2 += (ratio * ref_bet) ** 2
            if hand_result > 0:
                gross_win += hand_result
            elif hand_result < 0:
                gross_loss += -hand_result
            if bankroll > peak:
                peak = bankroll
            dd = peak - bankroll
            if dd > max_dd:
                max_dd = dd
            if bankroll <= 0 and not ruined:
                ruined = True
            if i % sample_every == 0:
                curve_sample.append(net)
            if config.bankroll_scaling and bankroll <= 0:
                hands_played = i + 1
                stopped_early = True
                break
            continue

        # ディーラープレイ（プレイヤーが全バストでなければ）
        any_alive = any(_hand_total(c)[0] <= 21 for c, b, s in hands)
        if any_alive:
            dealer_final = _play_dealer(dealer, shoe, rules)
        else:
            dealer_final = _hand_total(dealer)[0]

        round_win = 0
        for cards, b, surr in hands:
            p_total = _hand_total(cards)[0]
            if p_total > 21:
                hand_result -= b
                round_win -= 1
            elif dealer_final > 21:
                hand_result += b
                round_win += 1
            elif p_total > dealer_final:
                hand_result += b
                round_win += 1
            elif p_total < dealer_final:
                hand_result -= b
                round_win -= 1
            # プッシュは0

        if round_win > 0:
            wins += 1
        elif round_win < 0:
            losses += 1
        else:
            pushes += 1

        net += hand_result
        bankroll += hand_result
        ratio = hand_result / bet if bet else 0.0
        sum_x += ratio
        sum_x2 += ratio ** 2
        sum_profit += ratio * ref_bet
        sum_profit2 += (ratio * ref_bet) ** 2
        if hand_result > 0:
            gross_win += hand_result
        elif hand_result < 0:
            gross_loss += -hand_result

        if bankroll > peak:
            peak = bankroll
        dd = peak - bankroll
        if dd > max_dd:
            max_dd = dd
        if bankroll <= 0 and not ruined:
            ruined = True
        if i % sample_every == 0:
            curve_sample.append(net)
        if config.bankroll_scaling and bankroll <= 0:
            hands_played = i + 1
            stopped_early = True
            break

    n = hands_played
    win_rate = wins / n
    push_rate = pushes / n

    # ハウスエッジ = -期待値/賭け金（%）。netはmin_bet単位、wageredも同様。
    house_edge = -(net / total_wagered) * 100 if total_wagered else 0.0
    return_pct = (net / total_wagered) * 100 + 100 if total_wagered else 100.0

    # 標準偏差（1手あたり、ベット正規化）
    mean = sum_x / n
    var = sum_x2 / n - mean ** 2
    std_dev = math.sqrt(var) if var > 0 else 0.0

    # P値（netが0より有意に大きいか、片側Z検定）
    if std_dev > 0:
        z = (sum_x / math.sqrt(n)) / std_dev if std_dev else 0
        # 標準正規CDF（誤差関数）
        p_value = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    else:
        p_value = 0.5

    # プロフィットファクター（総利益/総損失）
    # 旧実装は win_rate/loss_rate で近似していたが、これはベットサイズや
    # BJ配当(3:2)・ダブル・サレンダー等の非対称な損益額を一切反映せず、
    # 単純な勝ちハンド数/負けハンド数の比に等しくなってしまう。
    # ブラックジャックは（エッジが正でも）負けハンド数が勝ちハンド数を
    # 上回るのが通常なため、この近似は損益に関わらず常に1未満になる
    # 不具合があった。実際の勝ちハンド・負けハンドの金額を集計した
    # gross_win/gross_lossを使い、文字通りの総利益/総損失を算出する。
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf")

    # 破産確率（解析近似 Risk of Ruin）
    # bankrollは絶対額のため、mean/std_devを絶対額（同じ単位）で再計算する。
    # sum_x/std_dev はベット正規化値であり、可変ベット時にbankrollと単位が
    # 食い違うため使用しない（例: 加重平均edgeが正でも頻度の高い最小ベット時の
    # 不利な手が単純平均を負に引き込み、破産確率が常に100%になる不具合があった）。
    # さらにsum_profit/sum_profit2は実際のベット額ではなくref_bet（バンクロール
    # スケーリング適用前の設定値）で重み付けしており、bankroll_scaling時に
    # 「枯渇直前の不運な実現パス」だけで mean<=0 と判定され、同条件でも
    # シード次第で結果が大きく変わってしまう問題を緩和している。
    mean_profit = sum_profit / n
    var_profit = sum_profit2 / n - mean_profit ** 2
    std_profit = math.sqrt(var_profit) if var_profit > 0 else 0.0
    ruin_probability = _risk_of_ruin(mean_profit, std_profit, config.bankroll)

    return SimResult(
        num_hands=n,
        net_profit=net,
        win_rate=win_rate,
        push_rate=push_rate,
        house_edge=house_edge,
        std_dev=std_dev,
        profit_factor=profit_factor,
        ruin_probability=ruin_probability,
        p_value=p_value,
        max_drawdown=max_dd,
        total_wagered=total_wagered,
        return_pct=return_pct,
        bankroll_curve=curve_sample,
        curve_sample_every=sample_every,
        stopped_early=stopped_early,
    )


def _risk_of_ruin(mean_per_hand: float, std_per_hand: float,
                  bankroll_units: float) -> float:
    """Risk of Ruin の解析近似。

    RoR = exp(-2 * edge * bankroll / variance)
    （edgeとvarianceは同じベット単位で表現、ここではmin_bet単位）

    プレイヤー不利（mean<=0）の場合は事実上RoR=1。
    """
    if mean_per_hand <= 0:
        return 1.0
    variance = std_per_hand ** 2
    if variance <= 0:
        return 0.0
    exponent = -2.0 * mean_per_hand * bankroll_units / variance
    ror = math.exp(exponent)
    return min(1.0, max(0.0, ror))


if __name__ == "__main__":
    # BSのみ（カウンティングなし）小規模テスト
    rules = HouseRules(num_decks=6, soft17="H17", surrender="late")
    cfg = SimConfig(rules=rules, num_hands=200_000, seed=42)
    res = simulate(cfg)
    print(f"手数: {res.num_hands:,}")
    print(f"還元率: {res.return_pct:.2f}%  ハウスエッジ: {res.house_edge:.3f}%")
    print(f"勝率: {res.win_rate:.3f}  標準偏差: {res.std_dev:.3f}")
