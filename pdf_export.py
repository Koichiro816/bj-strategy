"""
pdf_export.py — ベーシックストラテジー表のPDF出力

ハード/ソフト/ペアの3テーブルを色分けして1つのPDFに出力する。
インデックスプレイ一覧も任意で添付。reportlab を使用。
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A5, letter, landscape
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                Paragraph, Spacer)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from rules import HouseRules
from strategy import generate_strategy_table
from index_plays import ILLUSTRIOUS_18, FAB_4


# アクション→色のマッピング（カラー）
ACTION_COLORS = {
    "H": colors.HexColor("#C8E6C9"),   # 薄緑（ヒット）
    "S": colors.HexColor("#FFCDD2"),   # 薄赤（スタンド）
    "D": colors.HexColor("#FFF9C4"),   # 薄黄（ダブル）
    "P": colors.HexColor("#BBDEFB"),   # 薄青（スプリット）
    "R": colors.HexColor("#CE93D8"),   # 紫（サレンダー）
}

ACTION_LABELS = {
    "H": "H (Hit)", "S": "S (Stand)", "D": "D (Double)",
    "P": "P (Split)", "R": "R (Surrender)",
}

PAPER_SIZES = {
    "A4": A4,
    "A5": A5,
    "Letter": letter,
}

UPCARDS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]


def _up_label(up):
    return "A" if up == 11 else str(up)


def _build_grid_table(data_dict, row_labels, row_keys, color: bool):
    """テーブル用の2次元データとスタイルを生成する。

    row_labels: 各行の表示名
    row_keys  : 各行のキー（data_dict検索用）
    """
    header = ["Hand"] + [_up_label(u) for u in UPCARDS]
    rows = [header]
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#37474F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#ECEFF1")),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
    ]

    for r_idx, (label, key) in enumerate(zip(row_labels, row_keys), start=1):
        row = [label]
        for c_idx, up in enumerate(UPCARDS, start=1):
            act = data_dict.get((key, up), "")
            row.append(act)
            if color and act in ACTION_COLORS:
                style_cmds.append(
                    ("BACKGROUND", (c_idx, r_idx), (c_idx, r_idx),
                     ACTION_COLORS[act]))
        rows.append(row)

    return rows, style_cmds


def _hard_table(strategy_table, color):
    totals = list(range(17, 4, -1))  # 17..5 を上から
    labels = [str(t) for t in totals]
    return _build_grid_table(strategy_table["hard"], labels, totals, color)


def _soft_table(strategy_table, color):
    # ソフト: total 20..13 を A+9..A+2 で表示
    totals = list(range(20, 12, -1))
    labels = [f"A,{t - 11}" for t in totals]
    return _build_grid_table(strategy_table["soft"], labels, totals, color)


def _pair_table(strategy_table, color):
    ranks = [11, 10, 9, 8, 7, 6, 5, 4, 3, 2]
    labels = []
    for r in ranks:
        labels.append("A,A" if r == 11 else f"{r},{r}")
    return _build_grid_table(strategy_table["pair"], labels, ranks, color)


def _legend_flowable(styles, color):
    """色分け凡例を作る。"""
    cells = [[ACTION_LABELS[a]] for a in ["H", "S", "D", "P", "R"]]
    data = [["凡例 / Legend"]]
    for a in ["H", "S", "D", "P", "R"]:
        data.append([ACTION_LABELS[a]])
    t = Table(data, colWidths=[120])
    cmds = [
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
    ]
    if color:
        for i, a in enumerate(["H", "S", "D", "P", "R"], start=1):
            cmds.append(("BACKGROUND", (0, i), (0, i), ACTION_COLORS[a]))
    t.setStyle(TableStyle(cmds))
    return t


def _index_table(rules):
    """Illustrious 18 + Fab 4 のインデックス一覧テーブル。"""
    data = [["Hand", "Dealer", "Index(TC>=)", "Action"]]
    for (h, d, thr, act) in ILLUSTRIOUS_18 + FAB_4:
        dlabel = "A" if d in ("A", 11) else str(d)
        data.append([str(h), dlabel, f"{thr:+d}", act])
    t = Table(data, colWidths=[60, 50, 70, 50])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#37474F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
    ]))
    return t


def generate_pdf(
    strategy_table: dict,
    rules: HouseRules,
    output_path: str,
    paper_size: str = "A5",
    color: bool = True,
    include_index_plays: bool = True,
    true_count: int = 0,
) -> str:
    """PDFを生成してパスを返す。

    引数:
      strategy_table: generate_strategy_table の出力
      rules         : HouseRules
      output_path   : 出力ファイルパス
      paper_size    : "A4"/"A5"/"Letter"
      color         : True=カラー, False=モノクロ
      include_index_plays : インデックス一覧を添付
      true_count    : 表示用TC（参考表示のみ）
    """
    if paper_size not in PAPER_SIZES:
        raise ValueError(f"paper_size は A4/A5/Letter: {paper_size}")

    page = landscape(PAPER_SIZES[paper_size])
    doc = SimpleDocTemplate(
        output_path, pagesize=page,
        topMargin=10 * mm, bottomMargin=10 * mm,
        leftMargin=10 * mm, rightMargin=10 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Title"], fontSize=14)
    h_style = ParagraphStyle("h", parent=styles["Heading2"], fontSize=10)
    note_style = ParagraphStyle("note", parent=styles["Normal"], fontSize=7)

    elements = []
    elements.append(Paragraph("Blackjack Basic Strategy", title_style))
    elements.append(Paragraph(rules.short_description(), note_style))
    if true_count != 0:
        elements.append(Paragraph(
            f"True Count = {true_count:+d} 反映済み（インデックスプレイ参照）",
            note_style))
    elements.append(Spacer(1, 4 * mm))

    # 3テーブルを横並びにするため、それぞれTableを作りまとめる
    hard_rows, hard_style = _hard_table(strategy_table, color)
    soft_rows, soft_style = _soft_table(strategy_table, color)
    pair_rows, pair_style = _pair_table(strategy_table, color)

    cw = [22] + [16] * 10
    hard_t = Table(hard_rows, colWidths=cw)
    hard_t.setStyle(TableStyle(hard_style))
    soft_t = Table(soft_rows, colWidths=cw)
    soft_t.setStyle(TableStyle(soft_style))
    pair_t = Table(pair_rows, colWidths=cw)
    pair_t.setStyle(TableStyle(pair_style))

    # 見出し付きでまとめる
    def titled(title, tbl):
        inner = Table([[Paragraph(title, h_style)], [tbl]])
        inner.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        return inner

    legend = _legend_flowable(styles, color)

    # 横3列: ハード / ソフト / ペア
    layout = Table([[
        titled("Hard Totals", hard_t),
        titled("Soft Totals", soft_t),
        titled("Pairs", pair_t),
    ]], colWidths=[None, None, None])
    layout.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(layout)
    elements.append(Spacer(1, 4 * mm))
    elements.append(legend)

    if include_index_plays:
        elements.append(Spacer(1, 4 * mm))
        elements.append(Paragraph("Illustrious 18 + Fab 4 (Hi-Lo Indexes)", h_style))
        elements.append(_index_table(rules))

    doc.build(elements)
    return output_path


if __name__ == "__main__":
    r = HouseRules()
    table = generate_strategy_table(r)
    path = generate_pdf(table, r, "bs_test.pdf", paper_size="A5", color=True)
    print("PDF生成:", path)
