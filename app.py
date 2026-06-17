"""
app.py — Streamlit ウェブアプリ（スマホ対応）
"""

import os
import tempfile

import pandas as pd
import streamlit as st

from rules import HouseRules
from strategy import generate_strategy_table, generate_ev_table
from index_plays import (ILLUSTRIOUS_18, FAB_4, get_active_indexes,
                         get_filtered_indexes, should_take_insurance, apply_tc_overlay)
from simulator import SimConfig, simulate
from pdf_export import generate_pdf

st.set_page_config(
    page_title="BJ Strategy & Simulator",
    page_icon="🃏",
    layout="wide",
)


def _check_password():
    """パスワード認証。secrets に PASSWORD が設定されていない場合は認証をスキップ。"""
    try:
        correct = st.secrets["PASSWORD"]
    except (KeyError, FileNotFoundError):
        return  # ローカル開発時はスキップ

    if st.session_state.get("authenticated"):
        return

    st.markdown(
        '<div style="max-width:360px;margin:80px auto;">', unsafe_allow_html=True)
    st.title("🃏 BJ Strategy")
    pw = st.text_input("パスワード", type="password", label_visibility="collapsed",
                       placeholder="パスワードを入力してください")
    if st.button("ログイン", use_container_width=True, type="primary"):
        if pw == correct:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()


_check_password()

UPCARDS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]

# アクション → 背景色 / テキスト色（印刷しやすいパステル）
CELL_COLORS = {
    "H": "#C8E6C9",
    "S": "#FFCDD2",
    "D": "#FFF9C4",
    "P": "#BBDEFB",
    "R": "#E1BEE7",
}
CELL_TEXT = {
    "H": "#1B5E20",
    "S": "#B71C1C",
    "D": "#E65100",
    "P": "#0D47A1",
    "R": "#6A1B9A",
}
TC_CELL_BG   = "#FFE0B2"
TC_CELL_TEXT = "#BF360C"


