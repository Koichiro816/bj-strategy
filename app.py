"""
app.py — Streamlit ウェブアプリ（スマホ対応）
"""

import hashlib
import json
import os
import random
import tempfile
import time as _time
from urllib.parse import quote, unquote

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    import extra_streamlit_components as stx
except Exception:  # 依存が無い環境でもアプリ本体は動く
    stx = None

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


_AUTH_COOKIE = "bj_auth"


def _auth_token(pw):
    """パスワードから認証トークン（Cookie保存用）を生成する。平文は保存しない。"""
    return hashlib.sha256(("bj-auth-v1:" + str(pw)).encode()).hexdigest()[:32]


def _check_password():
    """パスワード認証。secrets に PASSWORD が設定されていない場合は認証をスキップ。
    一度ログインすると第一者Cookieに認証トークンを保存し、モバイルでの
    WebSocket再接続やリロードでもログイン画面に戻らない（セッション消失対策）。"""
    try:
        correct = st.secrets["PASSWORD"]
    except (KeyError, FileNotFoundError):
        return  # ローカル開発時はスキップ

    expected = _auth_token(correct)
    st.session_state["_auth_expected"] = expected  # 後段でCookieへ保存する際に使用

    if st.session_state.get("authenticated"):
        return

    # Cookie による自動ログイン（サーバー側で読めるため再接続でも即復帰）
    try:
        if st.context.cookies.get(_AUTH_COOKIE) == expected:
            st.session_state.authenticated = True
            return
    except Exception:
        pass

    st.markdown(
        '<div style="max-width:360px;margin:80px auto;">', unsafe_allow_html=True)
    st.title("🃏 BJ Strategy")
    pw = st.text_input("パスワード", type="password", label_visibility="collapsed",
                       placeholder="パスワードを入力してください")
    if st.button("ログイン", width='stretch', type="primary"):
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
        st.markdown("### 🎫 アクセスプラン")
        if st.session_state.is_pro:
            st.success("PRO 機能が有効です")
            st.caption("シミュレーター・インデックス・PDF出力が利用できます。")
            if st.button("ログアウト（無料に戻す）", width='stretch'):
                st.session_state.is_pro = False
                st.rerun()
        else:
            st.info("現在 **無料プラン**（ベーシックストラテジー表のみ）")
            code = st.text_input(
                "PROアクセスコード", type="password",
                placeholder="購入時に発行されたコードを入力",
                help="シミュレーター・インデックスプレイ・PDF出力を解放します。")
            if st.button("PROを有効化", width='stretch', type="primary"):
                if code.strip() in _get_pro_codes():
                    st.session_state.is_pro = True
                    st.rerun()
                else:
                    st.error("コードが正しくありません。")
            # TODO: 決済導線（Stripe/Gumroad）の購入リンクをここに設置する
            st.caption("PRO版では、実際に何手打つとどうなるかを試せる"
                       "シミュレーターや、資金を失う確率の見える化（破産確率）、"
                       "カウンティング時の例外プレイ、PDF出力が使えるようになります。")
    return st.session_state.is_pro


IS_PRO = _render_pro_gate()


def _line_url():
    """LINE友だち追加URL（secrets の LINE_URL）。未設定なら空文字。"""
    try:
        return st.secrets.get("LINE_URL", "") or ""
    except Exception:
        return ""


def _tool_url():
    """このツールの公開URL（シェア用）。"""
    try:
        return st.context.url or ""
    except Exception:
        return ""


def _render_line_cta(key_suffix="", show_admin_hint=False):
    """LINE友だち追加の常設CTA（リードマグネットの集客導線）。

    LINE_URL未設定時は一般ユーザーに何も表示しない（裏側を見せない）。
    管理者向けの設定メモは show_admin_hint=True のときだけ表示する。"""
    url = _line_url()
    if not url and not show_admin_hint:
        return
    href = url if url else "#"
    st.markdown(
        f'<a href="{href}" target="_blank" rel="noopener" '
        f'style="display:block;text-decoration:none;margin:6px 0;">'
        f'<div style="background:#06C755;color:#ffffff;border-radius:12px;'
        f'padding:13px 14px;text-align:center;font-weight:800;font-size:0.95rem;'
        f'box-shadow:0 2px 8px rgba(6,199,85,.35);line-height:1.4;">'
        f'💬【無料】あなたの遊ぶお店のルール早見＆ツール更新をLINEで受け取る'
        f'<div style="font-size:0.72rem;font-weight:600;opacity:.92;margin-top:2px;">'
        f'タップで友だち追加（無料）</div></div></a>',
        unsafe_allow_html=True)
    if not url:
        st.caption("※管理者向け: secrets.toml に LINE_URL を設定するとリンクが有効化されます。")


def _render_share_home():
    """SNSシェアとホーム画面追加の導線（バイラル＋定着）。"""
    url = _tool_url()
    if url:
        txt = quote("ブラックジャックの最善手が一目でわかる無料ツール🃏")
        u = quote(url)
        x_url = f"https://twitter.com/intent/tweet?text={txt}&url={u}"
        line_url = f"https://social-plugins.line.me/lineit/share?url={u}"
        st.markdown(
            f'<div style="display:flex;gap:8px;margin:4px 0;">'
            f'<a href="{x_url}" target="_blank" rel="noopener" style="flex:1;text-decoration:none;">'
            f'<div style="background:#111;color:#fff;border-radius:8px;padding:8px;'
            f'text-align:center;font-weight:700;font-size:0.82rem;">𝕏 でシェア</div></a>'
            f'<a href="{line_url}" target="_blank" rel="noopener" style="flex:1;text-decoration:none;">'
            f'<div style="background:#06C755;color:#fff;border-radius:8px;padding:8px;'
            f'text-align:center;font-weight:700;font-size:0.82rem;">LINEでシェア</div></a>'
            f'</div>', unsafe_allow_html=True)
    with st.expander("📱 ホーム画面に追加してアプリのように使う"):
        st.markdown(
            "ホーム画面に置くと、次回からワンタップで起動でき、保存した設定も"
            "そのまま残ります。\n\n"
            "- **iPhone（Safari）**：下部の共有ボタン → 「ホーム画面に追加」\n"
            "- **Android（Chrome）**：右上メニュー → 「ホーム画面に追加」")


_POLICY_TEXT = (
    "本ツールはブラックジャックの数理・戦略を学ぶための<strong>学習用シミュレーター</strong>です。"
    "日本国内で金銭を賭けて行う賭博は刑法で禁じられており、"
    "<strong>オンラインカジノ等の賭博行為を推奨・勧誘するものではありません</strong>。"
    "海外の合法な環境、または金銭の賭け・換金を伴わないアミューズメント施設でのプレイを想定しています。"
    "<strong>ギャンブルは20歳から。のめり込みにご注意ください</strong>"
    "（相談窓口：ギャンブル依存症問題を考える会 等）。"
)


def _render_policy_notice(compact=False):
    """賭博の適法性・利用目的・年齢・依存症配慮に関する常設の免責表示。
    compact=True はサイドバー向けの小さめ表示。"""
    if compact:
        st.markdown(
            f'<div style="font-size:0.66rem;color:#78909C;line-height:1.5;'
            f'margin-top:8px;">{_POLICY_TEXT}</div>',
            unsafe_allow_html=True)
    else:
        st.markdown(
            f'<div style="background:#ECEFF1;border:1px solid #CFD8DC;'
            f'border-radius:10px;padding:12px 16px;margin:18px 0 4px;'
            f'font-size:0.74rem;color:#546E7A;line-height:1.7;">'
            f'⚠️ {_POLICY_TEXT}</div>',
            unsafe_allow_html=True)


with st.sidebar:
    st.markdown("---")
    _render_line_cta(show_admin_hint=True)
    _render_share_home()
    _render_policy_notice(compact=True)


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
st.markdown(
    '<div style="margin:-6px 0 10px;color:#455A64;font-size:0.94rem;'
    'line-height:1.55;">遊ぶ卓の<strong>最善手</strong>と'
    '<strong>カジノの取り分（ハウスエッジ）</strong>が一目でわかる、'
    '数理で楽しむブラックジャック学習ツールです。</div>',
    unsafe_allow_html=True)

