"""
app.py — Streamlit ウェブアプリ（スマホ対応）
"""

import os
import tempfile

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from rules import HouseRules
from strategy import (generate_strategy_table, generate_ev_table, stand_breakdown,
                      house_edge_wizard, evaluate_hand, add_card)
from index_plays import (ILLUSTRIOUS_18, FAB_4, get_active_indexes,
                         get_filtered_indexes, should_take_insurance,
                         get_insurance_threshold, apply_tc_overlay)
from simulator import SimConfig, simulate
from pdf_export import generate_pdf
from diagrams import (holecard_timeline_figure, holecard_loss_example_figure,
                      hilo_tag_figure, running_to_true_count_figure,
                      index_play_figure, insurance_ev_figure, penetration_figure)

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


# ===========================================================================
# フリーミアム ゲーティング（無料 / PRO）
# ---------------------------------------------------------------------------
# CFO価格戦略（§2-1）に基づくティア設計:
#   無料 : ベーシックストラテジー表のみ（集客フック・無料勢と同水準）
#   PRO  : ＋シミュレーター・インデックスプレイ・PDF出力（差別化機能）
#
# 【決済連携TODO】
#   現状は「PROアクセスコード」入力で解放する簡易ゲート。
#   本番では Stripe / Gumroad 等の決済Webhookで発行したコードを
#   secrets / DB で検証する方式に差し替える。
#   想定フロー: 決済完了 → 一意のアクセスコード発行 → ユーザーがサイドバーに入力
#               → ここで照合（将来は API/DB 照会）→ st.session_state.is_pro = True
#   それまでは secrets["PRO_CODE"]（単一コード）で運用する。
# ===========================================================================
def _get_pro_codes() -> set:
    """有効なPROアクセスコード集合を返す。

    secrets に PRO_CODE（文字列）または PRO_CODES（カンマ区切り/リスト）が
    設定されていればそれを使う。未設定ならローカル開発用の既定コードを使う。
    """
    codes: set = set()
    try:
        single = st.secrets.get("PRO_CODE")
        if single:
            codes.add(str(single).strip())
    except (KeyError, FileNotFoundError, AttributeError):
        pass
    try:
        multi = st.secrets.get("PRO_CODES")
        if multi:
            if isinstance(multi, str):
                codes.update(c.strip() for c in multi.split(",") if c.strip())
            else:  # list/tuple
                codes.update(str(c).strip() for c in multi)
    except (KeyError, FileNotFoundError, AttributeError):
        pass
    # secrets未設定時のローカル開発用フォールバック（本番では必ずsecretsを設定）
    if not codes:
        codes.add("DEMO-PRO")
    return codes


# フリーミアムのマスタースイッチ。False=全機能を無料公開（集客フック）。
# 決済・導線が整う将来フェーズで True にするとPROロック（sim/PDF/インデックス）が有効化される。
FREEMIUM_ENABLED = False


def _render_pro_gate() -> bool:
    """サイドバーにPROゲートを描画し、PRO解放状態を返す。
    FREEMIUM_ENABLED=False のときはゲートを出さず全機能を無料解放する。"""
    if not FREEMIUM_ENABLED:
        return True
    if "is_pro" not in st.session_state:
        st.session_state.is_pro = False

    with st.sidebar:
        st.markdown("### 🔓 アクセスティア")
        if st.session_state.is_pro:
            st.success("PRO 機能が有効です")
            st.caption("シミュレーター・インデックス・PDF出力が利用できます。")
            if st.button("ログアウト（無料に戻す）", use_container_width=True):
                st.session_state.is_pro = False
                st.rerun()
        else:
            st.info("現在 **無料プラン**（ベーシックストラテジー表のみ）")
            code = st.text_input(
                "PROアクセスコード", type="password",
                placeholder="購入時に発行されたコードを入力",
                help="シミュレーター・インデックスプレイ・PDF出力を解放します。")
            if st.button("PROを有効化", use_container_width=True, type="primary"):
                if code.strip() in _get_pro_codes():
                    st.session_state.is_pro = True
                    st.rerun()
                else:
                    st.error("コードが正しくありません。")
            # TODO: 決済導線（Stripe/Gumroad）の購入リンクをここに設置する
            st.caption("PRO版で差別化機能（シミュレーション・破産確率・"
                       "インデックス・PDF）が解放されます。")
    return st.session_state.is_pro


IS_PRO = _render_pro_gate()


def _pro_locked_notice(feature_name: str):
    """PRO限定機能のロック表示。無料ユーザーに解放方法を案内する。"""
    st.warning(f"🔒 **{feature_name}** は PRO 機能です。")
    st.markdown(
        "この機能を使うには、サイドバーの **「PROアクセスコード」** に"
        "購入時のコードを入力して有効化してください。\n\n"
        "- **無料プラン**：ベーシックストラテジー表（ハウスルール対応）\n"
        "- **PRO プラン**：＋シミュレーター・破産確率・インデックスプレイ・PDF出力")
    # TODO: 決済（Stripe/Gumroad）の購入ボタン/リンクをここに設置する


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
# ── ルールセット（プリセット）定義 ────────────────────────────────
# 名前 → 各ウィジェット(key)に流し込む値。新しい店舗ルールはここに追加するだけ。
RULESET_PRESETS = {
    "BLOW川崎": {
        "hr_num_decks": 6,
        "hr_bj_pay": "3:2 (1.5倍)",
        "hr_soft17": "S17 (スタンド)",
        "hr_hole_card": "ENHC — 欧州式（ノーホールカード）",
        "hr_double": "any（どの2枚でも）",
        "hr_das": True,
        "hr_split_aces": True,
        "hr_draw_split_aces": False,
        "hr_max_splits": 9,
        "hr_surrender": "early（アーリーサレンダー）",
        "hr_surrender_vs_ace": False,
        "hr_decks_dealt": 4.5,   # 6デッキ中4.5配布＝ペネトレーション75%
    },
    "インスパイアカジノ（緑テーブル）": {
        "hr_num_decks": 6,
        "hr_bj_pay": "3:2 (1.5倍)",
        "hr_soft17": "H17 (ヒット)",
        "hr_hole_card": "HC — US式（事前確認あり）",
        "hr_double": "any（どの2枚でも）",
        "hr_das": True,
        "hr_split_aces": True,
        "hr_draw_split_aces": False,
        "hr_max_splits": 3,
        "hr_surrender": "late（レイトサレンダー）",
        "hr_surrender_vs_ace": False,
        "hr_decks_dealt": 6.0,   # 6デッキ全配布(100%)＝CSM
    },
}
_RULESET_OPTIONS = ["カスタム（手動設定）"] + list(RULESET_PRESETS.keys())

