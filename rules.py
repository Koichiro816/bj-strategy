"""
rules.py — ハウスルール設定

ブラックジャックのハウスルールをデータクラスで定義する。
strategy.py / simulator.py / pdf_export.py / app.py から共通利用される。
"""

from dataclasses import dataclass


@dataclass
class HouseRules:
    """ブラックジャックのハウスルール定義。

    各属性はカジノテーブルのルールを表現する。
    EV計算・シミュレーションの両方で使用する。
    """

    num_decks: int = 6               # デッキ数（1/2/4/6/8）
    blackjack_pays: float = 1.5      # BJ配当: 3:2=1.5, 6:5=1.2
    dealer_peeks: bool = True        # US式（ディーラーBJ確認あり）
    soft17: str = "S17"              # "H17"=ソフト17ヒット, "S17"=スタンド
    double_allowed: str = "any"      # "any", "9-11", "10-11"
    double_after_split: bool = True  # スプリット後のダブル可否（DAS）
    split_aces: bool = True          # エースのスプリット可否
    draw_to_split_aces: bool = False # スプリットしたエースへの追加ヒット可否
    max_splits: int = 3              # 最大追加スプリット回数（3=最大4ハンド）
    surrender: str = "late"          # "none", "late", "early"
    surrender_vs_ace: bool = False   # エース対面でのサレンダー可否
    penetration: float = 0.75        # ペネトレーション（シミュレーション用）

    def __post_init__(self):
        """入力バリデーション。不正値は例外を送出する。"""
        if self.num_decks not in (1, 2, 4, 6, 8):
            raise ValueError(f"num_decks は 1/2/4/6/8 のいずれか: {self.num_decks}")
        if self.blackjack_pays not in (1.5, 1.2):
            raise ValueError(f"blackjack_pays は 1.5(3:2) か 1.2(6:5): {self.blackjack_pays}")
        if self.soft17 not in ("H17", "S17"):
            raise ValueError(f"soft17 は 'H17' か 'S17': {self.soft17}")
        if self.double_allowed not in ("any", "9-11", "10-11"):
            raise ValueError(f"double_allowed は 'any'/'9-11'/'10-11': {self.double_allowed}")
        if self.surrender not in ("none", "late", "early"):
            raise ValueError(f"surrender は 'none'/'late'/'early': {self.surrender}")
        if not (0.0 < self.penetration <= 1.0):
            raise ValueError(f"penetration は 0〜1: {self.penetration}")

    def can_double_total(self, total: int) -> bool:
        """指定ハード合計でダブルが許可されるか判定する。"""
        if self.double_allowed == "any":
            return True
        if self.double_allowed == "9-11":
            return 9 <= total <= 11
        if self.double_allowed == "10-11":
            return 10 <= total <= 11
        return False

    def short_description(self) -> str:
        """ルールの要約文字列を返す（PDF/UI表示用）。"""
        bj = "3:2" if self.blackjack_pays == 1.5 else "6:5"
        das = "DAS" if self.double_after_split else "NoDAS"
        surr = {"none": "NoSurr", "late": "LS", "early": "ES"}[self.surrender]
        surr_ace = "" if self.surrender_vs_ace else "/NoAce"
        return (f"{self.num_decks}D, {self.soft17}, {bj}, {das}, {surr}{surr_ace}, "
                f"Double:{self.double_allowed}")