# ===========================================================================
# ハウスルール入力
# ===========================================================================
# ── ルールセット（プリセット）定義 ────────────────────────────────
# 名前 → 各ウィジェット(key)に流し込む値。新しい店舗ルールはここに追加するだけ。
RULESET_PRESETS = {
    "アミューズメントA（ENHC・アーリーサレンダー型）": {
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
    "アミューズメントB（H17・CSM型）": {
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
        "hr_surrender_vs_ace": True,   # エース対面でもサレンダー可
        "hr_decks_dealt": 6.0,   # CSM卓＝毎ハンド実質リシャッフル（100%扱い）
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

# ユーザーが自分で保存したカスタムプリセット。
# 第一者 Cookie（extra-streamlit-components の CookieManager）に保存する。
# CookieManager は Streamlit と同一オリジンで動くため第一者 Cookie を書け、
# アプリを完全に閉じても各自の端末（同一ブラウザ）に残る。次回起動時は
# サーバー側の st.context.cookies から読める（コンポーネント往復不要で安定）。
_PRESET_COOKIE = "bj_user_presets"

# CookieManager は一度だけ生成。値が変わらない限り再実行を誘発しないため
# ①②のようなウィジェットリセットは起きない。
_cookie_manager = stx.CookieManager(key="bj_cookie_mgr") if stx is not None else None

# 認証トークンを第一者Cookieに保存（未保存のときだけ）。以後リロード/再接続で
# サーバー側が読み取り、ログイン画面に戻らずに自動復帰できる。
_auth_expected = st.session_state.get("_auth_expected")
if (_auth_expected and st.session_state.get("authenticated")
        and _cookie_manager is not None):
    try:
        if st.context.cookies.get(_AUTH_COOKIE) != _auth_expected:
            _cookie_manager.set(_AUTH_COOKIE, _auth_expected, key="set_auth",
                                max_age=2592000, same_site="lax")  # 30日
    except Exception:
        pass


def _cookie_presets():
    """CookieManager が保持するプリセット辞書を返す（無ければ空辞書）。
    CookieManager.__init__ が getAll 済みで、フロント側のハイドレーション後の
    再実行で実際の値が入る。読み取りはライブラリ自身の get を使う。"""
    if _cookie_manager is None:
        return {}
    try:
        raw = _cookie_manager.get(_PRESET_COOKIE)
    except Exception:
        raw = None
    if not raw:
        return {}
    try:
        parsed = json.loads(unquote(raw))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


if "user_presets" not in st.session_state:
    st.session_state["user_presets"] = {}

# Cookie からの復元。ハイドレーション後の再実行で値が届くため、セッションが
# 空のあいだは毎回読みにいく（保存済みの内容は上書きしない）。
if not st.session_state["user_presets"]:
    _restored = _cookie_presets()
    if _restored:
        st.session_state["user_presets"] = _restored


def _persist_user_presets():
    """現在の自分用プリセット一覧を第一者 Cookie に書き出す（1年間有効）。
    保存/削除ハンドラ内からのみ呼び、直後に st.rerun() しないこと
    （set はフロント描画で書き込むため、即 rerun すると取りこぼす）。"""
    if _cookie_manager is None:
        return
    presets = st.session_state.get("user_presets", {})
    payload = quote(json.dumps(presets, ensure_ascii=False))
    try:
        _cookie_manager.set(
            _PRESET_COOKIE, payload,
            key="set_presets", max_age=31536000, same_site="lax",
        )
    except Exception:
        pass

# プリセット保存時に集めるハウスルールのキー一覧
_HR_KEYS = list(_HR_DEFAULTS.keys())


def _apply_ruleset():
    """ルールセット選択時、プリセット値を各ウィジェットのsession_stateへ反映する。

    既定プリセット(RULESET_PRESETS)とユーザー保存プリセット(user_presets)の両方を探す。
    """
    # ユーザーが詳細パネルのプリセットを手動で選んだ印（以後は自動同期しない）
    st.session_state["_hr_touched"] = True
    name = st.session_state.get("hr_ruleset")
    preset = (RULESET_PRESETS.get(name)
              or st.session_state.get("user_presets", {}).get(name))
    if preset:
        for _key, _val in preset.items():
            st.session_state[_key] = _val
    # 上の「お店」選択も矛盾なく揃える（プリセット名→同名／カスタム→標準）
    if name in RULESET_PRESETS or name in st.session_state.get("user_presets", {}):
        st.session_state["onb_ruleset"] = name
    else:  # カスタム（手動設定）
        st.session_state["onb_ruleset"] = _ONB_STANDARD


# はじめての方向けオンボーディング：お店を選ぶ1問だけでルールを自動セット
_ONB_STANDARD = "まだ決めていない・標準設定でOK"
_ONB_COOKIE = "bj_onb_choice"


def _apply_onboarding():
    """オンボーディングの1問選択を、下のハウスルール設定へそのまま流し込む。
    プリセット名なら該当値を、「標準設定でOK」なら無難な既定値を適用し、
    下の詳細パネル(hr_ruleset)の選択表示も同期させる。"""
    name = st.session_state.get("onb_ruleset")
    preset = (RULESET_PRESETS.get(name)
              or st.session_state.get("user_presets", {}).get(name))
    if preset:
        for _key, _val in preset.items():
            st.session_state[_key] = _val
        st.session_state["hr_ruleset"] = name
    elif name == _ONB_STANDARD:
        for _key, _val in _HR_DEFAULTS.items():
            st.session_state[_key] = _val
        st.session_state["hr_ruleset"] = "カスタム（手動設定）"


def _read_onb_choice():
    """前回選んだお店（Cookie）を返す。無ければ None。"""
    if _cookie_manager is None:
        return None
    try:
        return _cookie_manager.get(_ONB_COOKIE)
    except Exception:
        return None


def _on_onb_change():
    """お店ラジオをユーザーが操作したら、操作済みフラグを立ててルールを適用。
    お店を選び直したら詳細パネルの手動フラグは解除し、再び自動同期させる。"""
    st.session_state["_onb_touched"] = True
    st.session_state["_hr_touched"] = False
    _apply_onboarding()


def _persist_onb_choice():
    """選んだお店を第一者 Cookie に記憶（次回のデフォルトにする・1年間有効）。
    コールバック外の本体から呼び、直後に st.rerun() しないこと。"""
    if _cookie_manager is None:
        return
    try:
        _cookie_manager.set(
            _ONB_COOKIE, st.session_state.get("onb_ruleset", _ONB_STANDARD),
            key="set_onb", max_age=31536000, same_site="lax",
        )
    except Exception:
        pass


def _preset_to_rules(preset):
    """ハウスルール辞書(hr_*キー)を HouseRules に変換する（ハウスエッジ計算用）。"""
    g = preset.get
    bj = str(g("hr_bj_pay", ""))
    hc = str(g("hr_hole_card", ""))
    num_decks = int(g("hr_num_decks", 6))
    dd = g("hr_decks_dealt")
    penetration = (dd / num_decks) if dd else 0.75  # HEには影響しないが整合のため
    return HouseRules(
        num_decks=num_decks,
        blackjack_pays=1.5 if bj.startswith("3:2") else 1.2,
        soft17="S17" if str(g("hr_soft17", "")).startswith("S17") else "H17",
        double_allowed=str(g("hr_double", "any")).split("（")[0].strip() or "any",
        double_after_split=bool(g("hr_das", True)),
        split_aces=bool(g("hr_split_aces", True)),
        draw_to_split_aces=bool(g("hr_draw_split_aces", False)),
        max_splits=int(g("hr_max_splits", 3)),
        surrender=str(g("hr_surrender", "late")).split("（")[0].strip() or "none",
        surrender_vs_ace=bool(g("hr_surrender_vs_ace", False)),
        penetration=penetration,
        dealer_peeks=not hc.startswith("ENHC"),
    )


def _preset_house_edge(preset):
    """プリセットのハウスエッジ(%)を返す。計算不能なら None。"""
    try:
        return house_edge_wizard(_preset_to_rules(preset))
    except Exception:
        return None


def _onb_label(name):
    """お店ラジオの表示ラベル：『店名 ｜ ハウスエッジ』。"""
    preset = (_HR_DEFAULTS if name == _ONB_STANDARD
              else (RULESET_PRESETS.get(name)
                    or st.session_state.get("user_presets", {}).get(name, {})))
    he = _preset_house_edge(preset)
    if he is None:
        return name
    return f"{name}　🎰 ハウスエッジ {he:.2f}%"


_GUIDE_IMG_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "assets", "guide")


def _img_popover(label, filename, caption):
    """ルール設定の隣に置く「📷 見分け方」ポップオーバー（押すと写真が出る）。"""
    with st.popover(label, width='stretch'):
        _p = os.path.join(_GUIDE_IMG_DIR, filename)
        if os.path.exists(_p):
            st.image(_p, width='stretch')
        st.caption(caption)


# ─── 使い方ステップ（折り畳み・一度見れば十分なのでデフォルト閉） ───
with st.expander("📋 使い方は3ステップ（はじめての方はこちら）", expanded=False):
    st.markdown(
        '<div style="font-size:0.9rem;color:#1B3D24;line-height:1.7;">'
        '<strong>Step 1.</strong> 下の「⚙️ ハウスルール設定」で、遊ぶ卓の条件を選ぶ'
        '（ルールが分からなければ各項目の「📷 見分け方」ボタンで写真を確認）<br>'
        '<strong>Step 2.</strong> 「ベーシックストラテジー」タブの<strong>⚡クイック判定</strong>で、'
        '自分の2枚とディーラーのカードを選ぶ<br>'
        '<strong>Step 3.</strong> 表示された<strong>最善手</strong>のとおりにプレイ。'
        'その卓の<strong>ハウスエッジ（カジノの取り分）</strong>も自動で表示されます。</div>',
        unsafe_allow_html=True)

# ─── はじめての方へ：お店を選ぶだけ ───
st.markdown(
    '<div style="background:#FFF8E1;border:1px solid #FFD54F;border-radius:10px;'
    'padding:12px 16px 4px;margin-bottom:6px;font-size:0.92rem;color:#5D4037;'
    'line-height:1.6;">'
    '<span style="font-weight:800;">🔰 はじめての方へ</span> — '
    'まずは<strong>遊ぶお店を選ぶだけ</strong>。あとのルール設定は自動で入ります。'
    '</div>',
    unsafe_allow_html=True)
# 「標準設定でOK」を先頭・デフォルトにし、以降にお店を並べる
_onb_options = ([_ONB_STANDARD] + list(RULESET_PRESETS.keys())
                + list(st.session_state["user_presets"].keys()))
if "onb_ruleset" not in st.session_state:
    st.session_state["onb_ruleset"] = _ONB_STANDARD
    st.session_state["_onb_persisted"] = _ONB_STANDARD
# ユーザー未操作の間は、Cookieのハイドレーション後に前回のお店を復元して適用。
# 初回描画ではCookieがまだNoneを返すため、復元できるまで毎回試みる。
if (not st.session_state.get("_onb_touched")
        and not st.session_state.get("_onb_restored")):
    _remembered = _read_onb_choice()
    if _remembered in _onb_options:
        st.session_state["onb_ruleset"] = _remembered
        st.session_state["_onb_persisted"] = _remembered
        st.session_state["_onb_restored"] = True
        _apply_onboarding()
st.radio(
    "お店を選んでください",
    _onb_options,
    key="onb_ruleset",
    on_change=_on_onb_change,
    format_func=_onb_label,
)
# 選択が変わったら Cookie に記憶（次回のデフォルトにする）。コールバック外の
# 本体で行うことでコンポーネント描画が可能。直後に st.rerun() しない。
if st.session_state.get("_onb_persisted") != st.session_state["onb_ruleset"]:
    _persist_onb_choice()
    st.session_state["_onb_persisted"] = st.session_state["onb_ruleset"]
if st.session_state["onb_ruleset"] == _ONB_STANDARD:
    st.caption("お店が分からない／一覧にない場合はこのまま（標準設定）でOKです。"
               "決まっている場合は上からお店を選ぶと、ルールが自動でセットされます。")
else:
    st.caption("✅ 「" + st.session_state["onb_ruleset"] + "」のルールを自動セットしました。"
               "次回もこの選択が記憶され、最初から選ばれた状態で開きます。"
               "卓ごとの違いを微調整したいときだけ、下の「⚙️ ハウスルール設定」を開いてください。")

# メイン動線上の集客導線（LINE_URL未設定時は何も表示しない）
_render_line_cta(key_suffix="_main")

# 詳細パネルのプリセット選択を「お店」選択に同期する安全網（ラジオ生成前に実行）。
# モバイルのCookieハイドレーション競合等で片方だけ同期に失敗しても、ここで必ず
# 一致させる。ユーザーが詳細パネルのプリセットを手動で選んだ場合(_hr_touched)は尊重。
if not st.session_state.get("_hr_touched"):
    _onb_now = st.session_state.get("onb_ruleset", _ONB_STANDARD)
    _hr_target = (_onb_now if (_onb_now in RULESET_PRESETS
                               or _onb_now in st.session_state["user_presets"])
                  else "カスタム（手動設定）")
    if st.session_state.get("hr_ruleset") != _hr_target:
        st.session_state["hr_ruleset"] = _hr_target
        # ラベルだけでなく実ルールも揃える（プリセットのとき）
        _hp = (RULESET_PRESETS.get(_hr_target)
               or st.session_state["user_presets"].get(_hr_target))
        if _hp:
            for _hk, _hv in _hp.items():
                st.session_state[_hk] = _hv

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
                 "early＝確認前に降りられる強力な方式。"
                 "※ENHC（ノーホールカード）卓ではディーラーが2枚目を引く前に降りられるため、"
                 "実質アーリーサレンダーとして扱います。")
        surrender_vs_ace_ui = st.checkbox(
            "エース対面でのサレンダー可", key="hr_surrender_vs_ace",
            help="ディーラーのアップカードがA（エース）のときもサレンダーできるか。")
        _pen_max = float(num_decks)   # 最大＝毎ハンド実質リシャッフル（CSM相当）
        _pen_min = float(max(1, num_decks // 2))
        # 1デッキ卓では min==max になりスライダーが例外を出すため、必ず min<max を保証
        if _pen_min >= _pen_max:
            _pen_min = _pen_max - 0.5
        # decks_dealt は num_decks に依存。session_state値を範囲にクランプしてから使う
        _dd = st.session_state.get("hr_decks_dealt")
        if _dd is None:
            _dd = num_decks * 0.75
        _dd = min(max(_pen_min, round(_dd * 2) / 2), _pen_max)
        st.session_state["hr_decks_dealt"] = _dd   # スライダー生成前なので変更OK
        decks_dealt = st.slider(
            "何デッキ使うごとにシャッフルするか（シミュ用・最大＝毎ハンド実質リシャッフル／CSM相当）",
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
               "次回から上の一覧・「🔰 はじめての方へ」でワンタップ呼び出し。"
               "※ 保存内容はお使いのブラウザ（第一者Cookie）に残ります。"
               "アプリを完全に閉じても、同じ端末・同じブラウザなら次回も自動で復元されます"
               "（別の端末やシークレットモードには引き継がれません）。")
    _save_name = st.text_input(
        "プリセット名", key="hr_preset_name", placeholder="例：六本木○○カジノ")
    _ps1, _ps2 = st.columns(2)
    with _ps1:
        if st.button("現在の設定を保存", width='stretch'):
            _nm = (_save_name or "").strip()
            if not _nm:
                st.warning("プリセット名を入力してください。")
            elif _nm in RULESET_PRESETS or _nm == "カスタム（手動設定）":
                st.warning("その名前は既定プリセットと重複します。別の名前にしてください。")
            else:
                st.session_state["user_presets"][_nm] = {
                    _key: st.session_state[_key] for _key in _HR_KEYS}
                st.session_state["_preset_saved_flag"] = True
                # Cookie へ書き込み。set はフロント描画で反映されるため、
                # ここで st.rerun() せず CookieManager の再実行に任せる（取りこぼし防止）。
                _persist_user_presets()
    with _ps2:
        _user_names = list(st.session_state["user_presets"].keys())
        if _user_names:
            _del = st.selectbox(
                "保存済みを削除", ["（選択）"] + _user_names, key="hr_preset_del")
            if st.button("選択を削除", width='stretch') and _del in _user_names:
                del st.session_state["user_presets"][_del]
                if st.session_state.get("hr_ruleset") == _del:
                    st.session_state["hr_ruleset"] = "カスタム（手動設定）"
                # 更新後の一覧を Cookie へ反映（即 rerun しない：取りこぼし防止）
                _persist_user_presets()
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
st.caption("※ ハウスエッジ＝カジノ側の取り分。低いほどプレイヤーに有利です。")
with st.expander("計算方法について"):
    st.markdown(
        "この数値は **Wizard of Odds 公表値ベースの加法モデルによる近似**です"
        "（連続シャッフラー基準・誤差±0.05〜0.1%）。"
        "カットカード使用卓では実測が約+0.1%高くなります。\n\n"
        "精密な検証は "
        "[Wizard of Odds 公式計算機](https://wizardofodds.com/games/blackjack/calculator/) "
        "をご利用ください。")




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
        (f'{_ACTION_ICON["H"]} H = ヒット',     CELL_COLORS["H"], CELL_TEXT["H"]),
        (f'{_ACTION_ICON["S"]} S = スタンド',   CELL_COLORS["S"], CELL_TEXT["S"]),
        (f'{_ACTION_ICON["D"]} D = ダブル',     CELL_COLORS["D"], CELL_TEXT["D"]),
        (f'{_ACTION_ICON["P"]} P = スプリット', CELL_COLORS["P"], CELL_TEXT["P"]),
        (f'{_ACTION_ICON["R"]} R = サレンダー', CELL_COLORS["R"], CELL_TEXT["R"]),
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
# CUD（色覚多様性）対応：色に依存せず形でも識別できるよう各手に記号を割り当てる。
_ACTION_ICON = {"H": "⬆", "S": "✋", "D": "⏫", "P": "✂", "R": "🏳"}
# 10バリュー（10・J・Q・K）は戦略上すべて同じなので1つの選択肢にまとめる。
_TEN_OPT = "10,J,Q,K"
_QUICK_CARD_OPTS = ["2", "3", "4", "5", "6", "7", "8", "9", _TEN_OPT, "A"]
_TEN_DEFAULT = _TEN_OPT


def _opt_rank(o: str) -> int:
    if o == "A":
        return 11
    if o.startswith("10") or o in ("J", "Q", "K"):
        return 10
    return int(o)


def _card_name(r: int) -> str:
    return "A" if r == 11 else str(r)


# 見た目用のスート。戦略には影響しないため、カードの並び位置から機械的に
# 割り当てる（ペアやディーラーと重複しにくい順序）。色は実物どおり赤/黒。
_SUIT_CYCLE = ("♠", "♥", "♣", "♦")
_SUIT_COLOR = {"♠": "#1C2833", "♣": "#1C2833", "♥": "#C0392B", "♦": "#C0392B"}


def _rank_card_html(rank, suit_idx=0):
    """選んだランクをトランプ風カード（角インデックス＋中央スートピップ）で描画。
    10バリューは「10,J,Q,K」を1枚にまとめて表示する。rank が None のときは
    未選択を表す空欄の点線枠を描画する。"""
    W, H = 60, 86
    if rank is None:
        return (
            f'<div style="width:{W}px;height:{H}px;border:2px dashed #cfcfcf;'
            f'border-radius:8px;background:#fafafa;display:flex;align-items:center;'
            f'justify-content:center;color:#c0c0c0;font-size:22px;flex:0 0 auto;">?'
            f'</div>')
    suit = _SUIT_CYCLE[suit_idx % len(_SUIT_CYCLE)]
    color = _SUIT_COLOR[suit]
    idx_label = "10" if rank == _TEN_OPT else rank
    ifs = 13 if idx_label == "10" else 15
    corner = (
        f'<div style="line-height:1;text-align:center;">'
        f'<div style="font-size:{ifs}px;font-weight:800;'
        f'font-family:Georgia,\'Times New Roman\',serif;">{idx_label}</div>'
        f'<div style="font-size:11px;margin-top:1px;">{suit}</div></div>')
    if rank == _TEN_OPT:
        center = (
            f'<div style="text-align:center;line-height:1;">'
            f'<div style="font-size:24px;">{suit}</div>'
            f'<div style="font-size:8.5px;font-weight:700;color:#90A4AE;'
            f'letter-spacing:1.5px;margin-top:4px;">J·Q·K</div></div>')
    else:
        center = f'<div style="font-size:28px;line-height:1;">{suit}</div>'
    return (
        f'<div style="position:relative;width:{W}px;height:{H}px;'
        f'border:1px solid #90A4AE;border-radius:8px;'
        f'background:linear-gradient(155deg,#ffffff 0%,#fcfcfc 60%,#eef1f3 100%);'
        f'box-shadow:0 2px 5px rgba(0,0,0,.28),inset 0 0 0 2px #ffffff;'
        f'color:{color};display:flex;align-items:center;justify-content:center;'
        f'flex:0 0 auto;">'
        f'<div style="position:absolute;top:5px;left:6px;">{corner}</div>'
        f'{center}'
        f'<div style="position:absolute;bottom:5px;right:6px;'
        f'transform:rotate(180deg);">{corner}</div>'
        f'</div>')


def _hand_cards_html(*ranks, suit_offset=0):
    """選んだランク群をカードとして横並びで描画する。
    suit_offset で見た目のスートの開始位置をずらす（ディーラー/複数ハンド用）。"""
    cards = "".join(_rank_card_html(r, suit_offset + i) for i, r in enumerate(ranks))
    return (f'<div style="display:flex;flex-wrap:wrap;gap:8px;justify-content:center;'
            f'margin:4px 0 2px;">{cards}</div>')


def _table_view_html(player_ranks, du):
    """プレイヤー視点の卓レイアウト：ディーラーを上、自分の手札（可変枚数）を下に並べる。"""
    lbl = ('font-size:0.72rem;color:#607D8B;font-weight:700;text-align:center;'
           'letter-spacing:1px;')
    return (
        f'<div style="margin:8px 0 2px;">'
        f'<div style="{lbl}">ディーラー</div>'
        f'{_hand_cards_html(du, suit_offset=3)}'
        f'<div style="border-top:1px dashed #B0BEC5;width:72%;margin:9px auto;"></div>'
        f'<div style="{lbl}">あなたの手札</div>'
        f'{_hand_cards_html(*player_ranks)}'
        f'</div>')


_MARU = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫"


def _maru(n):
    """1〜12を丸数字に。範囲外は (n) で表す。"""
    return _MARU[n - 1] if 1 <= n <= len(_MARU) else f"({n})"


def _hand_total_soft(picks):
    """カード選択リスト（"2".."A","10,J,Q,K"）から合計とソフト判定を返す。"""
    ranks = [_opt_rank(p) for p in picks]
    r0 = ranks[0]
    total, soft = (11, True) if r0 == 11 else (r0, False)
    for r in ranks[1:]:
        total, soft = add_card(total, soft, r)
    return total, soft


def _pills_picker(label, key, default):
    """カードのランクを横並びチップ（st.pills）で選ぶ。ネイティブ部品のため
    セッション状態を保持し、ページ再読み込み（＝ログイン画面復帰）を起こさない。"""
    if st.session_state.get(key) not in _QUICK_CARD_OPTS:
        st.session_state[key] = default
    st.pills(label, _QUICK_CARD_OPTS, selection_mode="single", key=key)
    return st.session_state[key] or default


def _pills_picker_optional(label, key):
    """省略可能なカード選択。デフォルトを注入せず、未選択なら None を返す。
    ヒットで引いた札の追加入力用（勝手に高い札が入ってバーストするのを防ぐ）。"""
    st.pills(label, _QUICK_CARD_OPTS, selection_mode="single", key=key)
    val = st.session_state.get(key)
    return val if val in _QUICK_CARD_OPTS else None


def _reset_quick_hand():
    """クイック判定のカード入力を全て消して空欄に戻す（on_click コールバック）。
    ウィジェット生成前に実行されるため、pop が安全に効く。スプリット各手も消す。"""
    keys = (["q_du", "q_p1", "q_p2"] + [f"q_p{i}" for i in range(3, 12)]
            + [f"q_spa_{i}" for i in range(2, 12)]
            + [f"q_spb_{i}" for i in range(2, 12)])
    for k in keys:
        st.session_state.pop(k, None)


def _dealer_strength_phrase(dup):
    """ディーラーのアップカードの強さを初心者向けの言葉にする。
    自滅（バースト）しやすさの実勢：6≧5＞4＞3＞2 ＞ 7＞8＞9＞10＞A。
    6が最も弱く、Aが最も強い。7は17前後で止まりやすい御しやすい中立札で、
    真に強いのは9・10・A。"""
    name = _card_name(dup)
    if dup == 6:
        return f"ディーラーの{name}は最も自滅（バースト）しやすい、いちばん弱いアップカード"
    if dup == 5:
        return f"ディーラーの{name}は6に次いでバーストしやすい弱いアップカード"
    if dup == 4:
        return f"ディーラーの{name}はバーストしやすい弱めのアップカード"
    if dup in (2, 3):
        return f"ディーラーの{name}はやや弱いアップカード"
    if dup == 7:
        return f"ディーラーの{name}は17前後で止まりやすい、御しやすい中立寄りのアップカード"
    if dup == 8:
        return f"ディーラーの{name}はやや強いアップカード"
    return f"ディーラーの{name}は強いアップカード"  # 9,10,A


def _plain_reason(best, total, soft, pair_rank, dup, evs):
    """最善手の理由を、EVの数字ではなく平易な日本語で説明する（初心者向け）。"""
    dlr = _dealer_strength_phrase(dup)
    vals = sorted(evs.values(), reverse=True)
    close = len(vals) >= 2 and (vals[0] - vals[1]) < 0.03
    tail = "（僅差の選択なので、表通りで大丈夫です）" if close else ""

    if best == "R":
        return (f"{dlr}。この手はどう打っても勝ちにくい、最も不利な組み合わせです。"
                "賭け金の半分を返してもらい、損失を最小限にします（サレンダー）。")
    if best == "P":
        pname = _card_name(pair_rank)
        if pair_rank == 11:
            return ("A のペアは、分ければ2つの手がそれぞれ21に届きやすくなる超有利な形。"
                    "必ず分けます（スプリット）。")
        if pair_rank == 8:
            return ("8 のペアの「16」はそのままでは最も弱い手のひとつ。分けて2つの新しい手を"
                    "作る方がずっと有利です（スプリット）。")
        return (f"{dlr}。{pname} のペアは、分けて2つの手にした方が有利になります（スプリット）。")
    if best == "D":
        why = "A があり安全に伸ばせて" if soft else "あと1枚で大きく伸びやすく"
        return (f"{dlr}。{why}、勝ちやすい場面です。賭けを2倍にして1枚だけ引いて"
                f"勝負します（ダブルダウン）。{tail}")
    if best == "S":
        if soft:
            # ソフトハンドは引いてもバーストしない。改善の見込みが薄いから止める
            return (f"A を含むソフト{total} は、ここから引いても良くなる見込みが小さい手です"
                    "（ソフトなので引いてもバーストはしませんが、引くと"
                    "かえって弱いハードの手になりやすい）。だから止めます"
                    "（スタンド）。あとはディーラーの結果を待ちます。")
        if total >= 19:
            return (f"合計 {total} はそれ自体が十分に強い手です。引く必要はなく、"
                    "引けばバーストの危険が増えるだけなので止めます"
                    "（スタンド）。あとはディーラーの結果を待ちます。")
        if total >= 17:
            return (f"合計 {total} は強い手ではありませんが、ここから1枚引くとバースト"
                    "しやすく、引いても勝率は上がりません。だから損を避けるためにあえて"
                    "引かず止めます（スタンド）。あとはディーラーの結果を待ちます。")
        return (f"{dlr}。あなたの {total} は引くとバーストしやすい手ですが、"
                f"弱いディーラーが自滅（バースト）するのを待つ方が得なので止めます"
                f"（スタンド）。{tail}")
    # H（ヒット）
    if soft:
        # ソフトハンドは A を1として数え直せるためバーストしない
        return (f"A を含むソフト{total} は、引いてもバーストしません"
                "（Aを1として数え直せるため）。リスクなく手を伸ばせるので、"
                f"もう1枚引きます（ヒット）。{tail}")
    if total <= 11:
        return ("この合計なら何を引いてもバーストしません。迷わずもう1枚引いて手を強くします"
                "（ヒット）。")
    return (f"{dlr}。今の {total} のままでは勝ちにくいので、もう1枚引いて手を強くします"
            f"（ヒット）。弱い手のまま止める方が、バーストより危険な場面です。{tail}")


def _hl_prompt(text):
    """次に操作すべき箇所を目立たせる案内バナー（ユーザー誘導用）。"""
    st.markdown(
        f'<div style="background:#FFF3E0;border:2px solid #FB8C00;border-radius:10px;'
        f'padding:10px 14px;margin:8px 0 2px;font-weight:700;color:#E65100;'
        f'font-size:0.95rem;">{text}</div>', unsafe_allow_html=True)


def _action_card(best, hand_desc, dup, insurance=False):
    """最善手の大きな色付きカードを描画する。
    insurance=True のときは大きな表示を『🛡️インシュランス ⇒ 最善手』にする。"""
    bg = CELL_COLORS.get(best, "#ECEFF1")
    fg = CELL_TEXT.get(best, "#37474F")
    _ico = _ACTION_ICON.get(best, "")
    if insurance:
        big = (f'🛡️インシュランス<span style="opacity:.55;"> ⇒ </span>'
               f'{_ico} {_ACTION_NAMES[best]}')
        fs = "1.7rem"
    else:
        big = f'{_ico} {_ACTION_NAMES[best]}'
        fs = "2.0rem"
    st.markdown(
        f'<div style="background:{bg};border-radius:12px;padding:14px 18px;'
        f'text-align:center;margin:6px 0;">'
        f'<div style="font-size:0.8rem;color:{fg};opacity:0.85;font-weight:600;">'
        f'あなたの手: {hand_desc} ／ ディーラー {_card_name(dup)}</div>'
        f'<div style="font-size:{fs};font-weight:800;color:{fg};line-height:1.3;">'
        f'{big}</div>'
        f'<div style="font-size:0.9rem;color:{fg};font-weight:700;">（{best}）</div>'
        f'</div>', unsafe_allow_html=True)


def _reco_details(best, evs, total, soft, pair_rank, dup, tc, rules):
    """推奨の理由・EV・詳細expander・スタンド内訳をまとめて描画する。"""
    best_ev = evs.get(best)
    if best_ev is not None:
        ev_col = "#1B5E20" if best_ev >= 0 else "#B71C1C"
        st.markdown(
            f'<div style="background:#F1F8E9;border-left:4px solid #7CB342;'
            f'border-radius:6px;padding:10px 14px;margin:2px 0 8px;font-size:0.9rem;'
            f'line-height:1.65;color:#33401F;">💡 '
            f'{_plain_reason(best, total, soft, pair_rank, dup, evs)}'
            f'<div style="margin-top:6px;font-size:0.85rem;color:#455A64;">'
            f'この選択の期待値（EV）＝ <strong style="color:{ev_col};">{best_ev:+.3f}</strong>'
            f'（賭け金1単位あたり。プラスなら有利、マイナスなら最も損失の小さい手）</div></div>',
            unsafe_allow_html=True)
    with st.expander("📐 もっと詳しく（各アクションの期待値を数字で比較）", expanded=False):
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

    with st.expander("❓ 期待値（EV）って何？（はじめての方へ）", expanded=False):
        st.markdown(
            "**EV（期待値）＝賭け金1単位につき、その手を1回打つごとに平均でどれだけ"
            "増減するか**を表す数字です。\n\n"
            "たとえば **EV −0.05** は、1単位賭けるたびに<strong>平均0.05単位ずつ損する</strong>"
            "という意味（100回打てば平均で5単位ほどの損になる計算）です。\n\n"
            "- **EVプラス**：長い目で見て<strong>あなたが有利</strong>な場面です。\n"
            "- **EVマイナス**：不利な場面ですが、表示された最善手は"
            "<strong>「数ある選択肢の中で最も損失が小さい打ち方」</strong>です。\n\n"
            "ブラックジャックはもともとカジノがわずかに有利なゲームなので、"
            "EVマイナスの場面は普通にあります。大切なのは"
            "**毎回いちばん損の小さい（＝EVの高い）手を選び続けること**。"
            "それが長期的に負けを最小化する唯一の方法です。",
            unsafe_allow_html=True)
        st.caption("※ 1回ごとの勝ち負けは運で大きく上下します。EVは「同じ場面を"
                   "何度も繰り返したときの平均」を表す指標です。")

    if total >= 12 and total <= 21:
        bd = stand_breakdown(total, dup, rules, tc=tc)
        st.caption(
            f"参考・スタンドした場合: 勝ち {bd['win'] * 100:.0f}% ／ "
            f"引分 {bd['push'] * 100:.0f}% ／ 負け {bd['lose'] * 100:.0f}%")


def _split_action_badge(best, total, hand_desc):
    """スプリット各ハンド用のコンパクトなアクション表示。"""
    if best == "BUST":
        bg, fg, name = "#FFEBEE", "#B71C1C", f"バースト（{total}）💥"
    else:
        bg = CELL_COLORS.get(best, "#ECEFF1")
        fg = CELL_TEXT.get(best, "#37474F")
        name = _ACTION_NAMES.get(best, best)
    return (
        f'<div style="background:{bg};border-radius:10px;padding:8px 12px;'
        f'text-align:center;margin:2px 0 6px;">'
        f'<div style="font-size:0.72rem;color:{fg};opacity:.85;font-weight:600;">'
        f'{hand_desc}</div>'
        f'<div style="font-size:1.3rem;font-weight:800;color:{fg};">{name}</div></div>')


def _play_split_hand(title, prefix, pair_opt, du, dup, rules, tc):
    """スプリットした1つの手をプレイアウトする（2枚目入力→段階的ヒット）。"""
    st.markdown(f"**{title}**（{_card_name(_opt_rank(pair_opt))} からスタート）")
    picks = [pair_opt]
    aces = _opt_rank(pair_opt) == 11
    one_card_only = aces and not rules.draw_to_split_aces
    best, evs, total, soft, awaiting = "S", {}, 0, False, False
    while True:
        n = len(picks)
        total, soft = _hand_total_soft(picks)
        if n < 2:
            _hl_prompt(f"👇 {title}に配られた2枚目のカードを選んでください")
            nxt = _pills_picker_optional(
                f"{title}・カード②（配られた札）", f"{prefix}_{n + 1}")
            if nxt is None:
                awaiting = True
                break
            picks.append(nxt)
            continue
        if total > 21:
            best = "BUST"
            break
        if one_card_only:  # スプリットしたエースは1枚のみ（引き足し不可）
            best = "S"
            evs = {}
            break
        _, evsf = evaluate_hand(total, soft, False, dup, rules, tc=tc)
        evs = {"S": evsf["S"], "H": evsf["H"]}
        if n == 2 and rules.double_after_split and "D" in evsf:
            evs["D"] = evsf["D"]
        best = max(evs, key=evs.get)
        if best == "H" and total < 21 and n < 11:
            nk = f"{prefix}_{n + 1}"
            if st.session_state.get(nk) not in _QUICK_CARD_OPTS:
                _hl_prompt(f"👇 {title}でヒット！引いたカードを選んでください")
            nxt = _pills_picker_optional(
                f"{title}・カード{_maru(n + 1)}（引いた札）", nk)
            if nxt is None:
                awaiting = True
                break
            picks.append(nxt)
            continue
        break

    st.markdown(
        _hand_cards_html(*picks, suit_offset=(1 if prefix.endswith("b") else 0)),
        unsafe_allow_html=True)
    if awaiting:
        return
    names = ",".join(_card_name(_opt_rank(p)) for p in picks)
    kind = "ソフト" if soft else "ハード"
    hd = f"{names} = {kind}{total}"
    st.markdown(_split_action_badge(best, total, hd), unsafe_allow_html=True)
    if best == "D":
        st.caption("ダブルダウン：もう1枚だけ引いて賭け金を倍に（この手はここで完了）。")
    elif one_card_only:
        st.caption("スプリットしたエースは1枚ずつしか引けないルールのため、"
                   "ここでスタンドです。")


def render_quick_decision(rules, tc):
    """自分の2枚＋ディーラーのアップカードから最善手と各アクションEVを即表示する。"""
    st.markdown("##### ⚡ クイック判定（自分の手とディーラーを選ぶだけ）")
    st.caption("スマホでも一目。自分の2枚とディーラーのアップカードを選ぶと、"
               "最善手と「なぜ」を即表示します。表を探す必要はありません。")
    st.caption("↓ ランクをタップして選んでください")
    # 下の卓表示（ディーラー上・自分下）に合わせ、選択も同じ順に並べる。
    # 初期状態は全て空欄（未選択）。3枚とも選ぶまで判定は出さない。
    du = _pills_picker_optional("ディーラーのアップカード", "q_du")
    p1 = _pills_picker_optional("自分のカード①", "q_p1")
    p2 = _pills_picker_optional("自分のカード②", "q_p2")

    # リセット（選択があるときだけ表示）。全カードを空欄に戻す。
    _extra_keys = [f"q_p{i}" for i in range(3, 12)]
    _split_keys = ([f"q_spa_{i}" for i in range(2, 12)]
                   + [f"q_spb_{i}" for i in range(2, 12)])
    _any_selected = any(
        st.session_state.get(k) in _QUICK_CARD_OPTS
        for k in ["q_du", "q_p1", "q_p2"] + _extra_keys + _split_keys)
    if _any_selected:
        st.button("🔄 リセット（カードを全て消す）", key="q_reset",
                  on_click=_reset_quick_hand)

    # 未選択がある間は、卓を空欄表示して選択を促す
    if du is None or p1 is None or p2 is None:
        st.markdown(_table_view_html([p1, p2], du), unsafe_allow_html=True)
        st.info("ディーラーのアップカードと、自分のカード①②を選ぶと、"
                "最善手を表示します。")
        st.markdown("---")
        return

    c1, c2, dup = _opt_rank(p1), _opt_rank(p2), _opt_rank(du)
    is_pair = (c1 == c2)
    is_bj = (c1 == 11 and c2 == 10) or (c1 == 10 and c2 == 11)

    # ── インシュランス（ディーラーがA のときだけ判定）──
    # 推奨時は大きなアクション表示に『🛡️インシュランス ⇒ 最善手』として統合。
    ins_take = (dup == 11 and should_take_insurance(tc))
    if dup == 11 and not ins_take and not is_bj:
        st.caption(f"🛡️ インシュランスは不要（TC {tc:+d} ＜ +{get_insurance_threshold()}）。")

    if is_bj:
        st.markdown(_table_view_html([p1, p2], du), unsafe_allow_html=True)
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

    # まず2枚で判定
    total2, soft2 = _hand_total_soft([p1, p2])
    pair_rank2 = c1 if is_pair else 0
    best2, evs2 = evaluate_hand(total2, soft2, is_pair, dup, rules,
                                pair_rank=pair_rank2, tc=tc)

    # ── スプリット推奨 → 2つの手に分けてそれぞれプレイアウト ──
    if is_pair and best2 == "P":
        st.markdown(_table_view_html([p1, p2], du), unsafe_allow_html=True)
        hand_desc = (f"{_card_name(c1)},{_card_name(c2)} = ペア"
                     f"（{'ソフト' if soft2 else 'ハード'}{total2}）")
        _action_card("P", hand_desc, dup, insurance=ins_take)
        _reco_details("P", evs2, total2, soft2, pair_rank2, dup, tc, rules)
        st.markdown("---")
        st.markdown("#### ✂️ スプリット後の各ハンドをプレイ")
        st.caption("ペアを2つの手に分けます。各手に配られたカードを選ぶと、"
                   "それぞれの最善手（ヒット／スタンド）が表示されます。")
        _play_split_hand("ハンド1", "q_spa", p1, du, dup, rules, tc)
        st.markdown("")
        _play_split_hand("ハンド2", "q_spb", p2, du, dup, rules, tc)
        st.markdown("---")
        return

    # ── 単一ハンド：最善手がヒットの間、引いたカードを追加入力できる ──
    # 追加カードは「空」で表示し、実際に引いた札を選ぶまで手に加えない。
    picks = [p1, p2]
    best, evs, total, soft = best2, evs2, total2, soft2
    awaiting = False
    while True:
        total, soft = _hand_total_soft(picks)
        n = len(picks)
        if total > 21:
            break  # バースト
        if n == 2:
            best, evs = best2, evs2
        else:
            _, evs_full = evaluate_hand(total, soft, False, dup, rules, tc=tc)
            evs = {"S": evs_full["S"], "H": evs_full["H"]}
            best = "H" if evs["H"] > evs["S"] else "S"
        # 最善手がヒットなら、次に引いたカードの入力欄を「ハイライト付き」で出す
        if best == "H" and total < 21 and n < 11:
            nk = f"q_p{n + 1}"
            if st.session_state.get(nk) not in _QUICK_CARD_OPTS:
                _hl_prompt("👇 ヒットです！引いたカードを、この下で選んでください")
            newpick = _pills_picker_optional(
                f"自分のカード{_maru(n + 1)}（ヒットで引いた札を選ぶ）", nk)
            if newpick is None:
                awaiting = True
                break  # 入力待ち：札を選ぶまでこれ以上増やさない
            picks.append(newpick)
            continue
        break

    pair_rank = c1 if (is_pair and len(picks) == 2) else 0

    # 卓レイアウトで全カードを確認表示
    st.markdown(_table_view_html(picks, du), unsafe_allow_html=True)

    _names = ",".join(_card_name(_opt_rank(p)) for p in picks)
    _kind = "ソフト" if soft else "ハード"
    if is_pair and len(picks) == 2:
        hand_desc = f"{_names} = ペア（{_kind}{total}）"
    else:
        hand_desc = f"{_names} = {_kind}{total}"

    # バースト（合計が21超）
    if total > 21:
        st.markdown(
            '<div style="background:#FFEBEE;border:2px solid #E53935;border-radius:12px;'
            'padding:16px 18px;text-align:center;margin:6px 0;">'
            '<div style="font-size:1.6rem;font-weight:800;color:#B71C1C;">'
            f'バースト（{total}）💥</div>'
            f'<div style="font-size:0.9rem;color:#6D4C41;font-weight:600;margin-top:4px;">'
            f'あなたの手: {hand_desc}。合計が21を超えたので、この手は負けです。'
            '「🔄 リセット」で次の手へ。</div></div>',
            unsafe_allow_html=True)
        st.markdown("---")
        return

    _action_card(best, hand_desc, dup, insurance=ins_take)
    _reco_details(best, evs, total, soft, pair_rank, dup, tc, rules)
    st.markdown("---")


# ===========================================================================
# トレーニング（遊んで覚える練習モード）— 出された手の最善手を当てる
# ===========================================================================
def _deal_training_hand():
    """学習用にランダムな手を配る。10値札は実際の出現率に合わせ4倍の重み。
    ナチュラル（A＋10値）はアクション判断が不要なので配り直す。"""
    weights = [4 if o == _TEN_OPT else 1 for o in _QUICK_CARD_OPTS]
    while True:
        p1, p2, du = random.choices(_QUICK_CARD_OPTS, weights=weights, k=3)
        c1, c2 = _opt_rank(p1), _opt_rank(p2)
        if not ((c1 == 11 and c2 == 10) or (c1 == 10 and c2 == 11)):
            return p1, p2, du


def _hand_analysis(p1, p2, du, rules, tc):
    """選択肢文字列の手を解析し、最善手・各EV・手の属性を返す。"""
    c1, c2, dup = _opt_rank(p1), _opt_rank(p2), _opt_rank(du)
    t1, s1 = (11, True) if c1 == 11 else (c1, False)
    total, soft = add_card(t1, s1, c2)
    is_pair = (c1 == c2)
    pair_rank = c1 if is_pair else 0
    best, evs = evaluate_hand(total, soft, is_pair, dup, rules,
                              pair_rank=pair_rank, tc=tc)
    return best, evs, total, soft, pair_rank, dup


def _tr_deal_card():
    """トレーニング用にランダムな1枚を配る（10値札は出現率に合わせ4倍の重み）。"""
    weights = [4 if o == _TEN_OPT else 1 for o in _QUICK_CARD_OPTS]
    return random.choices(_QUICK_CARD_OPTS, weights=weights, k=1)[0]


def _tr_new_hand(ss):
    """新しい問題（1手）を配って状態を初期化する。"""
    p1, p2, du = _deal_training_hand()
    ss["tr_du"] = du
    ss["tr_hands"] = [{"cards": [p1, p2], "done": False}]
    ss["tr_active"] = 0
    ss["tr_answered"] = None
    ss["tr_progressed"] = False  # ヒット/スプリットで手が進んだか


def _tr_eval(cards, du, rules, tc, ctx):
    """現在の手の判定。ctx: initial(初手2枚) / hit(3枚以上) /
    split2(分割後2枚・DASならD可) / splithit(分割後3枚以上)。"""
    dup = _opt_rank(du)
    total, soft = _hand_total_soft(cards)
    is_pair = (len(cards) == 2 and _opt_rank(cards[0]) == _opt_rank(cards[1]))
    pair_rank = _opt_rank(cards[0]) if is_pair else 0
    if ctx == "initial":
        best, evs = evaluate_hand(total, soft, is_pair, dup, rules,
                                  pair_rank=pair_rank, tc=tc)
    else:
        _, full = evaluate_hand(total, soft, False, dup, rules, tc=tc)
        evs = {"S": full["S"], "H": full["H"]}
        if ctx == "split2" and rules.double_after_split and "D" in full:
            evs["D"] = full["D"]
        best = max(evs, key=evs.get)
    return best, evs, total, soft, is_pair, pair_rank, dup


def _tr_next_hand(ss):
    """未完了の次のハンドへ active を移す（無ければそのまま＝全完了）。"""
    hands = ss["tr_hands"]
    for i in range(ss["tr_active"] + 1, len(hands)):
        if not hands[i]["done"]:
            ss["tr_active"] = i
            return


def _tr_advance(ss, best, rules):
    """正解の最善手に沿って手を進める（配札・分割・完了判定）。"""
    ss["tr_answered"] = None
    hands = ss["tr_hands"]
    active = ss["tr_active"]
    h = hands[active]
    cards = h["cards"]
    if best == "P":
        ss["tr_progressed"] = True
        pc = cards[0]
        aces = _opt_rank(pc) == 11
        newhands = []
        for _ in range(2):
            nh = {"cards": [pc, _tr_deal_card()], "done": False}
            # スプリットしたエースは原則1枚のみ（引き足し不可なら即完了）
            if aces and not rules.draw_to_split_aces:
                nh["done"] = True
            newhands.append(nh)
        hands[active:active + 1] = newhands
        if hands[active]["done"]:
            _tr_next_hand(ss)
        return
    if best == "H":
        ss["tr_progressed"] = True
        cards.append(_tr_deal_card())
        total, _ = _hand_total_soft(cards)
        if total >= 21 or len(cards) >= 11:
            h["done"] = True
            _tr_next_hand(ss)
        return
    if best == "D":
        cards.append(_tr_deal_card())
        h["done"] = True
        _tr_next_hand(ss)
        return
    # S（スタンド）/ R（サレンダー）→ この手は完了
    h["done"] = True
    _tr_next_hand(ss)


def _tr_stats(ss):
    """成績メトリクスとリセットボタンを描画する。"""
    tot, cor = ss["tr_total"], ss["tr_correct"]
    acc = (cor / tot * 100) if tot else 0.0
    s1m, s2m, s3m = st.columns(3)
    s1m.metric("正答率", f"{acc:.0f}%")
    s2m.metric("連続正解", f"{ss['tr_streak']}")
    s3m.metric("最高連続", f"{ss['tr_best']}")
    st.caption(f"これまで {cor}/{tot} 問正解。"
               + ("いい調子です！" if acc >= 80 and tot >= 5 else
                  "間違えた手こそ伸びしろ。理由を読んで次へ。" if tot >= 1 else
                  "まずは1問やってみましょう。"))
    if tot >= 1 and st.button("成績をリセット", key="tr_reset"):
        for _k in ("tr_total", "tr_correct", "tr_streak", "tr_best"):
            ss[_k] = 0
        st.rerun()


def render_trainer(rules, tc):
    """最善手を当て、そのまま手を最後までプレイする練習モード。
    ヒットなら次の札が配られて継続、スプリットなら2つの手を順にプレイする。"""
    ss = st.session_state
    for _k, _v in (("tr_total", 0), ("tr_correct", 0),
                   ("tr_streak", 0), ("tr_best", 0)):
        ss.setdefault(_k, _v)
    if "tr_hands" not in ss:
        _tr_new_hand(ss)

    st.markdown("##### 🎓 トレーニング（最善手を当てて、そのまま最後までプレイ）")
    st.caption("配られた手の最善手をボタンで選ぶと、正解と理由が分かります。"
               "ヒットやスプリットのときは手がそのまま進み、決着まで練習できます。")

    du = ss["tr_du"]
    dup = _opt_rank(du)
    hands = ss["tr_hands"]
    active = ss["tr_active"]
    is_split = len(hands) > 1

    # 卓表示（ディーラー＋各ハンド。分割時はプレイ中/完了を表示）
    _lbl = ('font-size:0.72rem;color:#607D8B;font-weight:700;text-align:center;'
            'letter-spacing:1px;')
    _html = (f'<div style="margin:8px 0 2px;"><div style="{_lbl}">ディーラー</div>'
             f'{_hand_cards_html(du, suit_offset=3)}'
             f'<div style="border-top:1px dashed #B0BEC5;width:72%;margin:9px auto;">'
             f'</div>')
    for i, hh in enumerate(hands):
        if is_split:
            state = ("✓ 完了" if hh["done"]
                     else "▶ プレイ中" if i == active else "待機")
            tag = f'ハンド{i + 1}（{state}）'
        else:
            tag = "あなたの手札"
        _html += (f'<div style="{_lbl}">{tag}</div>'
                  f'{_hand_cards_html(*hh["cards"], suit_offset=i)}')
    _html += '</div>'
    st.markdown(_html, unsafe_allow_html=True)

    all_done = all(h["done"] for h in hands)
    if all_done:
        if ss.get("tr_progressed"):
            st.success("この手は決着です。おつかれさまでした。")
        if st.button("次の問題（新しい手）▶", type="primary", width='stretch',
                     key="tr_next_hand"):
            _tr_new_hand(ss)
            st.rerun()
        _tr_stats(ss)
        return

    h = hands[active]
    cards = h["cards"]
    if is_split:
        ctx = "split2" if len(cards) == 2 else "splithit"
    else:
        ctx = "initial" if len(cards) == 2 else "hit"
    best, evs, total, soft, is_pair, pair_rank, _ = _tr_eval(cards, du, rules, tc, ctx)

    label = f"ハンド{active + 1}" if is_split else "この手"
    answered = ss.get("tr_answered")
    if not answered:
        st.caption(f"↓ {label}、あなたならどうする？")
        acts = [a for a in ("H", "S", "D", "P", "R") if a in evs]
        cols = st.columns(len(acts))
        for i, act in enumerate(acts):
            if cols[i].button(f"{_ACTION_ICON.get(act, '')} {_ACTION_NAMES[act]}",
                              key=f"tr_btn_{act}", width='stretch'):
                ok = (act == best)
                ss["tr_total"] += 1
                if ok:
                    ss["tr_correct"] += 1
                    ss["tr_streak"] += 1
                    ss["tr_best"] = max(ss["tr_best"], ss["tr_streak"])
                else:
                    ss["tr_streak"] = 0
                ss["tr_answered"] = (act, ok)
                st.rerun()
    else:
        chosen, ok = answered
        if ok:
            st.success(f"⭕ 正解！　{_ACTION_NAMES[best]}（{best}）")
        else:
            st.error(f"❌ 残念。あなたは「{_ACTION_NAMES[chosen]}」、"
                     f"正解は「{_ACTION_NAMES[best]}（{best}）」です。")
        be = evs[best]
        ec = "#1B5E20" if be >= 0 else "#B71C1C"
        st.markdown(
            f'<div style="background:#F1F8E9;border-left:4px solid #7CB342;'
            f'border-radius:6px;padding:10px 14px;margin:2px 0 8px;font-size:0.9rem;'
            f'line-height:1.65;color:#33401F;">💡 '
            f'{_plain_reason(best, total, soft, pair_rank, dup, evs)}'
            f'<div style="margin-top:6px;font-size:0.85rem;color:#455A64;">'
            f'最善手の期待値（EV）＝ <strong style="color:{ec};">{be:+.3f}</strong>'
            f'（賭け金1単位あたり）</div></div>',
            unsafe_allow_html=True)
        # 次のアクションが続くか、この手が決着かで文言を変える
        if best in ("H", "P") or (best == "D"):
            nxt = "続ける ▶（次の札・手へ）"
        else:
            nxt = "続ける ▶"
        if st.button(nxt, type="primary", width='stretch', key="tr_continue"):
            _tr_advance(ss, best, rules)
            st.rerun()

    _tr_stats(ss)


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
         ("20", dlr[20]), ("21", dlr[21]), ("バースト", dlr["bust"])],
        columns=["ディーラー最終手", "確率"])
    dlr_df["確率"] = (dlr_df["確率"] * 100).map(lambda x: f"{x:.1f}%")
    with st.expander("ディーラー最終手の確率分布（参考）"):
        st.dataframe(dlr_df, width='stretch', hide_index=True)


# ===========================================================================
# カウンティング練習（Hi-Lo）— 基礎ドリルは無料、実戦ドリルはPRO
# ===========================================================================
_CT_RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]


