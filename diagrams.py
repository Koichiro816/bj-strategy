"""
diagrams.py — 用語集の複雑なルール項目を視覚的に説明するためのmatplotlib図解。

テキストだけでは伝わりにくい「手順の順番」や「金額の違い」を、
タイムライン図・比較バーチャートとして描画する。app.py の用語集タブから
st.pyplot() で呼び出して使う。
"""

import japanize_matplotlib  # noqa: F401  matplotlibの日本語フォントをOS非依存で設定する
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
