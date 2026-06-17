"""
pdf_export.py — ベーシックストラテジー表のPDF出力

ハード/ソフト/ペアの3テーブルを色分けして1つのPDFに出力する。
TC overlay 適用済みテーブルにも対応。インデックスプレイ一覧も任意で添付。
reportlab を使用。
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A5, letter, landscape
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                Paragraph, Spacer, KeepTogether, PageBreak)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from rules import HouseRules
from strategy import generate_strategy_table
from index_plays import ILLUSTRIOUS_18, FAB_4, apply_tc_overlay


# アクション→色のマッピング（カラー）
ACTION_COLORS = {
    "H": colors.HexColor("#C8E6C9"),   # 薄緑（ヒット）
    "S": colors.HexColor("#FFCDD2"),   # 薄赤（スタンド）
    "D": colors.HexColor("#FFF9C4"),   # 薄黄（ダブル）
    "P": colors.HexColor("#BBDEFB"),   # 薄青（スプリット）
    "R": colors.HexColor("#CE93D8"),   # 紫（サレンダー）
}

# TC変更セル用の色（app.py の TC_CELL_BG に対応）
TC_CHANGED_BG   = colors.HexColor("#FFE0B2")
TC_CHANGED_TEXT = colors.HexColor("#BF360C")

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


# 横並びにする3テーブル分のレイアウトパディング（titled()内のLEFTPADDING+RIGHTPADDING）
_LAYOUT_H_PAD = 8  # 4 + 4
_N_TABLES = 3


def _table_col_widths(avail_width: float) -> list:
    """用紙の利用可能幅から、Hard/Soft/Pairsの3テーブルが重ならずに収まる
    列幅（Hand列 + アップカード10列）を計算する。

    A5など幅が狭い用紙では固定幅(22+16*10=182pt)では3テーブル合計が
    利用可能幅を超え表が重なって表示されるため、ページ幅に応じて動的に縮小する。
    """
    per_table = (avail_width - _N_TABLES * _LAYOUT_H_PAD) / _N_TABLES
    label_w = per_table * (22 / 182)
    upcard_w = (per_table - label_w) / 10
    return [label_w] + [upcard_w] * 10


def _build_grid_table(data_dict, row_labels, row_keys, color: bool,
                      table_type: str = "hard", changed: set = None):
    """テーブル用の2次元データとスタイルを生成する。

    row_labels : 各行の表示名
    row_keys   : 各行のキー（data_dict検索用）
    table_type : "hard" / "soft" / "pair"（changed セットのタプル形式に対応）
    changed    : apply_tc_overlay が返す changed_cells セット
    """
    if changed is None:
        changed = set()

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
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]

    for r_idx, (label, key) in enumerate(zip(row_labels, row_keys), start=1):
        row = [label]
        for c_idx, up in enumerate(UPCARDS, start=1):
            act = data_dict.get((key, up), "")
            row.append(act)
            is_changed = (table_type, key, up) in changed
            if is_changed:
                style_cmds.append(
                    ("BACKGROUND", (c_idx, r_idx), (c_idx, r_idx), TC_CHANGED_BG))
                style_cmds.append(
                    ("TEXTCOLOR", (c_idx, r_idx), (c_idx, r_idx), TC_CHANGED_TEXT))
                style_cmds.append(
                    ("FONTNAME", (c_idx, r_idx), (c_idx, r_idx), "Helvetica-Bold"))
            elif color and act in ACTION_COLORS:
                style_cmds.append(
                    ("BACKGROUND", (c_idx, r_idx), (c_idx, r_idx),
                     ACTION_COLORS[act]))
        rows.append(row)

    return rows, style_cmds


def _hard_table(strategy_table, color, changed=None):
    totals = list(range(17, 4, -1))  # 17..5 を上から
    labels = [str(t) for t in totals]
    return _build_grid_table(strategy_table["hard"], labels, totals, color,
                             table_type="hard", changed=changed)


def _soft_table(strategy_table, color, changed=None):
    # ソフト: total 20..13 を A+9..A+2 で表示
    totals = list(range(20, 12, -1))
    labels = [f"A,{t - 11}" for t in totals]
    return _build_grid_table(strategy_table["soft"], labels, totals, color,
                             table_type="soft", changed=changed)


def _pair_table(strategy_table, color, changed=None):
    ranks = [11, 10, 9, 8, 7, 6, 5, 4, 3, 2]
    labels = []
    for r in ranks:
        labels.append("A,A" if r == 11 else f"{r},{r}")
    return _build_grid_table(strategy_table["pair"], labels, ranks, color,
                             table_type="pair", changed=changed)


def _legend_flowable(styles, color, has_tc_changes: bool = False):
    """色分け凡例を作る（横1行レイアウトで省スペース化）。
    TC変更セルがある場合は追加エントリを表示。"""
    labels = [ACTION_LABELS[a] for a in ["H", "S", "D", "P", "R"]]
    if has_tc_changes:
        labels.append("* TC-adjusted")
    data = [labels]

    t = Table(data)
    cmds = [
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if color:
        for i, a in enumerate(["H", "S", "D", "P", "R"]):
            cmds.append(("BACKGROUND", (i, 0), (i, 0), ACTION_COLORS[a]))
    if has_tc_changes:
        n = len(labels) - 1
        cmds.append(("BACKGROUND", (n, 0), (n, 0), TC_CHANGED_BG))
        cmds.append(("TEXTCOLOR", (n, 0), (n, 0), TC_CHANGED_TEXT))
        cmds.append(("FONTNAME", (0, n), (0, n), "Helvetica-Bold"))
    t.setStyle(TableStyle(cmds))
    return t


def _index_table(rules: HouseRules):
    """Illustrious 18 + Fab 4 のインデックス一覧テーブル（ルール適用済み）。"""
    data = [["Hand", "Dealer", "Index(TC>=)", "Action"]]
    for (h, d, thr, act) in ILLUSTRIOUS_18 + FAB_4:
        # H17限定プレイ（15 vs A）はS17では非表示
        if h == "15" and d == "A" and rules.soft17 == "S17":
            continue
        # サレンダー不可の場合、Rインデックスは非表示
        if act == "R" and rules.surrender == "none":
            continue
        # エース対面サレンダー不可の場合は除外
        if act == "R" and d == "A" and not rules.surrender_vs_ace:
            continue
        # ENHC: dealer 10/A 対面のダブルインデックスは非表示
        dlabel = "A" if d in ("A", 11) else str(d)
        if not rules.dealer_peeks and act == "D" and dlabel in ("10", "A"):
            continue
        data.append([str(h), dlabel, f"{thr:+d}", act])

    t = Table(data, colWidths=[60, 50, 70, 50], repeatRows=1)
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
      strategy_table: generate_strategy_table の出力（ベースBS）
      rules         : HouseRules
      output_path   : 出力ファイルパス
      paper_size    : "A4"/"A5"/"Letter"
      color         : True=カラー, False=モノクロ
      include_index_plays : インデックス一覧を添付
      true_count    : True Count。0以外のとき TC overlay を適用してセルを橙色でハイライト
    """
    if paper_size not in PAPER_SIZES:
        raise ValueError(f"paper_size は A4/A5/Letter: {paper_size}")

    # TC overlay 適用
    changed: set = set()
    if true_count != 0:
        display_table, changed = apply_tc_overlay(strategy_table, true_count, rules)
    else:
        display_table = strategy_table

    page = landscape(PAPER_SIZES[paper_size])
    margin = 10 * mm
    doc = SimpleDocTemplate(
        output_path, pagesize=page,
        topMargin=margin, bottomMargin=margin,
        leftMargin=margin, rightMargin=margin,
    )
    avail_width = page[0] - 2 * margin

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Title"], fontSize=14)
    h_style = ParagraphStyle("h", parent=styles["Heading2"], fontSize=10)
    note_style = ParagraphStyle("note", parent=styles["Normal"], fontSize=7)

    elements = []
    page1 = []  # ベーシックストラテジー表+凡例: 1ページに収めるためKeepTogetherでまとめる
    page1.append(Paragraph("Blackjack Basic Strategy", title_style))
    page1.append(Paragraph(rules.short_description(), note_style))
    if true_count != 0:
        tc_note = f"TC = {true_count:+d} index plays applied"
        if changed:
            tc_note += f" ({len(changed)} cells adjusted, shown in orange)"
        page1.append(Paragraph(tc_note, note_style))
    page1.append(Spacer(1, 4 * mm))

    # 3テーブルを横並びにするため、それぞれTableを作りまとめる
    hard_rows, hard_style = _hard_table(display_table, color, changed)
    soft_rows, soft_style = _soft_table(display_table, color, changed)
    pair_rows, pair_style = _pair_table(display_table, color, changed)

    cw = _table_col_widths(avail_width)
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

    legend = _legend_flowable(styles, color, has_tc_changes=bool(changed))

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
    page1.append(layout)
    page1.append(Spacer(1, 4 * mm))
    page1.append(legend)
    elements.append(KeepTogether(page1))

    if include_index_plays:
        elements.append(PageBreak())
        elements.append(Paragraph("Illustrious 18 + Fab 4 (Hi-Lo Indexes)", h_style))
        elements.append(_index_table(rules))

    doc.build(elements)
    return output_path


if __name__ == "__main__":
    r = HouseRules()
    table = generate_strategy_table(r)
    # TC=0（ベースBS）
    path = generate_pdf(table, r, "bs_test.pdf", paper_size="A5", color=True)
    print("PDF生成（TC=0）:", path)
    # TC=+3 でのオーバーレイテスト
    path2 = generate_pdf(table, r, "bs_test_tc3.pdf", paper_size="A4", color=True,
                         true_count=3)
    print("PDF生成（TC=+3）:", path2)