def _hilo_tag(rank_str):
    """Hi-Loのタグ（2-6:+1 / 7-9:0 / 10,J,Q,K,A:-1）を返す。"""
    r = _opt_rank(rank_str)
    if 2 <= r <= 6:
        return 1
    if 7 <= r <= 9:
        return 0
    return -1


def _ct_stat_row(ok_key, total_key, extra=""):
    ok = st.session_state.get(ok_key, 0)
    total = st.session_state.get(total_key, 0)
    if total:
        acc = ok / total * 100
        st.caption(f"成績：{ok} / {total} 問正解（正答率 {acc:.0f}%）{extra}")


# ── ① タグ当てドリル（無料） ──────────────────────────────
def _ct_tag_new():
    st.session_state["ct_tag_card"] = random.choice(_CT_RANKS)


def _ct_tag_answer(ans):
    ss = st.session_state
    card = ss["ct_tag_card"]
    tag = _hilo_tag(card)
    ss["ct_tag_total"] = ss.get("ct_tag_total", 0) + 1
    if ans == tag:
        ss["ct_tag_ok"] = ss.get("ct_tag_ok", 0) + 1
        ss["ct_tag_streak"] = ss.get("ct_tag_streak", 0) + 1
    else:
        ss["ct_tag_streak"] = 0
    ss["ct_tag_last"] = (card, ans, tag)
    _ct_tag_new()