# 各ウィジェットの初期値（カスタム時の既定）。session_state未設定なら入れる。
_HR_DEFAULTS = {
    "hr_num_decks": 6,
    "hr_bj_pay": "3:2 (1.5倍)",
    "hr_soft17": "S17 (スタンド)",
    "hr_hole_card": "HC — US式（事前確認あり）",
    "hr_double": "any（どの2枚でも）",
    "hr_das": True,
    "hr_split_aces": True,
    "hr_draw_split_aces": False,
    "hr_max_splits": 3,
    "hr_surrender": "late（レイトサレンダー）",
    "hr_surrender_vs_ace": False,
    "hr_decks_dealt": None,   # None=デッキ数から75%で自動算出
}
for _k, _v in _HR_DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ユーザーが自分で保存したカスタムプリセット（このセッション中のみ保持）
if "user_presets" not in st.session_state:
    st.session_state["user_presets"] = {}

# プリセット保存時に集めるハウスルールのキー一覧
_HR_KEYS = list(_HR_DEFAULTS.keys())


def _apply_ruleset():
    """ルールセット選択時、プリセット値を各ウィジェットのsession_stateへ反映する。

    既定プリセット(RULESET_PRESETS)とユーザー保存プリセット(user_presets)の両方を探す。
    """
    name = st.session_state.get("hr_ruleset")
    preset = (RULESET_PRESETS.get(name)
              or st.session_state.get("user_presets", {}).get(name))
    if preset:
        for _key, _val in preset.items():
            st.session_state[_key] = _val


_GUIDE_IMG_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "assets", "guide")


def _img_popover(label, filename, caption):
    """ルール設定の隣に置く「📷 見分け方」ポップオーバー（押すと写真が出る）。"""
    with st.popover(label, use_container_width=True):
        _p = os.path.join(_GUIDE_IMG_DIR, filename)
        if os.path.exists(_p):
            st.image(_p, use_container_width=True)
        st.caption(caption)


# ─── 使い方ステップ（最上部・初心者導線） ───
st.markdown(
    '<div style="background:#E8F5E9;border:1px solid #A5D6A7;border-radius:10px;'
    'padding:12px 16px;margin-bottom:12px;font-size:0.9rem;color:#1B3D24;'
    'line-height:1.7;">'
    '<div style="font-weight:800;font-size:0.95rem;margin-bottom:4px;">'
    '📋 使い方は3ステップ</div>'
    '<strong>Step 1.</strong> 下の「⚙️ ハウスルール設定」で、遊ぶ卓の条件を選ぶ'
    '（ルールが分からなければ各項目の「📷 見分け方」ボタンで写真を確認）<br>'
    '<strong>Step 2.</strong> 「ベーシックストラテジー」タブの<strong>⚡クイック判定</strong>で、'
    '自分の2枚とディーラーのカードを選ぶ<br>'
    '<strong>Step 3.</strong> 表示された<strong>最善手</strong>のとおりにプレイ。'
    'その卓の<strong>ハウスエッジ（カジノの取り分）</strong>も自動で表示されます。</div>',
    unsafe_allow_html=True)

