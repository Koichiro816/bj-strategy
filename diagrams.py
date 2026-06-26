"""
diagrams.py — 用語集の複雑なルール項目を視覚的に説明するためのmatplotlib図解。

テキストだけでは伝わりにくい「手順の順番」や「金額の違い」を、
タイムライン図・比較バーチャートとして描画する。app.py の用語集タブから
st.pyplot() で呼び出して使う。
"""

# 日本語フォント設定（OS非依存）。
# japanize_matplotlib は Python 3.12+ で distutils が削除されたため import に失敗することがある。
# その場合はシステムにインストールされた日本語フォント（Noto CJK / IPAex / Windows等）に切り替える。
import matplotlib
try:
    import japanize_matplotlib  # noqa: F401
except Exception:
    from matplotlib import font_manager as _fm
    _avail = {f.name for f in _fm.fontManager.ttflist}
    for _f in ("Noto Sans CJK JP", "IPAexGothic", "IPAPGothic", "TakaoPGothic",
               "VL PGothic", "Yu Gothic", "Meiryo", "MS Gothic"):
        if _f in _avail:
            matplotlib.rcParams["font.family"] = _f
            break
    matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


def _add_step_box(ax, x, y, w, h, text, facecolor, fontsize=8.3):
    box = FancyBboxPatch((x, y), w, h, facecolor=facecolor, edgecolor="#37474F",
                         linewidth=1.2, boxstyle="round,pad=0.02,rounding_size=0.06")
    ax.add_patch(box)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fontsize, color="#212121", linespacing=1.4)


def _add_arrow(ax, x1, y, x2):
    ax.annotate("", xy=(x2, y), xytext=(x1, y),
               arrowprops=dict(arrowstyle="-|>", color="#78909C", lw=1.6))


def holecard_timeline_figure():
    """HC / ANHC / ENHC で「ディーラーの2枚目がいつ配られ、いつ確認されるか」を
    3段のタイムライン図として比較する。
    """
    fig, ax = plt.subplots(figsize=(8.4, 4.4))
    ax.set_xlim(-1.6, 9.4)
    ax.set_ylim(0, 3.6)
    ax.axis("off")

    box_w, box_h, gap = 1.95, 0.85, 0.25

    rows = [
        ("HC\n（米国式）", 2.55, [
            ("①最初に2枚配る\n（表1枚＋裏1枚）", "#E3F2FD"),
            ("②裏を即チェック\nBJなら即終了", "#C8E6C9"),
            ("③プレイヤー\nが行動", "#FFF9C4"),
            ("④勝負・精算", "#E3F2FD"),
        ]),
        ("ANHC\n（豪州式）", 1.35, [
            ("①最初は\n表1枚だけ配る", "#E3F2FD"),
            ("②プレイヤー\nが行動", "#FFF9C4"),
            ("③ここで2枚目を\n引いて確認", "#E3F2FD"),
            ("④BJなら元の\n賭けだけ没収", "#FFE0B2"),
        ]),
        ("ENHC\n（欧州式）", 0.15, [
            ("①最初は\n表1枚だけ配る", "#E3F2FD"),
            ("②プレイヤー\nが行動", "#FFF9C4"),
            ("③ここで2枚目を\n引いて確認", "#E3F2FD"),
            ("④BJならダブル/\nスプリット分も没収", "#FFCDD2"),
        ]),
    ]

    for label, y, steps in rows:
        ax.text(-1.5, y + box_h / 2, label, ha="left", va="center",
                fontsize=10.5, fontweight="bold", color="#1A237E")
        x = 0.2
        prev_right = None
        for text, color in steps:
            if prev_right is not None:
                _add_arrow(ax, prev_right + 0.04, y + box_h / 2, x - 0.04)
            _add_step_box(ax, x, y, box_w, box_h, text, color)
            prev_right = x + box_w
            x += box_w + gap

    ax.set_title("ディーラーの2枚目（ホールカード）はいつ配られ、いつ確認される？",
                fontsize=12, fontweight="bold", color="#1A237E", pad=12)
    fig.tight_layout()
    return fig


def holecard_loss_example_figure():
    """「$100ベット→ダブルダウンで$200→ディーラーがBJ」という同一シナリオで、
    ANHCとENHCの没収額の違いを比較するバーチャート。
    HCではこの場面自体が起こらない（先にBJを確認しているため）ことを注記する。
    """
    fig, ax = plt.subplots(figsize=(6.2, 3.4))
    labels = ["ANHC\n（元の\\$100だけ没収）", "ENHC\n（\\$200を全額没収）"]
    values = [100, 200]
    colors = ["#FFE0B2", "#FFCDD2"]

    bars = ax.bar(labels, values, color=colors, edgecolor="#37474F",
                  linewidth=1.2, width=0.5)
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 6, f"\\${v}",
                ha="center", fontsize=13, fontweight="bold", color="#212121")

    ax.set_ylim(0, 230)
    ax.set_ylabel("ディーラーがBJだった場合の没収額")
    ax.set_title("例：\\$100ベット→ダブルダウンで\\$200に→直後にディーラーBJ",
                fontsize=10.5, fontweight="bold", color="#1A237E")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.text(0.5, -0.22, "※ HCではダブルする前にBJが確認されるため、この場面自体が起こりません。",
           ha="center", fontsize=8.5, color="#607D8B", transform=ax.transAxes)
    fig.tight_layout()
    return fig