def _inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;600;700&display=swap');
    /* body への指定は継承で広がるが、Streamlit内部のMaterial Iconsフォントを上書きしない */
    body {
        font-family: 'Noto Sans JP', 'Hiragino Sans', 'Yu Gothic UI', sans-serif !important;
    }

    /* ─── ページ全体 ─── */
    .stApp { background: #FFFFFF !important; }
    .main .block-container {
        padding: 1.2rem 1.8rem 2rem 1.8rem !important;
        max-width: 1200px !important;
    }

    /* ─── 見出し ─── */
    h1 {
        color: #1A237E !important;
        font-size: 1.6rem !important;
        font-weight: 700 !important;
        letter-spacing: 0.02em !important;
        border-bottom: 3px solid #1565C0;
        padding-bottom: 6px !important;
        margin-bottom: 0.5rem !important;
    }
    h2 {
        color: #1A237E !important;
        font-size: 1.05rem !important;
        font-weight: 700 !important;
        border-left: 4px solid #1565C0;
        padding-left: 10px !important;
        margin: 0.8rem 0 0.4rem 0 !important;
    }
    h3 { color: #283593 !important; font-size: 0.95rem !important; }

    /* ─── タブ ─── */
    .stTabs [data-baseweb="tab-list"] {
        background: #F0F4F8 !important;
        border-bottom: 2px solid #BBDEFB !important;
        gap: 2px !important;
        padding: 4px 4px 0 4px !important;
        border-radius: 8px 8px 0 0 !important;
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent !important;
        color: #546E7A !important;
        padding: 8px 16px !important;
        font-weight: 600 !important;
        font-size: 0.87rem !important;
        border-radius: 6px 6px 0 0 !important;
        transition: all 0.15s !important;
    }
    .stTabs [data-baseweb="tab"]:hover {
        background: rgba(21,101,192,0.06) !important;
        color: #1565C0 !important;
    }
    .stTabs [aria-selected="true"] {
        color: #1565C0 !important;
        background: #FFFFFF !important;
        border-bottom: 2px solid #1565C0 !important;
        font-weight: 700 !important;
    }

    /* ─── エクスパンダー（stExpander のみターゲット） ─── */
    [data-testid="stExpander"] {
        border: 1px solid #CFD8DC !important;
        border-radius: 8px !important;
        margin-bottom: 0.8rem !important;
        position: relative !important;
    }
    [data-testid="stExpander"] details summary,
    [data-testid="stExpander"] > div > div:first-child {
        background: #EEF2FF !important;
        color: #1A237E !important;
        font-weight: 600 !important;
        list-style: none !important;
        cursor: pointer !important;
    }
    [data-testid="stExpander"] details summary::marker,
    [data-testid="stExpander"] details summary::-webkit-details-marker {
        display: none !important;
    }

    /* ─── アラート ─── */
    [data-testid="stAlert"] { border-radius: 8px !important; }

    /* ─── メトリクス ─── */
    [data-testid="metric-container"] {
        background: #F8F9FF !important;
        border: 1px solid #C5CAE9 !important;
        border-radius: 10px !important;
        padding: 12px 16px !important;
    }
    [data-testid="stMetricValue"] {
        color: #1565C0 !important;
        font-size: 1.3rem !important;
        font-weight: 700 !important;
    }
    [data-testid="stMetricLabel"] {
        color: #546E7A !important;
        font-size: 0.78rem !important;
    }

    /* ─── ボタン ─── */
    .stButton > button {
        background: linear-gradient(135deg, #1565C0, #0D47A1) !important;
        color: #fff !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
        padding: 9px 26px !important;
        box-shadow: 0 2px 8px rgba(13,71,161,0.35) !important;
        transition: all 0.15s !important;
    }
    .stButton > button:hover {
        box-shadow: 0 4px 14px rgba(13,71,161,0.5) !important;
        transform: translateY(-1px) !important;
    }

    /* ─── フォームラベル ─── */
    .stSelectbox > label, .stSlider > label, .stCheckbox > label,
    .stNumberInput > label, .stRadio > label {
        color: #37474F !important;
        font-size: 0.83rem !important;
        font-weight: 500 !important;
    }

    /* ─── キャプション ─── */
    small, [data-testid="stCaptionContainer"] {
        color: #78909C !important;
        font-size: 0.78rem !important;
    }

    /* ─── hr ─── */
    hr { border-color: #E3E8EF !important; }

    /* ─── Dataframe ─── */
    [data-testid="stDataFrame"] {
        border: 1px solid #E0E0E0 !important;
        border-radius: 8px !important;
        overflow: hidden !important;
    }
    </style>
    """, unsafe_allow_html=True)


_inject_css()


def _up_label(u):
    return "A" if u == 11 else str(u)


# ===========================================================================
# タイトル
# ===========================================================================
col_title, col_suit = st.columns([5, 1])
with col_title:
    st.title("🃏 Blackjack Strategy & Simulator")
with col_suit:
    st.markdown(
        '<div style="text-align:right;font-size:1.8rem;'
        'color:rgba(21,101,192,0.25);padding-top:10px;letter-spacing:3px;">♠♥♦♣</div>',
        unsafe_allow_html=True)

# ===========================================================================
# ハウスルール入力
# ===========================================================================
with st.expander("⚙️  ハウスルール設定（クリックで展開）", expanded=False):
    rc1, rc2, rc3 = st.columns(3)
    with rc1:
        st.markdown("**テーブル基本ルール**")
        num_decks = st.selectbox("デッキ数", [1, 2, 4, 6, 8], index=3)
        bj_pay_label = st.selectbox("BJ 配当", ["3:2 (1.5倍)", "6:5 (1.2倍)"])
        soft17_label = st.selectbox(
            "ディーラー ソフト17", ["S17 (スタンド)", "H17 (ヒット)"])
        hole_card_label = st.selectbox(
            "ホールカードルール",
            ["HC — US式（事前確認あり）",
             "ANHC — オーストラリア式（ノーホールカード）",
             "ENHC — 欧州式（ノーホールカード）"])
    with rc2:
        st.markdown("**ダブル・スプリット**")
        double_label = st.selectbox(
            "ダブルダウン条件",
            ["any（どの2枚でも）", "9-11", "10-11"])
        das = st.checkbox("スプリット後ダブル可 (DAS)", value=True)
        split_aces = st.checkbox("エースのスプリット可", value=True)
        draw_to_split_aces = st.checkbox("スプリットA後のヒット可", value=False)
        max_splits = st.number_input("最大スプリット追加回数", 1, 9, 3, 1)
    with rc3:
        st.markdown("**サレンダー・ペネトレーション**")
        surrender_label = st.selectbox(
            "サレンダー",
            ["late（レイトサレンダー）", "none（なし）", "early（アーリーサレンダー）"])
        surrender_vs_ace_ui = st.checkbox("エース対面でのサレンダー可", value=False)
        _pen_min = float(max(1, num_decks // 2))
        _pen_max = max(_pen_min, float(num_decks - 1))
        _pen_default_raw = num_decks * 0.75
        # 0.5刻みに丸めてスライダー範囲内に収める
        _pen_default = min(max(_pen_min, round(_pen_default_raw * 2) / 2), _pen_max)
        decks_dealt = st.slider(
            "シューから何デッキ配布でシャッフルするか（シミュ用）",
            min_value=_pen_min,
            max_value=_pen_max,
            value=_pen_default,
            step=0.5,
        )
        penetration = decks_dealt / num_decks
        st.caption(
            f"→ {num_decks}デッキ中 {decks_dealt:g}デッキ配布してシャッフル"
            f"（ペネトレーション {penetration:.0%}）")

blackjack_pays = 1.5 if bj_pay_label.startswith("3:2") else 1.2
soft17 = "S17" if soft17_label.startswith("S17") else "H17"
double_allowed = double_label.split("（")[0].strip()
surrender = surrender_label.split("（")[0].strip()
# ANHC: doubles/splits は dealer BJ から保護される → HC と同等の戦略で計算
# ENHC: ダブル/スプリット分も全没収 → dealer_peeks=False で BJ リスクを反映
dealer_peeks_ui = not hole_card_label.startswith("ENHC")

try:
    rules = HouseRules(
        num_decks=num_decks,
        blackjack_pays=blackjack_pays,
        soft17=soft17,
        double_allowed=double_allowed,
        double_after_split=das,
        split_aces=split_aces,
        draw_to_split_aces=draw_to_split_aces,
        max_splits=int(max_splits),
        surrender=surrender,
        surrender_vs_ace=surrender_vs_ace_ui,
        penetration=penetration,
        dealer_peeks=dealer_peeks_ui,
    )
except ValueError as e:
    st.error(f"ルール設定エラー: {e}")
    st.stop()

st.info(f"📋 現在のルール: **{rules.short_description()}**")



@st.cache_data(show_spinner=False)
def _cached_table(rules_key: tuple):
    r = HouseRules(**dict(rules_key))
    return generate_strategy_table(r)


rules_dict = dict(
    num_decks=num_decks, blackjack_pays=blackjack_pays, soft17=soft17,
    double_allowed=double_allowed, double_after_split=das,
    draw_to_split_aces=draw_to_split_aces, max_splits=int(max_splits),
    split_aces=split_aces, surrender=surrender,
    surrender_vs_ace=surrender_vs_ace_ui,
    penetration=penetration, dealer_peeks=dealer_peeks_ui,
)
strategy_table = _cached_table(tuple(sorted(rules_dict.items())))



# ===========================================================================
# HTML テーブル描画
# ===========================================================================
_HDR_BG  = "background:linear-gradient(135deg,#1A237E,#283593)"
_UPCD_BG = "background:linear-gradient(135deg,#283593,#1565C0)"
_HAND_BG = "background:#EEF2FF"
_EMPTY_BG = "#FAFAFA"
_BORDER  = "border:1px solid #CFD8DC"
# 左端のHand列をスマホ横スクロール時も固定表示するためのsticky指定
# （Excelの「ウィンドウ枠の固定」と同様、左の見出し列だけ追従させる）
_STICKY_COL = ("position:sticky;left:0;z-index:3;"
              "box-shadow:2px 0 4px -2px rgba(0,0,0,0.25);")


def _cell_style(act, is_changed):
    if is_changed:
        return (f"background:{TC_CELL_BG};color:{TC_CELL_TEXT};"
                "font-weight:700;")
    bg = CELL_COLORS.get(act, _EMPTY_BG)
    fg = CELL_TEXT.get(act, "#555555")
    return f"background:{bg};color:{fg};font-weight:600;"


def render_strategy_html(data_dict, row_keys, row_labels,
                         table_type="hard", changed=None, ev_dict=None):
    if changed is None:
        changed = set()
    html = [
        '<div style="overflow-x:auto;border-radius:8px;'
        'box-shadow:0 2px 10px rgba(0,0,0,0.1);">',
        '<table style="border-collapse:collapse;width:100%;'
        'font-size:13px;text-align:center;min-width:480px;">',
    ]
    # 行1: DEALER UPCARD スパン
    html.append(
        f'<tr>'
        f'<th style="{_HDR_BG};{_STICKY_COL}color:transparent;padding:4px;'
        f'{_BORDER};width:60px;"></th>'
        f'<th colspan="10" style="{_HDR_BG};color:#FFD700;padding:6px;'
        f'{_BORDER};font-size:0.76rem;font-weight:700;letter-spacing:0.14em;">'
        f'▼ &nbsp; D E A L E R &nbsp; U P C A R D &nbsp; ▼'
        f'</th></tr>'
    )
    # 行2: アップカード数字
    html.append('<tr>')
    html.append(
        f'<th style="{_HAND_BG};{_STICKY_COL}color:#546E7A;padding:5px 4px;'
        f'{_BORDER};font-size:0.75rem;font-weight:600;">Hand</th>')
    for u in UPCARDS:
        html.append(
            f'<th style="{_UPCD_BG};color:#E3F2FD;padding:5px 8px;'
            f'{_BORDER};font-weight:700;">{_up_label(u)}</th>')
    html.append('</tr>')
    # データ行
    for key, label in zip(row_keys, row_labels):
        html.append('<tr>')
        html.append(
            f'<td style="{_HAND_BG};{_STICKY_COL}color:#283593;font-weight:700;'
            f'padding:5px 6px;{_BORDER};white-space:nowrap;">{label}</td>')
        for u in UPCARDS:
            act = data_dict.get((key, u), "")
            is_chg = (table_type, key, u) in changed
            cs = _cell_style(act, is_chg)
            if ev_dict is not None:
                ev_val = ev_dict.get((key, u))
                ev_str = f"{ev_val:+.3f}" if ev_val is not None else ""
                cell_content = (
                    f'<div>{act}</div>'
                    f'<div style="font-size:0.62rem;font-weight:500;opacity:0.85;">'
                    f'{ev_str}</div>')
            else:
                cell_content = act
            html.append(
                f'<td style="{cs}padding:5px 4px;{_BORDER};">{cell_content}</td>')
        html.append('</tr>')
    html.append('</table></div>')
    return "".join(html)


def _table_card(title: str, html_inner: str) -> str:
    return (
        '<div style="background:#FAFBFF;'
        'border:1px solid #C5CAE9;border-radius:10px;'
        'padding:14px 16px;margin:10px 0;">'
        f'<div style="font-size:0.76rem;font-weight:700;color:#1565C0;'
        f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">'
        f'{title}</div>'
        f'{html_inner}</div>'
    )


def legend_html(show_tc=False):
    items = [
        ("H = ヒット",     CELL_COLORS["H"], CELL_TEXT["H"]),
        ("S = スタンド",   CELL_COLORS["S"], CELL_TEXT["S"]),
        ("D = ダブル",     CELL_COLORS["D"], CELL_TEXT["D"]),
        ("P = スプリット", CELL_COLORS["P"], CELL_TEXT["P"]),
        ("R = サレンダー", CELL_COLORS["R"], CELL_TEXT["R"]),
    ]
    parts = [
        '<div style="display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 10px 0;'
        'padding:8px 12px;background:#F0F4F8;'
        'border:1px solid #CFD8DC;border-radius:8px;">'
        '<span style="font-size:0.76rem;font-weight:700;color:#546E7A;'
        'align-self:center;margin-right:4px;">凡例</span>'
    ]
    for label, bg, fg in items:
        parts.append(
            f'<span style="background:{bg};color:{fg};padding:3px 10px;'
            f'border-radius:4px;font-size:0.8rem;font-weight:700;'
            f'border:1px solid rgba(0,0,0,0.08);">{label}</span>')
    if show_tc:
        parts.append(
            f'<span style="background:{TC_CELL_BG};color:{TC_CELL_TEXT};'
            f'padding:3px 10px;border-radius:4px;font-size:0.8rem;'
            f'font-weight:700;border:1px solid rgba(0,0,0,0.08);">★ TC 変更</span>')
    parts.append('</div>')
    return "".join(parts)


# ===========================================================================
# タブ
# ===========================================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 ベーシックストラテジー",
    "🎯 インデックスプレイ",
    "🔢 シミュレーター",
    "📄 PDF 出力",
    "📚 ルール＆用語集"])

# ---------------------------------------------------------------------------
# Tab 1: ベーシックストラテジー
# ---------------------------------------------------------------------------
with tab1:
    st.subheader("ベーシックストラテジー")

    tc1_col, tc2_col = st.columns([3, 1])
    with tc1_col:
        tab1_tc = st.select_slider(
            "True Count (TC)",
            options=list(range(-5, 6)),
            value=0,
            format_func=lambda x: f"TC {x:+d}",
        )
    with tc2_col:
        show_ev = st.checkbox("EV表示", value=False,
                              help="各マスに最善アクションのEV（期待値）を表示します。")

    if tab1_tc == 0:
        display_table = strategy_table
        changed_cells: set = set()
    else:
        display_table, changed_cells = apply_tc_overlay(strategy_table, tab1_tc, rules)

    ev_table = generate_ev_table(display_table, rules, tc=tab1_tc) if show_ev else None

    if should_take_insurance(tab1_tc):
        st.success(f"TC {tab1_tc:+d} → インシュランスを取る（TC ≥ +3）")

    st.markdown(legend_html(show_tc=bool(changed_cells)), unsafe_allow_html=True)
    if changed_cells:
        st.caption(
            f"★ {len(changed_cells)} セルが TC {tab1_tc:+d} のインデックスプレイで変更されています。")

    hard_totals = list(range(17, 4, -1))
    soft_totals = list(range(20, 12, -1))
    pair_ranks  = [11, 10, 9, 8, 7, 6, 5, 4, 3, 2]

    st.markdown(
        _table_card(
            "ハードハンド ( Hard Totals )",
            render_strategy_html(
                display_table["hard"], hard_totals,
                [str(t) for t in hard_totals],
                table_type="hard", changed=changed_cells,
                ev_dict=ev_table["hard"] if ev_table else None)),
        unsafe_allow_html=True)

    st.markdown(
        _table_card(
            "ソフトハンド ( Soft Totals )",
            render_strategy_html(
                display_table["soft"], soft_totals,
                [f"A,{t - 11}" for t in soft_totals],
                table_type="soft", changed=changed_cells,
                ev_dict=ev_table["soft"] if ev_table else None)),
        unsafe_allow_html=True)

    st.markdown(
        _table_card(
            "ペア ( Pairs )",
            render_strategy_html(
                display_table["pair"], pair_ranks,
                ["A,A" if r == 11 else f"{r},{r}" for r in pair_ranks],
                table_type="pair", changed=changed_cells,
                ev_dict=ev_table["pair"] if ev_table else None)),
        unsafe_allow_html=True)

    st.caption(
        "無限デッキ近似による解析的BS。6D 標準BSとの既知差異は補正済み。"
        " ENHC/ANHC 選択時はノーホールカードルールが自動反映されます。")
    if show_ev:
        st.caption(
            "EVは賭け金1単位あたりの期待値。Hi-Loのバランス特性を利用し、"
            "選択したTCに応じて残りデッキの構成比率を近似調整して計算しています"
            "（TCを変えるとEV値も変化します）。TCインデックス発動セルは変更後アクションのEVを表示します。")

# ---------------------------------------------------------------------------
# Tab 2: インデックスプレイ
# ---------------------------------------------------------------------------
with tab2:
    st.subheader("True Count 別インデックスプレイ（Hi-Lo）")
    tc2 = st.slider("True Count (TC)", -5, 5, 0, 1)

    if should_take_insurance(tc2):
        st.success(f"TC {tc2:+d} → インシュランスを取る（TC ≥ +3）")
    else:
        st.info(f"TC {tc2:+d} → インシュランスは取らない")

    active = get_active_indexes(tc2, rules)
    st.markdown(f"**TC {tc2:+d} で発動中のインデックス**")
    if active:
        df = pd.DataFrame(
            [(h, _up_label(d) if isinstance(d, int) else d, f"{thr:+d}", a)
             for (h, d, thr, a) in active],
            columns=["ハンド", "ディーラー", "発動TC", "アクション"])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.write("発動中のインデックスはありません（BS通りにプレイ）。")

    st.markdown("---")
    st.markdown("**Illustrious 18 + Fab 4 全一覧（現在のハウスルールに適用可能なもののみ）**")
    filtered_idx = get_filtered_indexes(rules)
    all_idx = pd.DataFrame(
        [(h, _up_label(d) if isinstance(d, int) else d, f"{thr:+d}", a)
         for (h, d, thr, a) in filtered_idx],
        columns=["ハンド", "ディーラー", "発動TC", "アクション"])
    st.dataframe(all_idx, use_container_width=True, hide_index=True)
    n_excluded = len(ILLUSTRIOUS_18) + len(FAB_4) - len(filtered_idx)
    if n_excluded > 0:
        st.caption(
            f"※ 現在のルール（{rules.short_description()}）では適用不可のため "
            f"{n_excluded} 件を除外しています。")

# ---------------------------------------------------------------------------
# Tab 3: シミュレーター
# ---------------------------------------------------------------------------
with tab3:
    st.subheader("モンテカルロ シミュレーター")
    col1, col2 = st.columns(2)
    with col1:
        num_hands = st.select_slider(
            "シミュレーション手数",
            options=[100_000, 500_000, 1_000_000, 5_000_000, 10_000_000],
            value=1_000_000)
        use_counting = st.checkbox("カウンティング戦略 (Hi-Lo)", value=False)
    with col2:
        min_bet = st.number_input("ミニマムベット", 1.0, 1000.0, 1.0)
        bankroll = st.number_input("バンクロール（min_bet 単位）", 10.0, 100000.0, 100.0)

    bet_spread = None
    if use_counting:
        st.markdown("**ベットスプレッド（TC 閾値 → 倍率）**")
        c1, c2, c3 = st.columns(3)
        with c1:
            m1 = st.number_input("TC ≥ +1 倍率", 1.0, 50.0, 2.0)
        with c2:
            m2 = st.number_input("TC ≥ +2 倍率", 1.0, 50.0, 4.0)
        with c3:
            m3 = st.number_input("TC ≥ +3 倍率", 1.0, 50.0, 6.0)
        bet_spread = {1: m1, 2: m2, 3: m3}

    if st.button("シミュレーション実行", type="primary"):
        cfg = SimConfig(
            rules=rules,
            num_hands=int(num_hands),
            use_counting=use_counting,
            bet_spread=bet_spread,
            min_bet=min_bet,
            bankroll=bankroll,
            strategy="counting" if use_counting else "basic",
            seed=None,
        )
        with st.spinner(f"{int(num_hands):,} 手をシミュレーション中..."):
            res = simulate(cfg)

        st.success("完了")
        m1c, m2c, m3c, m4c = st.columns(4)
        m1c.metric("還元率", f"{res.return_pct:.2f}%")
        m2c.metric("ハウスエッジ", f"{res.house_edge:.3f}%")
        m3c.metric("勝率", f"{res.win_rate * 100:.1f}%")
        m4c.metric("純利益（単位）", f"{res.net_profit:,.0f}")

        m5c, m6c, m7c, m8c = st.columns(4)
        m5c.metric("標準偏差", f"{res.std_dev:.3f}")
        m6c.metric("プロフィットファクター", f"{res.profit_factor:.3f}")
        m7c.metric("破産確率", f"{res.ruin_probability * 100:.1f}%")
        m8c.metric("最大 DD（単位）", f"{res.max_drawdown:,.0f}")

        st.caption(
            f"P 値（純利益 > 0 の有意性・片側）: {res.p_value:.4f} / "
            f"総賭け額: {res.total_wagered:,.0f} 単位")

        if res.bankroll_curve:
            st.line_chart(pd.DataFrame({"累積純利益": res.bankroll_curve}))

        if use_counting:
            st.info(
                "検証目安: カウンティング時の還元率 ≈ 102%（エッジ ≈ +2%）。"
                " min×100 バンクロール + 標準スプレッドで破産確率 ≈ 75%。")

# ---------------------------------------------------------------------------
# Tab 4: PDF 出力
# ---------------------------------------------------------------------------
with tab4:
    st.subheader("PDF 出力")
    pcol1, pcol2, pcol3 = st.columns(3)
    with pcol1:
        paper = st.selectbox("用紙サイズ", ["A5", "A4", "Letter"])
    with pcol2:
        color_mode = st.radio("カラー", ["カラー", "モノクロ"], horizontal=True)
    with pcol3:
        pdf_tc = st.number_input("True Count（参考表示）", -5, 5, 0)
    pdf_chk1, pdf_chk2 = st.columns(2)
    with pdf_chk1:
        include_idx = st.checkbox("インデックスプレイを含める", value=True)
    with pdf_chk2:
        pdf_show_ev = st.checkbox("EV表示", value=False,
                                  help="各マスにアクションとEV（期待値）を表示します。")

    if st.button("PDF 生成", type="primary"):
        try:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            tmp.close()
            generate_pdf(
                strategy_table, rules, tmp.name,
                paper_size=paper,
                color=(color_mode == "カラー"),
                include_index_plays=include_idx,
                true_count=int(pdf_tc),
                show_ev=pdf_show_ev,
            )
            with open(tmp.name, "rb") as f:
                pdf_bytes = f.read()
            os.unlink(tmp.name)
            st.success("PDF 生成完了")
            st.download_button(
                "PDF をダウンロード", data=pdf_bytes,
                file_name=f"bj_strategy_{rules.num_decks}D_{rules.soft17}.pdf",
                mime="application/pdf")
        except Exception as e:
            st.error(f"PDF 生成エラー: {e}")

# ---------------------------------------------------------------------------
# Tab 5: ルール＆用語集
# ---------------------------------------------------------------------------
with tab5:
    st.subheader("📚 ブラックジャック完全ガイド")
    st.caption("ゲームのルールから用語・ハウスルール設定・カードカウンティングまで、初心者から上級者まで一冊で分かるガイドです。")

    def term(name, body):
        with st.expander(name):
            st.markdown(body)

    # ── ブラックジャックの遊び方 ────────────────────────────────
    st.markdown("#### 🎮 ブラックジャックの遊び方（まずここから）")

    term("ゲームの目的", """\
ディーラー（カジノ側）と1対1で **21に近い手札合計** を競うカードゲームです。

- **21を超えた（バースト）ら即負け**
- プレイヤーが21以下で、ディーラーより合計が大きければ **勝ち**（賭け額と同額もらえる）
- 同点は引き分け（プッシュ）で賭けは返還

> **勝利条件まとめ**
> 1. 自分がバーストせず、ディーラーをバーストさせる
> 2. バーストしない範囲でディーラーより大きい数字を出す
> 3. 最初の2枚が「A＋10点札」＝ ブラックジャック！（ボーナス配当）
""")

    term("カードの点数（まずここを覚えよう）", """\
| カード | 点数 |
|--------|------|
| 2〜9 | そのままの数字（2は2点、9は9点） |
| 10・J（ジャック）・Q（クイーン）・K（キング） | すべて **10点** |
| A（エース） | **1点 または 11点**（どちらか有利な方を自動選択） |

**例:**
```
A + K  →  11 + 10 = 21（ブラックジャック！最強）
A + 6  →  11 + 6  = ソフト17（Aが11点として機能）
A + 6 + 8  →  1 + 6 + 8 = 15（バストを避けてAを1点に切り替え）
```

Aが11点として機能している手を **「ソフトハンド」**、1点のみの手を **「ハードハンド」** といいます。
""")

    term("1ゲームの流れ", """\
```
① プレイヤーがベット（賭け額を決める）
        ↓
② カードが配られる
   ├─ プレイヤー：2枚とも表向き
   └─ ディーラー：1枚表向き（アップカード）、1枚裏向き（ホールカード）
        ↓
③ プレイヤーがアクションを選ぶ
   ├─ H：ヒット（もう1枚引く）
   ├─ S：スタンド（引くのをやめてディーラーに任せる）
   ├─ D：ダブルダウン（賭けを2倍にして1枚だけ引く）
   ├─ P：スプリット（ペアを2つの手に分ける）
   └─ R：サレンダー（半額返してゲームを降りる）
        ↓
④ ディーラーが裏向きカードを公開し、ルールに従ってヒット/スタンド
   └─ 通常ルール：17以上でスタンド、16以下でヒット
        ↓
⑤ 比較・精算
   ├─ プレイヤーがバースト → 即負け（ディーラーの手関係なし）
   ├─ ディーラーがバースト → プレイヤー勝ち
   ├─ 数字が大きい方の勝ち
   └─ 同点 → 引き分け（プッシュ・賭け返還）
```

> ディーラーは必ずルール通りに動くだけで、選択の余地はありません。プレイヤーだけが判断できます。
""")

    # ── 基本用語 ────────────────────────────────────────────────
    st.markdown("#### 📖 基本用語")

    term("ブラックジャック（BJ）とは", """\
最初に配られた2枚が **A ＋ 10点札（10・J・Q・K）** の組み合わせ。21を1発で達成する最強の手です。

| 配当 | $100 賭けの払い | 解説 |
|------|----------------|------|
| **3:2（標準）** | **$150** | 賭け額の1.5倍が払われる |
| 6:5（要注意） | $120 | 1.2倍しかもらえない |

> ⚠️ **6:5テーブルは必ず避けること。** ハウスエッジが約1.4%悪化し、どれだけうまくプレイしても取り返せない差になります。
""")

    term("アップカード（Upcard）", """\
ディーラーが **表向き** に置いているカード1枚のことです。

```
ディーラーの手札:
┌─────┐  ┌─────┐
│  7  │  │ ??? │  ← 裏向き（ホールカード）
│  ♠  │  │     │
└─────┘  └─────┘
   ↑
アップカード（7）
プレイヤーはこれだけ見て判断する
```

ベーシックストラテジー表の **横軸（列）** がディーラーのアップカードです。
""")

    term("ハードハンド / ソフトハンド", """\
**ハードハンド（Hard）**: Aがない、またはAを1点として数えるしかない手

```
9 + 7 = 16  → ハード16（バストリスクあり）
A + 6 + K = 1 + 6 + 10 = 17  → ハード17（Aを11にしたら27でバストするため）
```

**ソフトハンド（Soft）**: Aを11点として使えている手

```
A + 6 = 11 + 6 = ソフト17  → ヒットしても絶対バーストしない！
A + 3 = 11 + 3 = ソフト14  → ダブルダウンのチャンスになることも
```

> ソフトハンドはどんな1枚を引いてもバーストしないため（引いた結果Aを1点に切り替えるだけ）、積極的にダブルやヒットができます。ベーシックストラテジー表の **「ソフトハンド」セクション** がこれに対応します。
""")

    term("バースト（Bust）", """\
手札の合計が **21を超えること**。バーストした瞬間に即負けとなり、賭け額が没収されます。

```
例: 9 + 8 = 17 （ここでヒットしたら）
    17 + 7 = 24  → バースト！ 即負け
```

> ⚠️ ディーラーがバーストしていても、プレイヤーが先にバーストしていたら負けです。
""")

    term("プッシュ（Push）/ 引き分け", """\
プレイヤーとディーラーの合計が **同点** の場合。賭けは返還されます（勝ちにも負けにもならない）。

```
例: プレイヤー 19 vs ディーラー 19  → プッシュ（賭け金は全額返還）
```
""")

    # ── アクション ───────────────────────────────────────────────
    st.markdown("#### 🃏 アクション（ベーシックストラテジー表の読み方）")

    st.markdown("""\
<div style="background:#EEF2FF;border:1px solid #C5CAE9;border-radius:8px;
padding:12px 16px;margin-bottom:10px;font-size:0.85rem;">
<strong>📊 表の読み方:</strong>
縦軸＝自分の手（合計）、横軸＝ディーラーのアップカード。
マスの文字（H / S / D / P / R）がその状況での最善アクションです。
</div>
""", unsafe_allow_html=True)

    term("H = ヒット（Hit）", """\
もう1枚カードを引くアクション。手が弱い時や、ディーラーが強い時に選びます。

- 手がバーストしなければ何度でもヒットできる
- 21を超えたらバースト（即負け）

**使いどころ例:** 自分が12、ディーラーが7 → ヒット（ディーラーは17を目指しており、12では勝てない）
""")

    term("S = スタンド（Stand）", """\
これ以上引かず、現在の手でディーラーと勝負します。

**使いどころ例:** 自分が18、ディーラーが6 → スタンド（18は強い、かつディーラーが弱い）

> ⚠️ 表中の **S はスタンド（Stand）** の略です。サレンダー（Surrender）は **R** で表します（混同注意）。
""")

    term("D = ダブルダウン（Double Down）", """\
ベットを **2倍** にして、カードを **1枚だけ** 引くアクション。強い手で大きく稼ぐ場面です。

```
例: 自分 A+2（ソフト13）、ディーラー5
    賭け $100 → $200 に増やして1枚だけ引く
    6が来て A+2+6 = ソフト19  → $200 獲得！
    Kが来て A+2+K = ハード13  → 引き続きディーラーのバーストを祈る
```

成功すれば2倍の利益。**絶対に負ける手では使わない**（9・10・11やソフトハンドでの好機に限定）のがポイントです。
""")

    term("P = スプリット（Split）", """\
同じ数字のペア（例: 8と8）を **2つの別々の手** に分けるアクション。同額のベットを追加する必要があります。

```
8,8（合計16 = 最弱の手のひとつ）をスプリット

     元の手             スプリット後
  ┌─────┬─────┐      ┌─────┐   ┌─────┐
  │  8  │  8  │  →  │  8  │   │  8  │  ← それぞれに1枚引いて続行
  └─────┴─────┘      └─────┘   └─────┘
  合計16（弱い）        各8から再スタート（強くなる可能性大）
```

**原則:**
- **A,A と 8,8 は必ずスプリット**
- **10,10 はスプリットしない**（合計20は最強クラスなので崩さない）
""")

    term("R = サレンダー（Surrender）", """\
ベットの **半分（−0.50）** を失う代わりに、そのゲームを降りるアクション。

「どう転んでも大負けする手」でダメージを半分に抑えるのが目的です。

| 判断基準 | 説明 |
|----------|------|
| スタンドEV < −0.50 | サレンダー（EV=−0.50）の方がマシ |
| スタンドEV ≥ −0.50 | スタンドかヒットを選ぶ |

**典型的なサレンダー場面（6D S17）:**

| 自分の手 | ディーラー | 理由 |
|----------|-----------|------|
| 16 | 10 | スタンドEV≈−0.54、ヒットEV≈−0.54 → サレンダー−0.50が最良 |
| 15 | 10 | スタンドEV≈−0.54 → サレンダーの方がEVが高い |

**レイトサレンダー（Late）**: ディーラーがBJでないことを確認してから降参（一般的なルール）
**アーリーサレンダー（Early）**: 確認前に降参（非常にレア、プレイヤーに超有利）
""")

    term("DAS（Double After Split / スプリット後ダブル）", """\
ペアをスプリットした後、さらにダブルダウンできるルール。

```
例: 8,8 をスプリット
    → 一方の8に「3」が来て合計11
    → DASありなら、そこからダブルダウン可能！ 賭けをさらに倍に
```

- **DASあり**: ハウスエッジを約 **−0.14%** 改善（プレイヤー有利）
- できるだけDASありのテーブルを選ぶべき
""")

    # ── ハウスルール設定（設定パネルと同じ順番） ──────────────
    st.markdown("#### ⚙️ ハウスルール設定ガイド")
    st.markdown("""\
<div style="background:#F3F4F8;border:1px solid #C5CAE9;border-radius:8px;
padding:10px 14px;margin-bottom:10px;font-size:0.84rem;">
上部「ハウスルール設定」パネルの各項目を、パネルと同じ順番で解説します。
</div>
""", unsafe_allow_html=True)

    st.markdown("##### テーブル基本ルール")

    term("デッキ数（1 / 2 / 4 / 6 / 8 デッキ）", """\
1回のゲームで使うトランプの組数です。デッキ数が少ないほどプレイヤーに有利。

| デッキ数 | 6D比のエッジ差 | 特徴 |
|---------|-------------|------|
| 1デッキ | **−0.48%（最有利）** | 手配り（ピッチゲーム） |
| 2デッキ | −0.19% | 手配り |
| 4デッキ | −0.06% | シューゲーム |
| **6デッキ** | **±0%（基準）** | **世界で最も一般的** |
| 8デッキ | +0.02% | 大型カジノ |

デッキが少ない → カードの偏りが大きい → ダブルやBJ出現率の有利性が高まる。
また **デッキが少ないほどカードカウンティングの効果も大きい**。
""")

    term("BJ配当（3:2 vs 6:5）", """\
ブラックジャック（初期2枚でA＋10点札）が出た時の払い率。

| 配当 | $100 賭けの払い | ハウスエッジへの影響 |
|------|----------------|-------------------|
| **3:2（標準・推奨）** | **$150** | 基準 |
| 6:5（要注意） | $120 | **+1.39% 悪化** |

> 🚫 **6:5テーブルには絶対に座らないこと。** 配当の差が小さく見えますが、ハウスエッジ1.4%悪化はカウンティングでも取り返せません。
""")

    term("ディーラー ソフト17（S17 / H17）", """\
ディーラーが **ソフト17**（A+6など、Aを11点として合計17になる手）の時に何をするかのルール。

| ルール | ディーラー行動 | プレイヤーへの影響 |
|--------|-------------|------------------|
| **S17（スタンド）** | ソフト17でスタンド | **プレイヤー有利（約−0.22%）** |
| H17（ヒット） | ソフト17でヒット | +0.22% 不利 |

H17では、ディーラーが A+6（ソフト17）から追加で4を引いて A+6+4=ソフト21、なんてことが起きます。ディーラーが手を強化できる分プレイヤーに不利。
""")

    term("ホールカードルール（HC / ANHC / ENHC）", """\
ディーラーの2枚目（裏向きカード）の扱い方。プレイヤーのエッジに大きく影響します。

---

**HC（Hole Card = 米国式）**

ゲーム開始直後にディーラーが裏向きカードをこっそり確認し、BJ（A＋10点札）なら即ゲーム終了。

- プレイヤーは「ディーラーがBJでない」ことを前提にアクションを選べる
- Hard 11 vs A = **ダブル**（BJ確認済みなのでリスクなし）
- 北米・日本のほとんどのカジノで採用。最もプレイヤーに有利

---

**ANHC（Australian No Hole Card = オーストラリア式）**

最初から1枚しか配らず、プレイヤーのアクション終了後にディーラーが2枚目を引く。

- ディーラーBJ時に没収されるのは **元の賭けのみ**（ダブル・スプリットの追加賭け分は返還）
- この「ダブル/スプリット保護」があるため、戦略は**HCとほぼ同一**

---

**ENHC（European No Hole Card = 欧州式）**

ディーラーBJ時にダブルダウン・スプリットの追加賭け分も **全額没収**。

| ハンド | HC での正解 | ENHC での正解 | 理由 |
|--------|------------|-------------|------|
| Hard 11 vs A | **D（ダブル）** | H（ヒット） | BJ確率4/13でダブルEVが急落 |
| Hard 14 vs 10 | H（ヒット） | **R（サレンダー）** | BJリスクでスタンドEV < −0.50 |
| Pair 8,8 vs A | **P（スプリット）** | H（ヒット） | スプリットEV急落（−0.85 vs ヒット−0.64） |

> ENHCではディーラー10/A対面のダブルに関するTCインデックスも自動的に無効化されます。
""")

    st.markdown("##### ダブルダウン・スプリット")

    term("ダブルダウン条件（any / 9-11 / 10-11）", """\
最初の2枚のどの合計値でダブルダウンできるかのルール。

| 設定 | 対象合計 | ハウスエッジへの影響 |
|------|---------|-------------------|
| **any（推奨）** | すべての合計 | 基準（最も有利） |
| 9-11 | 9・10・11のみ | +0.09% 悪化 |
| 10-11 | 10・11のみ | +0.18% 悪化 |

`any` ルールなら、A+6（ソフト17）vs ディーラー3〜6 などでもダブルが有効になります。
""")

    term("スプリット後ダブル（DAS）", """\
ペアをスプリットした後、さらにダブルダウンできるか。

- **DASあり（推奨）**: ハウスエッジを約 **−0.14%** 改善（有利）
- DASなし: スプリット後はヒット/スタンドのみ

例: 8,8をスプリット → 一方に3が来て合計11 → DASありならそこでダブル可能！
""")

    term("エースのスプリット可否", """\
A,Aペアを2つに分けられるか。

- **可（推奨）**: A,Aは最強のペア。各Aに10系が来れば21に近い手が2つに
- ほぼ全てのカジノで可能。不可のテーブルは避けるべき

通常、スプリット後のAに引ける枚数は **1枚のみ**（A+10=21でもBJ扱いにはならない）。
""")

    term("スプリットA後のヒット可否", """\
スプリットしたエースに **追加でヒット** できるか。

- **不可（標準）**: スプリットA後は1枚のみ追加
- 可（非常にレア）: ハウスエッジが約 **−0.19%** 下がる有利なルール

ラスベガスの一部テーブルや特定条件で提供されることがあります。
""")

    term("最大スプリット追加回数", """\
同じランクのカードが来た時に何回まで再スプリットできるか。

- **標準: 3回追加**（最大4ハンド同時進行）
- 多いほどプレイヤーに有利

```
例: 8,8 → スプリット（2ハンド）
    → 一方にまた8が来る → 再スプリット（3ハンド）
    → 最大で4ハンドを同時に進行できる
```
""")

    st.markdown("##### サレンダー")

    term("サレンダー（late / none / early）", """\
ゲーム開始後、1アクションも取らずに **賭けの半分を回収して降参** するオプション。

| 種別 | タイミング | ハウスエッジへの影響 |
|------|-----------|------------------|
| **レイトサレンダー（Late）** | ディーラーBJ確認後 | 約 −0.08%（有利） |
| なし（None） | − | サレンダー不可 |
| アーリーサレンダー（Early） | BJ確認前 | 約 −0.39%（非常に有利・レア） |

**サレンダーEV = −0.50**（賭けの半分を失う）。スタンドEVが −0.50 を下回る絶望的な手でのみ有効。

代表的なサレンダー場面（6D S17 レイトサレンダー）:
- Hard 15 または 16 vs ディーラー 10
- Hard 16 vs ディーラー 9（ルールによる）

> **重要**: スタンドEV < −0.50 の場合、ヒットよりも**サレンダーが常に優先**されます。
""")

    term("エース対面でのサレンダー可否", """\
ディーラーのアップカードがAの時にサレンダーできるか（レイトサレンダー前提）。

- **不可（デフォルト）**: ディーラーA時はサレンダー不可
- 可: BJ非確認後にサレンダー可。ハウスエッジ約 **−0.03%** 追加改善

HC（US式）では、ディーラーがまずBJを確認し、非BJが判明してからサレンダーを受け付けます。
""")

    st.markdown("##### ペネトレーション")

    term("ペネトレーション（シミュレーション用）", """\
シュー（複数デッキを格納する容器）から **何デッキ分配布してからシャッフルするか**。

```
6デッキシューのイメージ:
┌──────────────────────────────────────────────┐
│ ████████████████████████████░░░░░░░░░░░░░░░░ │
│  ← 配布ゾーン（5デッキ分）  ↑シャッフルカード  │
└──────────────────────────────────────────────┘
                              ここで止める = ペネトレーション83%
```

| ペネトレーション | 6デッキ換算 | カウンティング精度 |
|---------------|------------|----------------|
| 50% | 3デッキ配布 | 低（TCが収束しにくい） |
| 75% | 4.5デッキ配布 | 中（現実的な標準） |
| 83% | 5デッキ配布 | 高 |

ペネトレーションが高い（多く配る）ほどカウンターのアドバンテージが上がります。

> **CSM（連続シャッフルマシン）= 実質ペネトレーション0%** でカウンティング完全無効化。
""")

    # ── カードカウンティング ─────────────────────────────────────
    st.markdown("#### 🔢 カードカウンティング")

    term("ベーシックストラテジー（BS）", """\
カードの組み合わせごとに数学的に最善のアクションを示した早見表。

BSを完璧に実行するだけで、6D S17テーブルのハウスエッジを約 **0.4〜0.5%** に抑えられます。

| 戦略レベル | ハウスエッジ目安 |
|-----------|----------------|
| 感覚でプレイ | 約 2〜4% |
| **BS完璧実行** | **約 0.4〜0.5%** |
| BS ＋ カウンティング ＋ ベットスプレッド | **−1〜−2%（プレイヤー有利！）** |

> このアプリの「ベーシックストラテジー」タブが、設定したハウスルールに合わせた最適なBSを表示します。
""")

    term("ハウスエッジ（House Edge）", """\
カジノが長期的に得る期待利益の割合。数字が小さい（低い）ほどプレイヤーに有利。

```
ハウスエッジ 0.5% = 100円賭けると長期的に99.5円戻る（還元率99.5%）
```

スロットは約3〜5%、ルーレット（ゼロあり）は約2.7%。BSを使えばブラックジャックはカジノゲームの中で最もプレイヤーに優しい部類です。
""")

    term("Hi-Lo カードカウンティング", """\
最も有名なカウンティング手法。各カードにタグ（＋1/0/−1）をつけ、デッキの「残りカードの濃さ」を追跡します。

```
カード:    2    3    4    5    6  │  7    8    9  │  10   J    Q    K    A
タグ:     +1   +1   +1   +1   +1 │   0    0    0  │  -1   -1   -1   -1   -1
         ←── 低いカード（有利） ──│── 中間（無視）──│──── 高いカード（不利） ────→
```

**カードが出るたびにタグを加算する:**

- 低いカード（2〜6）が出た → **＋1**（高いカードがデッキに残った！ プレイヤー有利）
- 中間（7〜9）→ **0**（無視してよい）
- 高いカード（10〜A）が出た → **−1**（高いカードが消えた）

この累積値を「ランニングカウント（RC）」といいます。
""")

    term("ランニングカウント（RC）/ トゥルーカウント（TC）", """\
**RC（Running Count）**: Hi-Loの累積値。ゲームを通じて更新し続ける数字。

**TC（True Count）**: RC ÷ 残りデッキ数。複数デッキ環境での補正値。

```
例1: RC = +12、残り3デッキ  →  TC = 12 ÷ 3 = +4（非常に有利！）
例2: RC = +12、残り6デッキ  →  TC = 12 ÷ 6 = +2（やや有利）
```

| TC | 状況 | 推奨行動 |
|----|------|---------|
| −2以下 | デッキに小カードが多い | 最小ベット |
| 0前後 | 中立 | 最小ベット、BSどおり |
| +1〜+2 | やや有利 | ベットを増やし始める |
| +3以上 | 大きく有利 | ベット最大、インシュランスも検討 |
""")

    term("インシュランス（Insurance）", """\
ディーラーのアップカードが **A** の時に提供されるサイドベット。

「ディーラーのホールカードが10（＝BJ）に賭ける」オプション。当たれば 2:1 払い。

- **基本的には取るべきでない**（長期的には損をする）
- **TC ≥ +3 の時のみ** 数学的に有利（Illustrious 18 の第1位）

> このアプリでは TC ≥ +3 になると自動的にインシュランスを勧める通知が表示されます。
""")

    term("Illustrious 18 / Fab 4", """\
カウンターが覚えるべき **BSからの逸脱プレイ** のリスト。TCに応じてアクションを変えます。

**Illustrious 18（18のプレイ変化）**: ベットとプレイで最も期待値が上がる18手
**Fab 4（4のサレンダー変化）**: TCに応じてサレンダーすべき4手

主要な例:

| ハンド | ディーラー | BS | TC条件 | インデックスプレイ |
|--------|-----------|-----|--------|------------------|
| 16 | 10 | H | TC ≥ 0 | **S（スタンド）** |
| 9 | 2 | H | TC ≥ +1 | **D（ダブル）** |
| インシュランス | A | なし | TC ≥ +3 | **取る** |
| 15 | 10 | H/S | TC ≥ +4 | **R（サレンダー）** |

「インデックスプレイ」タブで全一覧を確認できます。
""")

    term("ベットスプレッド（Bet Spread）", """\
TCに応じてベット額を変える戦略。高TCで大きく、低TCで小さく賭けます。

| TC | ベット倍率（典型例） |
|----|-------------------|
| 0以下 | 1倍（最小ベット） |
| +1 | 2倍 |
| +2 | 4倍 |
| +3以上 | 6倍 |

スプレッドが大きいほど期待値は上がりますが、カジノにカウンターとして見破られやすくなります。
""")

    term("TC が高い（+）/ 低い（−）時の戦略変化", """\
**TC が高い（+） = デッキに10点札・Aが多く残っている**

- ヒットするとバストしやすい（プレイヤーもディーラーも10が来る確率が高い）
- 「16 vs 10」などで **スタンドに切り替える**（Illustrious 18）
- ただし、サレンダーがあれば **R（EV=−0.50）が常に優先**（スタンドEV≈−0.54 より良い）
- 「9 vs 2」（TC≥+1）、「11 vs A」（TC≥+1、HC限定）などでダブルが有利になる

---

**TC が低い（−） = デッキに小さいカード（2〜6）が多く残っている**

- ヒットしてもバストしにくい → 積極的にヒット
- 「13 vs 2」（TC≤−1）、「12 vs 5」（TC≤−2）などで **ヒットに切り替える**

---

**ENHC でのTC注意事項**

ENHCではディーラーBJを事前確認しないため、**dealer 10/A 対面のダブルインデックスは無効化**されます。

| インデックス | 発動TC | HC | ENHC |
|------------|-------|-----|------|
| Hard 11 vs A | TC≥+1 | D（ダブル） | 無効（H） |
| Hard 10 vs A | TC≥+4 | D（ダブル） | 無効（H） |
| Hard 10 vs 10 | TC≥+4 | D（ダブル） | 無効（H） |

dealer 2/7 など BJ リスクのないアップカード対面のダブルインデックス（9 vs 2 など）はENHCでも有効です。
""")

    # ── リスク管理 ──────────────────────────────────────────────
    st.markdown("#### 📊 リスク管理")

    term("破産確率（Risk of Ruin / RoR）", """\
バンクロールを全て失う確率。

解析近似: `RoR ≈ exp(−2 × edge × bankroll / variance)`

| バンクロール | エッジ+2% | エッジ+1% |
|------------|----------|----------|
| 50単位 | 約 67% | 約 82% |
| 100単位 | 約 45% | 約 67% |
| 300単位 | 約 9% | 約 30% |

> 🎯 **鉄則**: バンクロール＝失っても良い金額として管理すること。ミニマム×100でも破産リスクは相当高いです。
""")

    term("プロフィットファクター（Profit Factor / PF）", """\
総利益 ÷ 総損失。統計的な収益安定性の指標。

- PF = 1.5 → 勝ちの合計が負けの合計の1.5倍
- PF ≥ 1.0 → 収益がプラス
- PF < 1.0 → 収益がマイナス

シミュレーター実行後の結果画面で確認できます。
""")

    term("ハウスエッジ vs 還元率（RTP）", """\
同じ数字の2つの見方です。

```
ハウスエッジ 0.5%  =  還元率 99.5%
（100円賭けると長期的に99.5円戻ってくる）

カウンティング + スプレッドでエッジを +2% に反転
=  還元率 102%
（長期的に賭けた額より2%多く戻る = 期待値プラス）
```
""")

    term("バックオフ / 出禁（Backoff / Barring）", """\
カジノがカウンターと判断したプレイヤーを排除すること。カジノの合法的な権利です。

| 段階 | 内容 |
|------|------|
| バックオフ | 特定ゲーム（BJ）のみプレイ禁止 |
| フラットベット強制 | ベット変動を禁止（常に同額のみ） |
| 出禁 | 施設全体への入場禁止 |

不自然なベット変動、大勝ち、アップカード確認時の視線パターンなどで判断されます。
""")

    term("CSM（コンティニュアス シャッフル マシン）", """\
使ったカードをその場でデッキに戻す自動シャッフル機。

- カウンティングが **実質不能**（カードが常にランダム）
- アミューズカジノには費用面から未導入の店舗も多い
- CSMテーブルでは純粋なBS（ハウスエッジ0.4〜0.5%）のみ有効
""")

    term("ブラックジャック（BJ）とは",
         "最初に配られた2枚でAce + 10 or 絵札の21を達成すること。"
         "**3:2** なら賭け $100 に対して $150 が払われる（有利）。"
         "**6:5** は $120 払いで、ハウスエッジが約+1.4%増える。絶対に避けるべきテーブル。")
    term("アップカード（Upcard）",
         "ディーラーが**表向き**に見せている1枚のカード。プレイヤーはここだけを見てアクションを決める。"
         "ディーラーのもう1枚（ホールカード）は裏向き。")
    term("ホールカード（Hole Card）/ HC・ANHC・ENHC",
         "**HC（Hole Card = 米国式）**: ゲーム開始時にディーラーが裏向きカードをこっそり確認し、"
         "BJ なら即座にゲームを終了させる。プレイヤーにとって最も有利なルール。\n"
         "**ANHC（オーストラリア式）**: ホールカードなし。ディーラーBJでも元の賭けのみ没収。\n"
         "**ENHC（欧州式）**: ホールカードなし、かつダブル・スプリット分も没収（最も不利）。\n"
         "→ ENHCではディーラーAce対面でのダブル（例: Hard 11）が著しく不利になります。")
    term("ハードハンド / ソフトハンド",
         "**ハードハンド**: Aceがない、またはAceを1として数えるしかない手。例: 9+7=ハード16。\n"
         "**ソフトハンド**: Aceを11として数えられる手。例: A+6=ソフト17。"
         "バストしにくく、ダブル機会が多い有利な手。")
    term("バースト（Bust）",
         "手札の合計が21を超えること。その時点で即負け"
         "（ただしディーラーが先にバーストしていれば勝利）。")
    term("プッシュ（Push）",
         "プレイヤーとディーラーが同点。賭けは返還される（引き分け）。")

    st.markdown("#### アクション（表の見方）")
    term("H = ヒット",
         "もう1枚引く。合計が弱い時や、ディーラーが強い時に選ぶ。")
    term("S = スタンド",
         "引かずに現在の手でディーラーと勝負する。"
         "※凡例の **S** は Stand（スタンド）の略。Surrender（サレンダー）は **R** で表します。")
    term("D = ダブルダウン",
         "ベットを2倍にして、カードを**1枚だけ**引く。9・10・11などの強い手で有利。"
         "成功すれば大きな利益、失敗すれば2倍の損失。")
    term("P = スプリット",
         "同じ数字2枚を2つの手に分ける。別途ベットが必要。"
         "例: 8,8は2枚で16（弱い）→分けて各8スタートにする。")
    term("R = サレンダー",
         "ベットの半分を失う代わりに勝負を降りる。「絶対に負ける」手を-50%に抑える戦術。\n"
         "**レイトサレンダー**: ディーラーがBJでないことを確認してから降参できる（一般的）。\n"
         "**アーリーサレンダー**: 確認前に降参（レア・プレイヤーに超有利）。")
    term("DAS（Double After Split）",
         "スプリット後にさらにダブルダウンできるルール。あると有利。")

    st.markdown("#### ルール設定")
    term("S17 / H17",
         "ディーラーがソフト17（A+6など）でどう動くか。\n"
         "**S17（Stand）**: ソフト17でスタンド → プレイヤー有利。\n"
         "**H17（Hit）**: ソフト17でヒット → ディーラーが手を強化するチャンスがある → プレイヤー不利。")
    term("ペネトレーション",
         "シューの何デッキ分を配布してからシャッフルするか。\n"
         "例: **6デッキ中5デッキ配布** = ペネトレーション83%。\n"
         "ペネトレーションが高い（多く配る）ほどカウンティングの精度が上がり有利。\n"
         "CSM（連続シャッフルマシン）は実質ペネトレーション0%でカウンティング不能。")

    st.markdown("#### カード カウンティング")
    term("ベーシックストラテジー（BS）",
         "カードの組み合わせごとに数学的に最善のアクションを示した早見表。"
         "BS通りに打つだけでハウスエッジを最小化できる（6D S17で約0.4〜0.5%）。")
    term("ハウスエッジ（House Edge）",
         "カジノが長期的に得る期待利益の割合。数字が小さいほどプレイヤーに有利。"
         "BSを完璧に使えば6デッキ S17 で約0.4〜0.5%。")
    term("Hi-Lo カード カウンティング",
         "最も有名なカウンティング手法。\n"
         "- 2〜6 が出たら **+1**\n"
         "- 7〜9 は **0**（無視）\n"
         "- 10〜A が出たら **−1**\n"
         "この合計がランニングカウント（RC）。")
    term("ランニングカウント（RC）/ トゥルーカウント（TC）",
         "**RC（Running Count）**: Hi-Lo の累積値。\n"
         "**TC（True Count）**: RC ÷ 残りデッキ数。デッキ数で補正した実効値。\n"
         "TC ≥ +1 でプレイヤー有利、TC ≥ +3 でインシュランスが有利になる。")
    term("インシュランス（Insurance）",
         "ディーラーのアップカードが**A**の時に提供されるサイドベット。"
         "ディーラー BJ に賭けて当たれば 2:1。**基本的には取るべきでない**。\n"
         "TC ≥ +3 の時のみ数学的に有利（Illustrious 18 の1番目）。")
    term("Illustrious 18 / Fab 4",
         "カウンターが覚えるべき BS からの逸脱プレイのリスト。"
         "TCに応じてアクションを変える18+4のプレイ。\n"
         "例: 16 vs 10 → TC ≥ 0 でスタンド（BS はヒット、**サレンダー有りなら R が優先**）。\n"
         "インデックスプレイタブで全一覧が確認できます。")
    term("ベットスプレッド（Bet Spread）",
         "TCが高い時にベットを増やし、低い時は最小ベットに抑える戦略。"
         "TC+1=2倍、TC+2=4倍、TC+3=6倍が典型例。スプレッドが大きいほど期待値は上がるが"
         "カジノにカウンターとして見破られやすい。")

    st.markdown("#### リスク管理")
    term("破産確率（Risk of Ruin / RoR）",
         "バンクロールを全て失う確率。解析近似: `exp(−2 × edge × bankroll / variance)`。\n"
         "ミニマム×100のバンクロールでも、標準スプレッドのカウンターの破産確率は約75%。\n"
         "「バンクロール＝失っても良い金額」として管理するのが鉄則。")
    term("プロフィットファクター（Profit Factor / PF）",
         "総利益 ÷ 総損失。1.5 なら「勝ちの合計が負けの合計の1.5倍」。"
         "1.0 以上なら収益がプラス。統計的な安定性の指標。")
    term("ハウスエッジ vs 還元率",
         "**ハウスエッジ 0.5%** = 長期的に賭け額の99.5%が返ってくる（還元率99.5%）。\n"
         "カウンティング + スプレッドで**エッジを+2%に反転**させると還元率102%（期待値プラス）。")
    term("バックオフ / 出禁（Backoff / Barring）",
         "カジノがカウンターと判断したプレイヤーをゲームから排除すること。"
         "合法だがカジノの権利。特定のゲームのみ禁止（バックオフ）から施設全体の出禁まで段階がある。")
    term("CSM（コンティニュアス シャッフル マシン）",
         "使ったカードをその場でデッキに戻す自動シャッフル機。カウンティングが実質不能になる。"
         "アミューズカジノには費用面から導入されていない所が多い。")