with st.expander("⚙️  ハウスルール設定（クリックで展開）", expanded=False):
    if st.session_state.pop("_preset_saved_flag", None):
        st.success("プリセットを保存しました。上の一覧から選べます。")
    _ruleset_options = (["カスタム（手動設定）"] + list(RULESET_PRESETS.keys())
                        + list(st.session_state["user_presets"].keys()))
    st.radio(
        "ルールセット（プリセット）",
        _ruleset_options,
        key="hr_ruleset",
        on_change=_apply_ruleset,
        horizontal=True,
    )
    st.caption("プリセットを選ぶと、下のハウスルールが自動入力されます"
               "（選択後に手動で微調整も可能）。自分用の設定は一番下で名前を付けて保存できます。")
    rc1, rc2, rc3 = st.columns(3)
    with rc1:
        st.markdown("**テーブル基本ルール**")
        num_decks = st.selectbox(
            "デッキ数", [1, 2, 4, 6, 8], key="hr_num_decks",
            help="使用するトランプの組数。少ないほどプレイヤー有利（1〜2デッキは好条件）。"
                 "／確認方法：シューの中のカードの組数。分からなければディーラーに聞く。")
        _img_popover(
            "📷 デッキ数の見分け方（シューを見る）", "shoe_fal.png",
            "シュー（カードを入れて配る箱）の中のカードの組数がデッキ数です（1〜8組）。"
            "見て分からなければ、ディーラーに「何デッキ？」と聞けばOKです。")
        bj_pay_label = st.selectbox(
            "BJ 配当", ["3:2 (1.5倍)", "6:5 (1.2倍)"], key="hr_bj_pay",
            help="ブラックジャック成立時の配当。3:2が正規。6:5は還元率が約1.4%下がる不利な卓で、避けたい条件です。"
                 "／確認方法：テーブル面の『PAYS 3 TO 2』『6 TO 5』表記。")
        soft17_label = st.selectbox(
            "ディーラー ソフト17", ["S17 (スタンド)", "H17 (ヒット)"], key="hr_soft17",
            help="エースを含む17（ソフト17）でディーラーがどう動くか。S17（スタンド）がプレイヤー有利、"
                 "H17（ヒット）はカジノ側が約0.2%有利になります。"
                 "／確認方法：テーブル面の『stand on all 17s』『hits soft 17』表記。")
        _img_popover(
            "📷 配当・ソフト17の見分け方（テーブルを見る）", "table_felt_annotated.png",
            "テーブル面の印字で分かります。図の「ここを見る」を参照："
            "『PAYS 3 TO 2』＝配当3:2（良卓）／『6 TO 5』＝不利。"
            "『stand on all 17s』＝S17（有利）／『hits soft 17』＝H17。")
        hole_card_label = st.selectbox(
            "ホールカードルール",
            ["HC — US式（事前確認あり）",
             "ANHC — オーストラリア式（ノーホールカード）",
             "ENHC — 欧州式（ノーホールカード）"],
            key="hr_hole_card",
            help="ディーラーが伏せ札（ホールカード）を持つか。US式(HC)はBJを事前確認。"
                 "欧州式(ENHC)は確認せず、ダブル/スプリットで増やした賭け金もディーラーBJで失うため約0.1%不利。")
    with rc2:
        st.markdown("**ダブル・スプリット**")
        double_label = st.selectbox(
            "ダブルダウン条件",
            ["any（どの2枚でも）", "9-11", "10-11"], key="hr_double",
            help="ダブルダウン（1枚だけ引いて賭け金を倍にする）が許される手。"
                 "any（任意の2枚）が最も有利。9-11や10-11は制限が強く不利になります。")
        das = st.checkbox(
            "スプリット後ダブル可 (DAS)", key="hr_das",
            help="DAS＝Double After Split。ペアを分けた後の手でもダブルできるルール。"
                 "可だとプレイヤー有利（約0.14%）。")
        split_aces = st.checkbox(
            "エースのスプリット可", key="hr_split_aces",
            help="A,A のペアを2つの手に分けられるか。エースの分割は非常に強力です。")
        draw_to_split_aces = st.checkbox(
            "スプリットA後のヒット可", key="hr_draw_split_aces",
            help="分割したエースに2枚目以降を引けるか。通常は各手1枚のみ。引けるとプレイヤー有利。")
        max_splits = st.number_input(
            "最大スプリット追加回数", min_value=1, max_value=9, step=1, key="hr_max_splits",
            help="同じ数字を何回まで分割できるか（3＝最大4ハンドまで）。")
    with rc3:
        st.markdown("**サレンダー・ペネトレーション**")
        surrender_label = st.selectbox(
            "サレンダー",
            ["late（レイトサレンダー）", "none（なし）", "early（アーリーサレンダー）"],
            key="hr_surrender",
            help="不利な手で賭け金の半額を捨てて降りる権利。late＝ディーラーのBJ確認後に降りる一般的な方式。"
                 "early＝確認前に降りられる強力な方式。")
        surrender_vs_ace_ui = st.checkbox(
            "エース対面でのサレンダー可", key="hr_surrender_vs_ace",
            help="ディーラーのアップカードがA（エース）のときもサレンダーできるか。")
        _pen_min = float(max(1, num_decks // 2))
        _pen_max = float(num_decks)   # 最大=全デッキ配布(100%)＝CSM相当
        # decks_dealt は num_decks に依存。session_state値を範囲にクランプしてから使う
        _dd = st.session_state.get("hr_decks_dealt")
        if _dd is None:
            _dd = num_decks * 0.75
        _dd = min(max(_pen_min, round(_dd * 2) / 2), _pen_max)
        st.session_state["hr_decks_dealt"] = _dd   # スライダー生成前なので変更OK
        decks_dealt = st.slider(
            "シューから何デッキ配布でシャッフルするか（シミュ用・最大100%＝CSM）",
            min_value=_pen_min,
            max_value=_pen_max,
            step=0.5,
            key="hr_decks_dealt",
        )
        penetration = decks_dealt / num_decks
        if penetration >= 1.0:
            st.caption(
                "🔄 **CSM（連続シャッフルマシン）相当**：毎ハンド実質シャッフルされ、"
                "捨て札が貯まらないため**カウンティングはほぼ無効**になります"
                "（シミュレーターでも毎ハンド・リシャッフルとして扱います）。")
        else:
            st.caption(
                f"→ {num_decks}デッキ中 {decks_dealt:g}デッキ配布してシャッフル"
                f"（ペネトレーション {penetration:.0%}）")

    # ── 自分用プリセット／削除 ──
    st.markdown("---")
    st.markdown("**💾 自分用プリセットを保存／呼び出し**")
    st.caption("いま選んでいるルールに名前を付けて保存できます。"
               "次回から上の一覧でワンタップ呼び出し。"
               "※ 保存はこのセッション中のみ有効です（ページを閉じると消えます）。")
    _save_name = st.text_input(
        "プリセット名", key="hr_preset_name", placeholder="例：六本木○○カジノ")
    _ps1, _ps2 = st.columns(2)
    with _ps1:
        if st.button("現在の設定を保存", use_container_width=True):
            _nm = (_save_name or "").strip()
            if not _nm:
                st.warning("プリセット名を入力してください。")
            elif _nm in RULESET_PRESETS or _nm == "カスタム（手動設定）":
                st.warning("その名前は既定プリセットと重複します。別の名前にしてください。")
            else:
                st.session_state["user_presets"][_nm] = {
                    _key: st.session_state[_key] for _key in _HR_KEYS}
                st.session_state["_preset_saved_flag"] = True
                st.rerun()
    with _ps2:
        _user_names = list(st.session_state["user_presets"].keys())
        if _user_names:
            _del = st.selectbox(
                "保存済みを削除", ["（選択）"] + _user_names, key="hr_preset_del")
            if st.button("選択を削除", use_container_width=True) and _del in _user_names:
                del st.session_state["user_presets"][_del]
                if st.session_state.get("hr_ruleset") == _del:
                    st.session_state["hr_ruleset"] = "カスタム（手動設定）"
                st.rerun()
        else:
            st.caption("（まだ保存したプリセットはありません）")

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

# ─── ハウスエッジ常時表示（Wizard of Odds公表値ベースの加法モデル） ───
# ルールを変えるとリアルタイムに増減する。リードマグネットの「磁力の核」。
_he = house_edge_wizard(rules)
_ret = 100.0 - _he
if _he <= 0.0:
    _he_color, _he_bg, _he_msg = "#1B5E20", "#E8F5E9", "このルールは理論上プレイヤー有利（ごく稀な好条件）。"
elif _he <= 0.5:
    _he_color, _he_bg, _he_msg = "#2E7D32", "#E8F5E9", "優良な部類。ベーシックストラテジー前提なら十分に戦えるテーブルです。"
elif _he <= 1.0:
    _he_color, _he_bg, _he_msg = "#EF6C00", "#FFF3E0", "平均的〜やや不利。条件の良い卓を選ぶ余地があります。"
else:
    _he_color, _he_bg, _he_msg = "#C62828", "#FFEBEE", "不利な部類。特に 6:5 配当は還元率を大きく下げます（避けたい卓）。"
st.markdown(
    f'<div style="background:{_he_bg};border:1px solid {_he_color}33;'
    f'border-left:5px solid {_he_color};border-radius:10px;'
    f'padding:12px 16px;margin:6px 0 2px 0;">'
    f'<div style="display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 20px;">'
    f'<span style="font-size:0.78rem;font-weight:700;color:#546E7A;'
    f'letter-spacing:0.08em;">このルールのハウスエッジ</span>'
    f'<span style="font-size:1.9rem;font-weight:800;color:{_he_color};'
    f'line-height:1;">{_he:.2f}<span style="font-size:1.0rem;">%</span></span>'
    f'<span style="font-size:0.82rem;color:#37474F;">還元率 '
    f'<strong style="color:{_he_color};">{_ret:.2f}%</strong></span>'
    f'</div>'
    f'<div style="font-size:0.8rem;color:#455A64;margin-top:6px;line-height:1.6;">'
    f'{_he_msg}</div></div>',
    unsafe_allow_html=True)
st.caption(
    "※ ハウスエッジ＝カジノ側の取り分（低いほどプレイヤー有利）。"
    "Wizard of Odds 公表値ベースの加法モデルによる近似（連続シャッフラー基準・誤差±0.05〜0.1%）。"
    "カットカード使用卓では実測が約+0.1%高くなります。"
    "精密な検証は [Wizard of Odds 公式計算機](https://wizardofodds.com/games/blackjack/calculator/) をご利用ください。")



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
# ディーラーのアップカード行（見出し行）をスマホ横向き時の縦スクロールでも
# 上端に固定表示するためのsticky指定。
_STICKY_TOP = ("position:sticky;top:0;z-index:4;"
              "box-shadow:0 2px 4px -2px rgba(0,0,0,0.25);")
# 左上の角セル（Hand列の見出し）は横スクロール・縦スクロールの両方で
# 固定する必要があるため、left/top両方をstickyにする。
_STICKY_COL_TOP = ("position:sticky;left:0;top:0;z-index:5;"
                   "box-shadow:2px 2px 4px -2px rgba(0,0,0,0.25);")


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
        # ページ全体のスクロールに対するposition:sticky;top:0は、Streamlit側の
        # コンテナ構成（タブパネル等のoverflow指定）に依存して効かない場合がある。
        # そのため、この div 自体に max-height + overflow-y:auto を持たせて
        # 「このdiv内だけでスクロールする」専用のスクロールコンテナとし、
        # sticky-topを確実にこのdivの内部スクロールに追従させる。
        '<div style="overflow-x:auto;overflow-y:auto;max-height:65vh;'
        'border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,0.1);">',
        '<table style="border-collapse:collapse;width:100%;'
        'font-size:13px;text-align:center;min-width:480px;">',
    ]
    # 行1: DEALER UPCARD スパン（装飾的な見出しのため固定はしない）
    html.append(
        f'<tr>'
        f'<th style="{_HDR_BG};{_STICKY_COL}color:transparent;padding:4px;'
        f'{_BORDER};width:60px;"></th>'
        f'<th colspan="10" style="{_HDR_BG};color:#FFD700;padding:6px;'
        f'{_BORDER};font-size:0.76rem;font-weight:700;letter-spacing:0.14em;">'
        f'▼ &nbsp; D E A L E R &nbsp; U P C A R D &nbsp; ▼'
        f'</th></tr>'
    )
    # 行2: アップカード数字（スマホ横向きでの縦スクロール時も上端に固定）
    html.append('<tr>')
    html.append(
        f'<th style="{_HAND_BG};{_STICKY_COL_TOP}color:#546E7A;padding:5px 4px;'
        f'{_BORDER};font-size:0.75rem;font-weight:600;">Hand</th>')
    for u in UPCARDS:
        html.append(
            f'<th style="{_UPCD_BG};{_STICKY_TOP}color:#E3F2FD;padding:5px 8px;'
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
# クイック判定（単手ルックアップ）— スマホの卓上で表より速い即答UI
# ===========================================================================
_ACTION_NAMES = {"H": "ヒット", "S": "スタンド", "D": "ダブルダウン",
                 "P": "スプリット", "R": "サレンダー"}
_QUICK_CARD_OPTS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10"]


def _opt_rank(o: str) -> int:
    return 11 if o == "A" else int(o)


def _card_name(r: int) -> str:
    return "A" if r == 11 else str(r)


def _card_picker(label, key, default):
    """カードを「タップ」して選ぶピッカー（プルダウンを廃止）。選択中は青く強調。"""
    if key not in st.session_state:
        st.session_state[key] = default
    cur = st.session_state[key]
    st.markdown(
        f"<div style='font-size:0.82rem;font-weight:700;color:#37474F;margin:2px 0;'>"
        f"{label}：<span style='color:#1565C0;font-size:1.0rem;'>{cur}</span></div>",
        unsafe_allow_html=True)
    cols = st.columns(10)
    for i, r in enumerate(_QUICK_CARD_OPTS):
        with cols[i]:
            if st.button(r, key=f"{key}_{r}", use_container_width=True,
                         type="primary" if r == cur else "secondary"):
                st.session_state[key] = r
                st.rerun()
    return st.session_state[key]


def render_quick_decision(rules, tc):
    """自分の2枚＋ディーラーのアップカードから最善手と各アクションEVを即表示する。"""
    st.markdown("##### ⚡ クイック判定（自分の手とディーラーを選ぶだけ）")
    st.caption("スマホでも一目。自分の2枚とディーラーのアップカードを選ぶと、"
               "最善手と「なぜ」を即表示します。表を探す必要はありません。")
    st.caption("↓ カードをタップして選んでください")
    p1 = _card_picker("自分のカード①", "q_p1", "10")
    p2 = _card_picker("自分のカード②", "q_p2", "6")
    du = _card_picker("ディーラーのアップカード", "q_du", "10")
    c1, c2, dup = _opt_rank(p1), _opt_rank(p2), _opt_rank(du)
    t1, s1 = (11, True) if c1 == 11 else (c1, False)
    total, soft = add_card(t1, s1, c2)
    is_pair = (c1 == c2)
    pair_rank = c1 if is_pair else 0
    is_bj = (c1 == 11 and c2 == 10) or (c1 == 10 and c2 == 11)

    if is_pair:
        hand_desc = f"{_card_name(c1)},{_card_name(c2)} = ペア（{'ソフト' if soft else 'ハード'}{total}）"
    else:
        hand_desc = f"{_card_name(c1)},{_card_name(c2)} = {'ソフト' if soft else 'ハード'}{total}"

    if is_bj:
        pay = "3:2（1.5倍）" if rules.blackjack_pays == 1.5 else "6:5（1.2倍）"
        st.markdown(
            '<div style="background:#FFF9C4;border:2px solid #F9A825;border-radius:12px;'
            'padding:16px 18px;text-align:center;margin:6px 0;">'
            '<div style="font-size:1.8rem;font-weight:800;color:#E65100;">'
            'ブラックジャック！🎉</div>'
            f'<div style="font-size:0.9rem;color:#6D4C41;font-weight:600;margin-top:4px;">'
            f'配当 {pay}。アクション不要でそのまま勝ちです'
            '（ディーラーがA・10のときは相手のBJ確認後に確定）。</div></div>',
            unsafe_allow_html=True)
        st.markdown("---")
        return

    best, evs = evaluate_hand(total, soft, is_pair, dup, rules,
                              pair_rank=pair_rank, tc=tc)
    bg = CELL_COLORS.get(best, "#ECEFF1")
    fg = CELL_TEXT.get(best, "#37474F")
    st.markdown(
        f'<div style="background:{bg};border-radius:12px;padding:14px 18px;'
        f'text-align:center;margin:6px 0;">'
        f'<div style="font-size:0.8rem;color:{fg};opacity:0.85;font-weight:600;">'
        f'あなたの手: {hand_desc} ／ ディーラー {_card_name(dup)}</div>'
        f'<div style="font-size:2.0rem;font-weight:800;color:{fg};line-height:1.25;">'
        f'{_ACTION_NAMES[best]}</div>'
        f'<div style="font-size:0.9rem;color:{fg};font-weight:700;">（{best}）</div>'
        f'</div>', unsafe_allow_html=True)

    with st.expander("なぜ？（各アクションの期待値を比較）", expanded=False):
        parts = []
        for act, ev in sorted(evs.items(), key=lambda x: -x[1]):
            abg = CELL_COLORS.get(act, "#ECEFF1")
            afg = CELL_TEXT.get(act, "#37474F")
            mark = ' <strong style="color:#1565C0;">← 最善</strong>' if act == best else ""
            parts.append(
                f'<div style="display:flex;align-items:center;gap:10px;margin:5px 0;">'
                f'<span style="min-width:104px;background:{abg};color:{afg};'
                f'padding:3px 10px;border-radius:5px;font-weight:700;font-size:0.85rem;'
                f'text-align:center;">{_ACTION_NAMES[act]}</span>'
                f'<span style="font-weight:700;color:{"#1B5E20" if ev >= 0 else "#B71C1C"};">'
                f'{ev:+.3f}</span>{mark}</div>')
        st.markdown("".join(parts), unsafe_allow_html=True)
        st.caption("EV＝賭け金1単位あたりの期待値。最も高いアクションが最善手です。"
                   "（マイナスでも、より損失の小さい手を選ぶのが最善になります）")

    if total >= 12:
        bd = stand_breakdown(total, dup, rules, tc=tc)
        st.caption(
            f"参考・スタンドした場合: 勝ち {bd['win'] * 100:.0f}% ／ "
            f"引分 {bd['push'] * 100:.0f}% ／ 負け {bd['lose'] * 100:.0f}%")
    st.markdown("---")


# ===========================================================================
# タブ
# ===========================================================================
def render_bs_tables(display_table, ev_table, changed_cells, tab1_tc, show_ev, rules):
    """ベーシックストラテジー早見表（ハード/ソフト/ペアの3表）を描画する。"""
    st.markdown(legend_html(show_tc=bool(changed_cells)), unsafe_allow_html=True)
    if changed_cells:
        st.caption(
            f"★ {len(changed_cells)} セルが TC {tab1_tc:+d} のインデックスプレイで変更されています。")
    hard_totals = list(range(17, 4, -1))
    soft_totals = list(range(20, 12, -1))
    pair_ranks = [11, 10, 9, 8, 7, 6, 5, 4, 3, 2]
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


def render_stand_breakdown_section(rules, tab1_tc):
    """スタンド時の勝率・引き分け・負け率の内訳セクションを描画する。"""
    st.markdown("##### 🎯 勝敗内訳（スタンド時の win / push / lose）")
    st.caption(
        "「この手でスタンドしたら実際に何%勝てるのか」を、ディーラー最終手分布から"
        "解析的に計算します。例：プレイヤー17 vs ディーラー7 は本当に強いのか？")
    wcol1, wcol2 = st.columns(2)
    with wcol1:
        wl_player = st.slider(
            "プレイヤーの最終手（ハード合計）", min_value=12, max_value=21, value=17,
            help="スタンドした時点のプレイヤー合計。ソフトハンドも、Aを11として"
                 "実効合計が同じなら勝敗内訳は同一です（スタンド時の比較相手は同じため）。")
    with wcol2:
        wl_up = st.selectbox(
            "ディーラーのアップカード", UPCARDS,
            index=UPCARDS.index(7), format_func=_up_label)
    bd = stand_breakdown(wl_player, wl_up, rules, tc=tab1_tc)
    bw, bp, bl = st.columns(3)
    bw.metric("勝率 (Win)", f"{bd['win'] * 100:.1f}%")
    bp.metric("引き分け (Push)", f"{bd['push'] * 100:.1f}%")
    bl.metric("負け率 (Lose)", f"{bd['lose'] * 100:.1f}%")
    st.caption(
        f"この手でスタンドしたときの期待値（勝率 − 負け率）＝ **{bd['ev']:+.4f}**"
        "（賭け金1単位あたり。プラスなら有利、マイナスなら不利）。\n\n"
        f"条件：ディーラー {_up_label(wl_up)}・TC {tab1_tc:+d}・{rules.short_description()}")
    if wl_up in (10, 11):
        st.caption(
            "※ ディーラーが10またはAを見せているときのこの勝率は、"
            "「ディーラーが最初からブラックジャックではなかった場合」の数字です。"
            "（もしディーラーがブラックジャックなら、その時点で勝負が決まり、"
            "あなたがプレイする場面にならないためです。）")
    dlr = bd["dealer"]
    dlr_df = pd.DataFrame(
        [("17", dlr[17]), ("18", dlr[18]), ("19", dlr[19]),
         ("20", dlr[20]), ("21", dlr[21]), ("バスト", dlr["bust"])],
        columns=["ディーラー最終手", "確率"])
    dlr_df["確率"] = (dlr_df["確率"] * 100).map(lambda x: f"{x:.1f}%")
    with st.expander("ディーラー最終手の確率分布（参考）"):
        st.dataframe(dlr_df, use_container_width=True, hide_index=True)


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
    with st.expander("🎓 上級者向け設定（True Count・EV表示）", expanded=False):
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

    _sub_q, _sub_t, _sub_b = st.tabs(
        ["⚡ クイック判定", "📊 早見表（全パターン）", "🎯 勝敗内訳"])
    with _sub_q:
        if should_take_insurance(tab1_tc):
            st.success(f"TC {tab1_tc:+d} → インシュランスを取る（TC ≥ +3）")
        render_quick_decision(rules, tab1_tc)
    with _sub_t:
        render_bs_tables(display_table, ev_table, changed_cells, tab1_tc, show_ev, rules)
    with _sub_b:
        render_stand_breakdown_section(rules, tab1_tc)

# ---------------------------------------------------------------------------
# Tab 2: インデックスプレイ
# ---------------------------------------------------------------------------
def _thr_label(thr, direction):
    op = "≥" if direction == "+" else "≤"
    return f"TC{op}{thr:+d}"


with tab2:
    st.subheader("True Count 別インデックスプレイ（Hi-Lo）")
    if not IS_PRO:
        _pro_locked_notice("インデックスプレイ")
    else:
        tc2 = st.slider("True Count (TC)", -5, 5, 0, 1)

        ins_thr = get_insurance_threshold()
        if should_take_insurance(tc2):
            st.success(f"TC {tc2:+d} → インシュランスを取る（TC ≥ {ins_thr:+d}）")
        else:
            st.info(f"TC {tc2:+d} → インシュランスは取らない（TC ≥ {ins_thr:+d} で得）")

        active = get_active_indexes(tc2, rules)
        st.markdown(f"**TC {tc2:+d} でベーシックストラテジーから逸脱中のプレイ**")
        if active:
            df = pd.DataFrame(
                [(h, _up_label(d) if isinstance(d, int) else d, _thr_label(thr, direction), a)
                 for (h, d, thr, a, direction) in active],
                columns=["ハンド", "ディーラー", "発動条件", "アクション"])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.write("発動中の逸脱プレイはありません（BS通りにプレイ）。")

        st.markdown("---")
        st.markdown("**インデックスプレイ全一覧（現在のハウスルールで実際にBSから逸脱するものだけを動的に算出）**")
        filtered_idx = get_filtered_indexes(rules)
        all_idx = pd.DataFrame(
            [(h, _up_label(d) if isinstance(d, int) else d, _thr_label(thr, direction), a)
             for (h, d, thr, a, direction) in filtered_idx],
            columns=["ハンド", "ディーラー", "発動条件", "アクション"])
        st.dataframe(all_idx, use_container_width=True, hide_index=True)
        n_excluded = len(ILLUSTRIOUS_18) + len(FAB_4) - len(filtered_idx)
        if n_excluded > 0:
            st.caption(
                f"※ 現在のルール（{rules.short_description()}）ではBSから逸脱しない、"
                f"または他のアクションが常に優先されるため "
                f"{n_excluded} 件を除外しています。")

# ---------------------------------------------------------------------------
# Tab 3: シミュレーター
# ---------------------------------------------------------------------------
with tab3:
    st.subheader("モンテカルロ シミュレーター")
    if not IS_PRO:
        _pro_locked_notice("シミュレーター")

if IS_PRO:
  with tab3:
    col1, col2 = st.columns(2)
    with col1:
        num_hands = st.select_slider(
            "シミュレーション手数",
            options=[100_000, 500_000, 1_000_000, 5_000_000, 10_000_000],
            value=1_000_000)
        use_counting = st.checkbox("カウンティング戦略 (Hi-Lo)", value=False)
    with col2:
        bankroll = st.number_input("バンクロール（絶対額）", 1, 10_000_000, 1000, step=1)
        max_bet = st.number_input("マックスベット（絶対額）", 1, 1_000_000, 1000, step=1,
                                  key="sim_max_bet")

        # 既存セッションでmin_bet/TC毎の賭け額がmax_betより大きい場合、
        # widget生成前にクリップしておく（number_inputは現在値が
        # max_valueを超えていると例外になるため）。
        for _key in ("sim_min_bet", "sim_m1", "sim_m2", "sim_m3"):
            if _key in st.session_state and st.session_state[_key] > max_bet:
                st.session_state[_key] = max_bet

        min_bet = st.number_input("ミニマムベット（絶対額）", 1, int(max_bet),
                                  min(10, int(max_bet)), step=1, key="sim_min_bet")

    auto_scale = False
    if use_counting:
        auto_scale = st.checkbox(
            "バンクロールの増減に応じてTC毎の賭け額を自動調整",
            value=False,
            help="チェック時、各ハンドの賭け額を「その時点のバンクロール ÷ "
                 "シミュレーション開始時のバンクロール」の比率で動的にスケールします。"
                 "試行が進みバンクロールが増えれば賭け額も増え、減れば賭け額も減ります。"
                 "下記で入力する賭け額・ミニマムベットは、開始時点"
                 "（バンクロール＝上記入力値）における基準値として使われます。")

    bet_spread = None
    if use_counting:
        st.markdown(
            "**ベットスプレッド（TC 閾値 → 賭け額・絶対値、開始時バンクロール基準、"
            f"マックスベット {int(max_bet):,} まで）**")
        c1, c2, c3 = st.columns(3)
        with c1:
            m1 = st.number_input("TC ≥ +1 賭け額（絶対額）", 1, int(max_bet),
                                 min(20, int(max_bet)), step=1, key="sim_m1")
        with c2:
            m2 = st.number_input("TC ≥ +2 賭け額（絶対額）", 1, int(max_bet),
                                 min(40, int(max_bet)), step=1, key="sim_m2")
        with c3:
            m3 = st.number_input("TC ≥ +3 賭け額（絶対額）", 1, int(max_bet),
                                 min(60, int(max_bet)), step=1, key="sim_m3")
        bet_spread = {1: m1, 2: m2, 3: m3}

    if st.button("シミュレーション実行", type="primary"):
        cfg = SimConfig(
            rules=rules,
            num_hands=int(num_hands),
            use_counting=use_counting,
            bet_spread=bet_spread,
            min_bet=min_bet,
            max_bet=max_bet,
            bankroll=bankroll,
            bankroll_scaling=auto_scale,
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
        m4c.metric("純利益（絶対額）", f"{res.net_profit:,.0f}")

        m5c, m6c, m7c, m8c = st.columns(4)
        m5c.metric("標準偏差", f"{res.std_dev:.3f}")
        m6c.metric("プロフィットファクター", f"{res.profit_factor:.3f}")
        m7c.metric("破産確率", f"{res.ruin_probability * 100:.1f}%")
        m8c.metric("最大 DD（絶対額）", f"{res.max_drawdown:,.0f}")
        st.caption(
            "※ 破産確率はサンプル数（シミュレーション手数）が少ないとシード"
            "（実行ごとの乱数）によって結果が大きくブレます。カウンティングの"
            "エッジは0.3〜0.8%程度と薄いため、安定した値を見たい場合は"
            "シミュレーション手数を多め（500万手以上を推奨）に設定してください。")

        st.caption(
            f"P 値（純利益 > 0 の有意性・片側）: {res.p_value:.4f} / "
            f"総賭け額: {res.total_wagered:,.0f}")

        if auto_scale:
            final_bankroll = bankroll + res.net_profit
            if res.stopped_early:
                st.warning(
                    f"バンクロールが枯渇したため、設定手数 {int(num_hands):,} 手のうち "
                    f"{res.num_hands:,} 手でシミュレーションを終了しました"
                    "（バンクロール比例ベットでは、バンクロールが尽きた時点でプレイを"
                    "継続できないため停止します）。以降の統計はこの実プレイ手数に基づきます。")
            else:
                st.caption(
                    f"バンクロール比例ベット適用中: 開始時バンクロール {bankroll:,.0f} → "
                    f"終了時バンクロール {final_bankroll:,.0f}（×{final_bankroll / bankroll:.3f}）。"
                    "シミュレーション中はこの比率で各ハンドの賭け額が動的に増減しています。")

        if res.bankroll_curve:
            sample_every = max(1, res.curve_sample_every)
            hand_index = [i * sample_every for i in range(len(res.bankroll_curve))]
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=hand_index, y=res.bankroll_curve, mode="lines",
                name="累積純利益", line=dict(color="#1f77b4"),
                hovertemplate="ハンド数: %{x:,}<br>累積純利益: %{y:,.1f}<extra></extra>"))
            fig.update_layout(
                xaxis_title="ハンド数", yaxis_title="累積純利益（絶対額）",
                margin=dict(l=10, r=10, t=10, b=10), height=400,
                xaxis=dict(rangeslider=dict(visible=True), type="linear"),
                hovermode="x unified", dragmode="pan")
            # scrollZoomはマウスホイールをグラフ側で奪い、ページスクロールが
            # 効かなくなる（グラフ通過後に上に戻せなくなる）ため有効化しない。
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                f"全 {res.num_hands:,} 手のシミュレーション結果を、"
                f"{sample_every:,} 手ごとに{len(res.bankroll_curve):,} 点サンプリングして"
                "累積純利益の推移を表示しています（横軸＝経過ハンド数）。"
                "グラフはドラッグでパン（移動）、"
                "下部のスライダーで範囲選択、"
                "ダブルクリックで全体表示にリセットできます。")

        if use_counting:
            st.info(
                "検証目安: カウンティング時の還元率 ≈ 102%（エッジ ≈ +2%）。"
                " ミニマムベット×100 のバンクロール + 標準スプレッドで破産確率 ≈ 75%。")