def hilo_tag_figure():
    """Hi-Loのカードタグ付けを「低い/中間/高い」の3グループで色分けして見せる。"""
    fig, ax = plt.subplots(figsize=(8.0, 3.0))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 2.6)
    ax.axis("off")

    groups = [
        ("2・3・4・5・6", "+1", "#C8E6C9", "#1B5E20", "低いカード\n（出るほど有利）"),
        ("7・8・9", "0", "#ECEFF1", "#37474F", "中間\n（無視してよい）"),
        ("10・J・Q・K・A", "−1", "#FFCDD2", "#B71C1C", "高いカード\n（出るほど不利）"),
    ]
    w, gap = 2.85, 0.35
    x = 0.25
    for cards, tag, bg, fg, note in groups:
        box = FancyBboxPatch((x, 1.15), w, 1.0, facecolor=bg, edgecolor="#37474F",
                             linewidth=1.2, boxstyle="round,pad=0.02,rounding_size=0.08")
        ax.add_patch(box)
        ax.text(x + w / 2, 1.85, cards, ha="center", va="center",
                fontsize=10.5, fontweight="bold", color=fg)
        ax.text(x + w / 2, 1.40, f"タグ {tag}", ha="center", va="center",
                fontsize=12, fontweight="bold", color=fg)
        ax.text(x + w / 2, 0.55, note, ha="center", va="center",
                fontsize=9, color="#455A64", linespacing=1.4)
        x += w + gap

    ax.set_title("Hi-Lo：カードが出るたびに加えるタグ", fontsize=12,
                fontweight="bold", color="#1A237E", pad=10)
    fig.tight_layout()
    return fig


def running_to_true_count_figure():
    """実際に数枚のカードが出た様子からRCが積み上がり、残りデッキ数で割ってTCになる流れを示す。"""
    fig, ax = plt.subplots(figsize=(9.0, 3.6))
    ax.set_xlim(-0.3, 10.6)
    ax.set_ylim(0, 3.4)
    ax.axis("off")

    cards = [("5", "+1", "#C8E6C9", "#1B5E20"), ("K", "−1", "#FFCDD2", "#B71C1C"),
             ("2", "+1", "#C8E6C9", "#1B5E20"), ("9", "0", "#ECEFF1", "#37474F"),
             ("3", "+1", "#C8E6C9", "#1B5E20"), ("A", "−1", "#FFCDD2", "#B71C1C"),
             ("6", "+1", "#C8E6C9", "#1B5E20"), ("4", "+1", "#C8E6C9", "#1B5E20")]

    card_w, card_h, gap = 0.95, 1.15, 0.25
    x = 0.15
    rc = 0
    for card, tag, bg, fg in cards:
        box = FancyBboxPatch((x, 1.9), card_w, card_h, facecolor=bg, edgecolor="#37474F",
                             linewidth=1.1, boxstyle="round,pad=0.02,rounding_size=0.10")
        ax.add_patch(box)
        ax.text(x + card_w / 2, 1.9 + card_h * 0.62, card, ha="center", va="center",
                fontsize=13, fontweight="bold", color="#212121")
        ax.text(x + card_w / 2, 1.9 + card_h * 0.22, tag, ha="center", va="center",
                fontsize=9.5, fontweight="bold", color=fg)
        rc += int(tag.replace("−", "-"))
        ax.text(x + card_w / 2, 1.55, f"RC={rc:+d}", ha="center", va="center",
                fontsize=8.3, color="#607D8B")
        x += card_w + gap

    ax.annotate("", xy=(5.3, 0.95), xytext=(5.3, 1.75),
               arrowprops=dict(arrowstyle="-|>", color="#78909C", lw=1.8))
    _add_step_box(ax, 3.3, 0.05, 4.0, 0.85,
                 f"最終 RC = {rc:+d}　÷　残り3デッキ　＝　TC {rc/3:+.1f}",
                 "#FFE0B2", fontsize=10.5)

    ax.set_title("カードが出るたびにRCを更新し、残りデッキ数で割ってTCにする",
                fontsize=11.5, fontweight="bold", color="#1A237E", pad=10)
    fig.tight_layout()
    return fig


_ACTION_GREEN = "#C8E6C9"
_ACTION_RED = "#FFCDD2"