def _render_tag_drill():
    ss = st.session_state
    if "ct_tag_card" not in ss:
        _ct_tag_new()
    st.markdown("##### ① タグ当てドリル（基礎・無料）")
    st.caption("表示されたカードのHi-Loタグ（2〜6=+1／7〜9=0／10・絵札・A=−1）を"
               "即答する練習です。まずはここから。")
    st.markdown(_hand_cards_html(ss["ct_tag_card"]), unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.button("−1", key="ct_tag_m", width='stretch',
              on_click=_ct_tag_answer, args=(-1,))
    c2.button("0", key="ct_tag_z", width='stretch',
              on_click=_ct_tag_answer, args=(0,))
    c3.button("+1", key="ct_tag_p", width='stretch',
              on_click=_ct_tag_answer, args=(1,))
    last = ss.get("ct_tag_last")
    if last:
        card, ans, tag = last
        tag_s = f"{tag:+d}" if tag else "0"
        ans_s = f"{ans:+d}" if ans else "0"
        if ans == tag:
            st.success(f"⭕ 正解！ {card} のタグは {tag_s}"
                       f"（連続 {ss.get('ct_tag_streak', 0)} 問正解中）")
        else:
            st.error(f"❌ {card} のタグは {tag_s} でした（あなたの回答：{ans_s}）")
    _ct_stat_row("ct_tag_ok", "ct_tag_total")


# ── ② デッキ・カウントダウン（基礎=無料／速度・複数枚=PRO） ─────────
_CT_CD_HIDE = 3  # 最後に伏せる枚数。ここまでのRCを当てる


def _ct_cd_start(per):
    ss = st.session_state
    deck = _CT_RANKS * 4
    random.shuffle(deck)
    ss["ct_cd_deck"] = deck
    ss["ct_cd_pos"] = 0
    ss["ct_cd_per"] = per
    ss["ct_cd_stage"] = "run"
    ss["ct_cd_t0"] = _time.time()
    ss["ct_cd_current"] = []
    ss["ct_cd_done_after_show"] = False
    _ct_cd_next()


def _ct_cd_next():
    ss = st.session_state
    deck, pos, per = ss["ct_cd_deck"], ss["ct_cd_pos"], ss["ct_cd_per"]
    limit = len(deck) - _CT_CD_HIDE
    take = min(per, limit - pos)
    if take <= 0:
        ss["ct_cd_stage"] = "answer"
        ss["ct_cd_elapsed"] = _time.time() - ss["ct_cd_t0"]
        return
    ss["ct_cd_current"] = deck[pos:pos + take]
    ss["ct_cd_pos"] = pos + take
    if ss["ct_cd_pos"] >= limit:
        ss["ct_cd_done_after_show"] = True


def _ct_cd_reveal():
    ss = st.session_state
    ss["ct_cd_stage"] = "answer"
    ss["ct_cd_elapsed"] = _time.time() - ss["ct_cd_t0"]


def _ct_cd_reset():
    st.session_state["ct_cd_stage"] = "idle"


def _render_countdown_drill(pro):
    ss = st.session_state
    st.markdown("##### ② デッキ・カウントダウン" + ("（実戦・PRO）" if pro else "（基礎・無料）"))
    st.caption(f"1デッキ52枚のうち{52 - _CT_CD_HIDE}枚を順にめくり、頭の中でRC"
               f"（ランニングカウント）を足し続けます。最後の{_CT_CD_HIDE}枚は伏せたまま、"
               "あなたのRCを答えてください。")
    per = 1
    if pro:
        per = st.radio("1回にめくる枚数（多いほど実戦的：2枚は打ち消しペア認識の練習）",
                       [1, 2, 3], horizontal=True, key="ct_cd_per_sel")
    stage = ss.get("ct_cd_stage", "idle")
    if stage == "idle":
        st.button("🔀 シャッフルして開始", key="ct_cd_go", type="primary",
                  on_click=_ct_cd_start, args=(per,))
        extra = ""
        if pro and ss.get("ct_cd_best") is not None:
            extra = f"　⏱ 自己ベスト {ss['ct_cd_best']:.1f}秒"
        _ct_stat_row("ct_cd_ok", "ct_cd_total", extra)
        return
    if stage == "run":
        shown = ss["ct_cd_pos"]
        limit = 52 - _CT_CD_HIDE
        st.progress(shown / limit, text=f"{shown} / {limit} 枚")
        st.markdown(_hand_cards_html(*ss["ct_cd_current"]), unsafe_allow_html=True)
        if ss.get("ct_cd_done_after_show"):
            st.button("これで全部 → RCを答える", key="ct_cd_fin", type="primary",
                      width='stretch', on_click=_ct_cd_reveal)
        else:
            st.button("次のカード ▶", key="ct_cd_nx", type="primary",
                      width='stretch', on_click=_ct_cd_next)
        st.button("最初からやり直す", key="ct_cd_re", on_click=_ct_cd_reset)
        return
    # answer
    deck = ss["ct_cd_deck"]
    true_rc = sum(_hilo_tag(c) for c in deck[:52 - _CT_CD_HIDE])
    ans = st.number_input("あなたのRCは？", min_value=-20, max_value=20,
                          value=0, step=1, key="ct_cd_ans")
    if st.button("判定する", key="ct_cd_judge", type="primary"):
        ss["ct_cd_total"] = ss.get("ct_cd_total", 0) + 1
        elapsed = ss.get("ct_cd_elapsed", 0.0)
        if int(ans) == true_rc:
            ss["ct_cd_ok"] = ss.get("ct_cd_ok", 0) + 1
            msg = f"⭕ 正解！ RC = {true_rc:+d}"
            if pro:
                best = ss.get("ct_cd_best")
                if best is None or elapsed < best:
                    ss["ct_cd_best"] = elapsed
                    msg += f"　⏱ {elapsed:.1f}秒（自己ベスト更新！）"
                else:
                    msg += f"　⏱ {elapsed:.1f}秒（自己ベスト {best:.1f}秒）"
            st.success(msg)
            st.balloons()
        else:
            st.error(f"❌ 正しいRCは {true_rc:+d} でした（あなたの回答：{int(ans):+d}）")
            if pro:
                st.caption(f"⏱ 所要 {ss.get('ct_cd_elapsed', 0.0):.1f}秒")
        ss["ct_cd_stage"] = "idle"
        _ct_stat_row("ct_cd_ok", "ct_cd_total")


# ── ③ TC換算ドリル（PRO） ────────────────────────────────
def _ct_tc_new():
    ss = st.session_state
    while True:
        rc = random.randint(-12, 12)
        decks = random.choice([1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0])
        if rc == 0:
            continue
        v = rc / decks
        # ちょうど .5 になる曖昧な問題（四捨五入の流儀差が出る）は避ける
        if abs(abs(v) - int(abs(v)) - 0.5) < 1e-9:
            continue
        ss["ct_tc_rc"], ss["ct_tc_decks"] = rc, decks
        return


def _render_tc_drill():
    ss = st.session_state
    if "ct_tc_rc" not in ss:
        _ct_tc_new()
    st.markdown("##### ③ TC換算ドリル（実戦・PRO）")
    st.caption("RC（ランニングカウント）を残りデッキ数で割ってTC（トゥルーカウント）に"
               "変換する暗算練習。ベット判断の心臓部です。答えは四捨五入した整数で。")
    rc, decks = ss["ct_tc_rc"], ss["ct_tc_decks"]
    st.markdown(f"**RC = {rc:+d}　／　残り約 {decks:g} デッキ** → TCは？")
    ans = st.number_input("TC（整数）", min_value=-15, max_value=15, value=0,
                          step=1, key="ct_tc_ans")
    c1, c2 = st.columns(2)
    if c1.button("判定する", key="ct_tc_judge", type="primary", width='stretch'):
        true_tc = round(rc / decks)
        ss["ct_tc_total"] = ss.get("ct_tc_total", 0) + 1
        if int(ans) == true_tc:
            ss["ct_tc_ok"] = ss.get("ct_tc_ok", 0) + 1
            st.success(f"⭕ 正解！ {rc:+d} ÷ {decks:g} ≒ TC {true_tc:+d}")
        else:
            st.error(f"❌ {rc:+d} ÷ {decks:g} = {rc / decks:+.2f} → "
                     f"TC {true_tc:+d} でした")
        _ct_tc_new()
    c2.button("次の問題", key="ct_tc_skip", width='stretch', on_click=_ct_tc_new)
    _ct_stat_row("ct_tc_ok", "ct_tc_total")
    st.caption("※ 実戦ではベット目的なら0方向へ切り捨てる保守的な流儀もあります。"
               "本ドリルは四捨五入で統一しています。")


# ── ④ インデックス・クイズ（PRO） ─────────────────────────
def _ct_ix_new(filtered):
    st.session_state["ct_ix_q"] = random.choice(filtered)


def _render_index_quiz(rules):
    ss = st.session_state
    st.markdown("##### ④ インデックス・クイズ（実戦・PRO）")
    st.caption("現在のハウスルールで実際に使えるインデックスプレイの「発動TC」を"
               "当てるクイズ。Illustrious 18 / Fab 4 を体で覚えます。")
    filtered = get_filtered_indexes(rules)
    if not filtered:
        st.info("現在のハウスルールでは発動するインデックスプレイがありません。")
        return
    if "ct_ix_q" not in ss or ss.get("ct_ix_rules") != rules.short_description():
        _ct_ix_new(filtered)
        ss["ct_ix_rules"] = rules.short_description()
    h, d, thr, a, direction = ss["ct_ix_q"]
    d_label = _up_label(d) if isinstance(d, int) else d
    op = "以上" if direction == "+" else "以下"
    st.markdown(f"**{h} vs ディーラー {d_label}** → **{a}** に変えるのは "
                f"**TCがいくつ{op}**のとき？")
    ans = st.number_input("発動TC（整数）", min_value=-10, max_value=10, value=0,
                          step=1, key="ct_ix_ans")
    c1, c2 = st.columns(2)
    if c1.button("判定する", key="ct_ix_judge", type="primary", width='stretch'):
        ss["ct_ix_total"] = ss.get("ct_ix_total", 0) + 1
        if int(ans) == thr:
            ss["ct_ix_ok"] = ss.get("ct_ix_ok", 0) + 1
            st.success(f"⭕ 正解！ {h} vs {d_label} は TC {thr:+d} {op}で {a}")
        else:
            st.error(f"❌ 正しくは TC {thr:+d} {op}で {a} でした")
        _ct_ix_new(filtered)
    c2.button("次の問題", key="ct_ix_skip", width='stretch',
              on_click=_ct_ix_new, args=(filtered,))
    _ct_stat_row("ct_ix_ok", "ct_ix_total")


def render_counting_trainer(rules):
    st.markdown("##### 🔢 カウンティング練習（Hi-Lo）")
    st.caption("カウンティングは合法な記憶・観察技術ですが、カジノ側が嫌えば"
               "バックオフ（プレイ拒否）される代償もあります。また**CSM卓（毎ハンド"
               "シャッフル）では効果がありません**。仕組みは「用語集」タブへ。")
    _render_tag_drill()
    st.markdown("---")
    # PROなら同じカウントダウンが速度計測・複数枚対応にアップグレードされる
    _render_countdown_drill(pro=IS_PRO)
    st.markdown("---")
    if not IS_PRO:
        _pro_locked_notice("カウンティング実戦ドリル")
        st.markdown(
            "PRO版の実戦ドリルでは、さらに次の練習ができます：\n\n"
            "- ⏱ **スピード計測カウントダウン**（所要秒数と自己ベストを記録）\n"
            "- 🃏 **複数枚めくり**（2〜3枚同時。打ち消しペアを一瞬で認識する実戦技術）\n"
            "- ➗ **TC換算ドリル**（RC→TCの暗算。ベット判断の心臓部）\n"
            "- 🎯 **インデックス・クイズ**（あなたの卓のルールで実際に使える例外プレイを暗記）")
        return
    _render_tc_drill()
    st.markdown("---")
    _render_index_quiz(rules)


# 表示順：無料の2タブ（戦略・ガイド）を先頭に、PRO3タブ（🔒）を後方にまとめる。
# 変数名（tab1..tab5）は各コンテンツblockと対応づけたまま、ラベル順のみ並べ替える。
tab1, tab5, tab2, tab3, tab4 = st.tabs([
    "📊 ベーシックストラテジー",
    "📚 ルール＆用語集（はじめての方へ）",
    "🔒 インデックスプレイ",
    "🔒 シミュレーター",
    "🔒 PDF 出力"])

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

    _sub_q, _sub_tr, _sub_ct, _sub_t, _sub_b = st.tabs(
        ["⚡ クイック判定", "🎓 トレーニング", "🔢 カウンティング練習",
         "📊 早見表（全パターン）", "🎯 勝敗内訳"])
    with _sub_q:
        render_quick_decision(rules, tab1_tc)
        _render_line_cta()
    with _sub_tr:
        render_trainer(rules, tab1_tc)
    with _sub_ct:
        render_counting_trainer(rules)
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
    st.caption("※ TC（トゥルーカウント）＝カードの偏りを表す指標。"
               "数字が高いほどプレイヤーに有利です（詳しくは「用語集」タブ）。"
               "インデックスプレイ＝カウント状況に応じて基本戦略から打ち方を変える例外パターンです。")
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
        st.markdown(f"**TC {tc2:+d} で基本戦略（BS）から打ち方を変えるプレイ**")
        if active:
            df = pd.DataFrame(
                [(h, _up_label(d) if isinstance(d, int) else d, _thr_label(thr, direction), a)
                 for (h, d, thr, a, direction) in active],
                columns=["ハンド", "ディーラー", "発動条件", "アクション"])
            st.dataframe(df, width='stretch', hide_index=True)
        else:
            st.write("いまは基本戦略から変えるプレイはありません（BS通りでOK）。")

        st.markdown("---")
        st.markdown("**インデックスプレイ全一覧（現在のハウスルールで実際に基本戦略から変わるものだけを動的に算出）**")
        filtered_idx = get_filtered_indexes(rules)
        all_idx = pd.DataFrame(
            [(h, _up_label(d) if isinstance(d, int) else d, _thr_label(thr, direction), a)
             for (h, d, thr, a, direction) in filtered_idx],
            columns=["ハンド", "ディーラー", "発動条件", "アクション"])
        st.dataframe(all_idx, width='stretch', hide_index=True)
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
        m7c.metric("破産確率", f"{res.ruin_probability * 100:.1f}%",
                   help="資金（バンクロール）をすべて失う確率。低いほど安全です。")
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
            st.plotly_chart(fig, width='stretch')
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
A + 6 + 8  →  1 + 6 + 8 = 15（バーストを避けてAを1点に切り替え）
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
9 + 7 = 16  → ハード16（バーストリスクあり）
A + 6 + K = 1 + 6 + 10 = 17  → ハード17（Aを11にしたら27でバーストするため）
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

- ヒットするとバーストしやすい（プレイヤーもディーラーも10が来る確率が高い）
- 「16 vs 10」などで **スタンドに切り替える**（Illustrious 18）
- ただし、サレンダーがあれば **R（EV=−0.50）が常に優先**（スタンドEV≈−0.54 より良い）
- 「9 vs 2」（TC≥+1）、「11 vs A」（TC≥+1、HC限定）などでダブルが有利になる

---

**TC が低い（−） = デッキに小さいカード（2〜6）が多く残っている**

- ヒットしてもバーストしにくい → 積極的にヒット
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
使ったカードをその場で機械に戻し続ける自動シャッフル機。

- **シュー（配り箱）は使いません**。切り札を積んでおく通常のシューゲームとは機材そのものが異なります
- カウンティングが **実質不能**（捨て札が貯まらず、カードが常にランダム）
- アミューズカジノには費用面から未導入の店舗も多い
- CSMテーブルでは純粋なBS（ハウスエッジ0.4〜0.5%）のみ有効
""")


# ===========================================================================
# フッター：免責・利用目的・年齢・依存症配慮の常設表示（全ページ共通）
# ===========================================================================
_render_policy_notice(compact=False)