# ---------------------------------------------------------------------------
# Tab 4: PDF 出力
# ---------------------------------------------------------------------------
with tab4:
    st.subheader("PDF 出力")
    if not IS_PRO:
        _pro_locked_notice("PDF 出力")

if IS_PRO:
  with tab4:
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

    st.markdown("""\
<div style="background:#FFF8E1;border:1px solid #FFE082;border-radius:8px;
padding:12px 16px;margin-bottom:14px;font-size:0.85rem;line-height:1.7;">
<strong>🔰 初めての方へ：読む順番のおすすめ</strong><br>
下から順番にすべて読む必要はありません。まずは以下の3つだけで十分プレイできます。
<ol style="margin:6px 0 4px 18px;padding:0;">
<li><strong>🎮 ブラックジャックの遊び方</strong>（ルールと進め方）</li>
<li><strong>📖 基本用語</strong>（ブラックジャック・バースト・プッシュなど）</li>
<li><strong>🃏 アクション</strong>（H/S/D/P/R の意味）</li>
</ol>
それ以降の「⚙️ ハウスルール設定ガイド」「🔢 カードカウンティング」「📊 リスク管理」は、
カウンティングや高度な戦略に興味が出てから読めば大丈夫です。各項目はタップすると開閉します。
</div>
""", unsafe_allow_html=True)

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

    with st.expander("ホールカードルール（HC / ANHC / ENHC）"):
        st.markdown("""\
**一言でいうと**：ディーラーの2枚目のカード（裏向き）を「いつ配るか」「いつ確認するか」の違いです。これだけで、あなたが追加でお金を賭けたとき（ダブルダウン・スプリット）に損をする可能性が変わってきます。

まずは下の図で、3つの方式が「カードを配る順番」と「確認するタイミング」がどう違うかを見てください。
""")
        st.pyplot(holecard_timeline_figure())
        st.markdown("""\
---

#### それぞれ何が違う？

| 方式 | カードを配る順番 | ディーラーがBJか確認するタイミング | あなたへの影響 |
|------|----------------|----------------------------------|---------------|
| **HC**（米国式） | 最初から表1枚＋裏1枚を配る | あなたが行動する**前**に確認 | ディーラーがBJでないと分かった状態で行動できる＝最も安心 |
| **ANHC**（豪州式） | 最初は表1枚だけ配る | あなたが行動した**後**に2枚目を引く | ディーラーがBJでも、追加で賭けた分（ダブル・スプリット）は**返ってくる** |
| **ENHC**（欧州式） | 最初は表1枚だけ配る | あなたが行動した**後**に2枚目を引く | ディーラーがBJだと、追加で賭けた分（ダブル・スプリット）も**没収される** |

つまり「いつ確認するか」はANHCとENHCで同じですが、ANHCには**追加ベットを守ってくれる保険**があり、ENHCにはそれが**ない**、という1点だけが大きな違いです。

#### 没収される金額をイメージしてみる

例えば $100 を賭けてダブルダウンし、賭け金が $200 になった直後にディーラーがブラックジャックだったとします。
""")
        st.pyplot(holecard_loss_example_figure())
        st.markdown("""\
ANHCなら没収は最初の$100だけで、ダブルした分の$100は戻ってきます。ENHCは追加分も含めて$200が丸ごと没収されます。**この差があるからこそ、ENHCでは「ダブルやスプリットを少し控える」のが正解になる**のです。

#### 結論：ENHCでは戦略をこう変える

ENHCは「追加ベットが保護されない」ため、HCで正解だったダブル・スプリットの一部が、ENHCでは逆に不正解（ヒットやサレンダーが正解）になります。

| ハンド | HCでの正解 | ENHCでの正解 | なぜ変わる？ |
|--------|------------|-------------|------|
| Hard 11 vs A | **D（ダブル）** | H（ヒット） | ディーラーがBJの確率は約4/13もあり、ダブル分が没収されるリスクが大きすぎる |
| Hard 14 vs 10 | H（ヒット） | **R（サレンダー）** | BJリスクのせいでスタンドの期待値が−0.50を下回るため、半分だけ失うサレンダーの方がマシ |
| Pair 8,8 vs A | **P（スプリット）** | H（ヒット） | スプリット分も没収されるリスクがあるため、無理に増やさない方が得 |

> 💡 ANHCはこの表の心配がなく、戦略はHCとほぼ同じです。違うのはENHCだけ、と覚えておけば十分です。
>
> このシミュレーターでは、ENHC選択時にディーラー10/A対面のダブルに関するTCインデックスも自動的に無効化されます。
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

    with st.expander("ペネトレーション（シミュレーション用）"):
        st.markdown("""\
**一言でいうと**：シュー（複数デッキをまとめて入れる箱）の中身を、シャッフルするまでに**どれくらい配り切るか**という割合です。

カウンティングは「残りデッキに何が多く残っているか」を読む技術なので、配る量が多いほど数字が信頼でき、カウンターにとって有利になります。
""")
        st.pyplot(penetration_figure())
        st.markdown("""\
| ペネトレーション | 6デッキ換算 | カウンティング精度 |
|---------------|------------|----------------|
| 50% | 3デッキ配布 | 低（TCが収束しにくい） |
| 75% | 4.5デッキ配布 | 中（現実的な標準） |
| 83% | 5デッキ配布 | 高 |
| 100%（=CSM） | 全デッキ配布扱い | 無効（毎ハンド・リシャッフル） |

> 💡 CSM（連続シャッフルマシン）は配るそばからシャッフルし直すため、カウンティングは完全に無効です。**本ツールではペネトレーションのスライダーを最大（100%）にするとCSM相当として扱い、シミュレーターが毎ハンド・リシャッフルします**（カウンティングが効かない状況を再現）。
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

    with st.expander("Hi-Lo カードカウンティング"):
        st.markdown("""\
**一言でいうと**：場に出たカードを見て「デッキに10点札・Aがどれだけ濃く残っているか」を頭の中で数える技術です。10点札・Aが多く残っているほど、あなた（プレイヤー）に有利になります（ブラックジャックが出やすい、ディーラーがバーストしやすいため）。

やることはシンプルで、カードが出るたびに下の3グループのどれかに当てはめて、タグの数字を足していくだけです。
""")
        st.pyplot(hilo_tag_figure())
        st.markdown("""\
この「足していった合計」を **ランニングカウント（RC）** と呼びます。
""")

    with st.expander("ランニングカウント（RC）/ トゥルーカウント（TC）"):
        st.markdown("""\
**RC（ランニングカウント）**：Hi-Loのタグをゲーム開始からずっと足し続けた合計値。シューがシャッフルされるまでリセットしません。

**TC（トゥルーカウント）**：RCを「残りデッキ数」で割った値。RCをそのまま使うと、デッキが多く残っているか少ないかで「濃さ」の感覚がズレてしまうため、これを補正する数字です。

下の例では、8枚のカードが出てRCが積み上がり、残り3デッキで割ってTCに変換する流れを示しています。
""")
        st.pyplot(running_to_true_count_figure())
        st.markdown("""\
| TC | 状況 | 推奨行動 |
|----|------|---------|
| −2以下 | デッキに小カードが多い | 最小ベット |
| 0前後 | 中立 | 最小ベット、BSどおり |
| +1〜+2 | やや有利 | ベットを増やし始める |
| +3以上 | 大きく有利 | ベット最大、インシュランスも検討 |
""")

    with st.expander("インシュランス（Insurance）"):
        st.markdown("""\
**一言でいうと**：ディーラーのアップカードが **A** のときだけ提示される「ディーラーがブラックジャックかどうか」に賭ける別枠の賭けです。当たれば2:1（賭けた額の2倍）がもらえます。

**基本的には取るべきではありません。** なぜなら、デッキの中で10点札（10・J・Q・K）が占める割合は、ニュートラルな状態では約30.8%しかなく、2:1で払われるこの賭けが得になるには33.3%（3枚に1枚）を超える必要があるからです。
""")
        st.pyplot(insurance_ev_figure())
        st.markdown("""\
カードカウンティングでTCが上がっている（＝10点札が濃く残っている）場面では、この割合が33.3%を超えることがあり、そのときだけインシュランスが数学的にプラスになります。

> このアプリでは、TCが+3以上になると自動的にインシュランスを勧める通知が表示されます。
""")

    with st.expander("Illustrious 18 / Fab 4"):
        st.markdown("""\
**一言でいうと**：「普段はベーシックストラテジー(BS)通りに打つが、TCがある数字を超えたらアクションを変えた方が得」という、覚える価値のある例外パターン集です。

**Illustrious 18**＝プレイ判断を変える価値が最も高い18パターン、**Fab 4**＝サレンダー判断を変える価値が高い4パターン、という意味です。

最も有名な例が「16 vs 10」です。普段はヒット（H）が正解ですが、TCが0以上になった瞬間にスタンド（S）が正解に切り替わります。
""")
        st.pyplot(index_play_figure())
        st.markdown("""\
他の代表例:

| ハンド | ディーラー | 普段のBS | 切り替わるTC | 切り替え後 |
|--------|-----------|-----|--------|------------------|
| 9 | 2 | H | TCが+1以上 | **D（ダブル）** |
| インシュランス | A | 取らない | TCが+3以上 | **取る** |
| 15 | 10 | H/S | TCが+4以上 | **R（サレンダー）** |

全一覧は「インデックスプレイ」タブで確認できます。
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