def index_play_figure():
    """最も有名なインデックスプレイ「16 vs 10」を例に、TCの境界で正解が切り替わる様子を示す。"""
    fig, ax = plt.subplots(figsize=(8.2, 2.6))
    ax.set_xlim(-2.2, 4.2)
    ax.set_ylim(0, 2.0)
    ax.axis("off")

    ax.annotate("", xy=(4.0, 1.0), xytext=(-2.0, 1.0),
               arrowprops=dict(arrowstyle="-|>", color="#37474F", lw=1.8))
    for tc in range(-2, 5):
        ax.plot([tc, tc], [0.92, 1.08], color="#37474F", lw=1.4)
        ax.text(tc, 0.7, f"{tc:+d}" if tc != 0 else "0", ha="center", fontsize=9.5, color="#37474F")
    ax.text(-2.0, 1.35, "TC", fontsize=10, color="#37474F", fontweight="bold")

    _add_step_box(ax, -2.05, 1.5, 1.85, 0.5, "TC < 0\nH（ヒット）", _ACTION_RED, fontsize=9.5)
    _add_step_box(ax, 0.15, 1.5, 1.85, 0.5, "TCが0以上\nS（スタンド）", _ACTION_GREEN, fontsize=9.5)
    ax.annotate("", xy=(0.0, 1.45), xytext=(0.0, 1.12),
               arrowprops=dict(arrowstyle="-|>", color="#BF360C", lw=2.0))

    ax.set_title("インデックスプレイの例：「16 vs 10」はTC=0で正解が切り替わる",
                fontsize=11.5, fontweight="bold", color="#1A237E", pad=12)
    fig.tight_layout()
    return fig


def insurance_ev_figure():
    """デッキ中の10点カードの割合が、保険の損益分岐点（1/3）をTCによって超えるかどうかを示す。"""
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    labels = ["TC = 0\n（ニュートラル）", "TC = +3\n（カード濃度UP）"]
    values = [4 / 13 * 100, 38.0]
    colors = ["#FFCDD2", "#C8E6C9"]

    bars = ax.bar(labels, values, color=colors, edgecolor="#37474F", linewidth=1.2, width=0.5)
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 1.2, f"{v:.1f}%",
                ha="center", fontsize=12.5, fontweight="bold", color="#212121")

    ax.axhline(100 / 3, color="#BF360C", linestyle="--", lw=1.6)
    ax.text(1.55, 100 / 3 + 0.8, "損益分岐点 33.3%\n（保険が2:1で\n払われるため）",
            fontsize=8.3, color="#BF360C", va="bottom", linespacing=1.3)

    ax.set_ylim(0, 46)
    ax.set_ylabel("残りデッキ中の「10点カード」の割合")
    ax.set_title("保険が得になるのは、10点カードの割合が33.3%を超えたとき",
                fontsize=10.8, fontweight="bold", color="#1A237E")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    return fig


def penetration_figure():
    """シューから配るデッキ量（ペネトレーション）の違いを3パターン並べて視覚化する。"""
    fig, ax = plt.subplots(figsize=(8.2, 3.4))
    ax.set_xlim(0, 10.4)
    ax.set_ylim(0, 3.4)
    ax.axis("off")

    patterns = [
        ("50%（浅い）", 0.50, "#FFCDD2"),
        ("75%（標準的）", 0.75, "#FFE0B2"),
        ("83%（深い）", 0.83, "#C8E6C9"),
    ]
    bar_w = 8.0
    for i, (label, frac, color) in enumerate(patterns):
        y = 2.5 - i * 1.05
        ax.text(-0.1, y + 0.4, label, ha="left", va="center", fontsize=10,
                fontweight="bold", color="#1A237E")
        outline = FancyBboxPatch((1.6, y), bar_w, 0.62, facecolor="#ECEFF1",
                                 edgecolor="#37474F", linewidth=1.2,
                                 boxstyle="round,pad=0.0,rounding_size=0.05")
        ax.add_patch(outline)
        dealt = FancyBboxPatch((1.6, y), bar_w * frac, 0.62, facecolor=color,
                               edgecolor="#37474F", linewidth=1.0,
                               boxstyle="round,pad=0.0,rounding_size=0.05")
        ax.add_patch(dealt)
        ax.text(1.6 + bar_w * frac / 2, y + 0.31, "配るゾーン", ha="center", va="center",
                fontsize=8.5, color="#212121")
        if frac < 0.97:
            ax.text(1.6 + bar_w * frac + (bar_w * (1 - frac)) / 2, y + 0.31,
                    "シャッフル\nカード以降", ha="center", va="center",
                    fontsize=7.3, color="#607D8B", linespacing=1.2)

    ax.set_title("ペネトレーション：シューの何%を配ってからシャッフルするか",
                fontsize=11.5, fontweight="bold", color="#1A237E", pad=10)
    fig.tight_layout()
    return fig
