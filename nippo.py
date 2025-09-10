import streamlit as st
import pandas as pd
import os
from datetime import date

# =============================
# 基本設定
# =============================
BASE_DIR = "data"
CRED_PATH = os.path.join(BASE_DIR, "credentials.csv")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
GLOBAL_PATH = os.path.join(BASE_DIR, "global_announcements.csv")

# 初期フォルダ作成
os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

# サンプルのcredentials.csvを自動生成（存在しない場合のみ）
if not os.path.exists(CRED_PATH):
    df = pd.DataFrame(
        [
            {"user_id": "taro", "password": "pass123", "display_name": "山田 太郎"},
            {"user_id": "hanako", "password": "pass456", "display_name": "佐藤 花子"},
        ]
    )
    df.to_csv(CRED_PATH, index=False)

# グローバル申し送りCSV 初期化（存在しない場合のみ）
if not os.path.exists(GLOBAL_PATH):
    pd.DataFrame(columns=["date", "user_id", "display_name", "announcement", "done"]).to_csv(GLOBAL_PATH, index=False)

# =============================
# ユーティリティ
# =============================

def load_credentials() -> pd.DataFrame:
    try:
        return pd.read_csv(CRED_PATH, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=["user_id", "password", "display_name"])  # 空


def auth(user_id: str, password: str):
    creds = load_credentials()
    row = creds[(creds["user_id"] == user_id) & (creds["password"] == password)]
    if not row.empty:
        rec = row.iloc[0]
        return {"user_id": rec["user_id"], "display_name": rec.get("display_name", rec["user_id"]) }
    return None


def user_report_path(user_id: str) -> str:
    user_dir = os.path.join(REPORTS_DIR, user_id)
    os.makedirs(user_dir, exist_ok=True)
    return os.path.join(user_dir, "reports.csv")


def _ensure_user_report_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["date", "work", "announcement", "notes", "next_plan"]:
        if col not in df.columns:
            df[col] = ""
    return df


def load_user_reports(user_id: str) -> pd.DataFrame:
    path = user_report_path(user_id)
    if os.path.exists(path):
        try:
            df = pd.read_csv(path)
            df = _ensure_user_report_columns(df)
            if "date" in df.columns:
                try:
                    df["date_dt"] = pd.to_datetime(df["date"], errors="coerce")
                except Exception:
                    df["date_dt"] = pd.NaT
            return df
        except Exception:
            pass
    return pd.DataFrame(columns=["date", "work", "announcement", "notes", "next_plan", "date_dt"])  # 空


def save_user_report(user_id: str, date_str: str, work: str, announcement: str, notes: str, next_plan: str):
    path = user_report_path(user_id)
    df = load_user_reports(user_id)
    df = _ensure_user_report_columns(df)

    # 日付キーを正規化（例: 2025/08/01 -> 2025-08-01、空白除去）
    if not df.empty:
        df["date"] = (
            df["date"].astype(str).str.strip().str.replace("/", "-", regex=False).str.slice(0, 10)
        )
    date_key = str(date_str)[:10]

    # 1日1件: 既存の同日レコードを除去
    existed = False
    if not df.empty and "date" in df.columns:
        mask = df["date"] == date_key
        existed = bool(mask.any())
        df = df.loc[~mask].copy()

    new_row = {
        "date": date_key,
        "work": work,
        "announcement": announcement,
        "notes": notes,
        "next_plan": next_plan,
    }

    # 保存用に補助列は落とす
    df = df.drop(columns=["date_dt"], errors="ignore")
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    # 念のため重複日付が残っていても最後のものを採用
    df = df.sort_index().drop_duplicates(subset=["date"], keep="last")

    df.to_csv(path, index=False)
    return "updated" if existed else "created"


def append_global_announcement(user_id: str, display_name: str, date_str: str, announcement: str):
    if not announcement.strip():
        return
    try:
        df = pd.read_csv(GLOBAL_PATH)
    except Exception:
        df = pd.DataFrame(columns=["date", "user_id", "display_name", "announcement", "done"])  # 空

    # 互換: done 列が無い既存CSVの場合は追加
    if "done" not in df.columns:
        df["done"] = False

    new_row = {
        "date": str(date_str)[:10],
        "user_id": user_id,
        "display_name": display_name,
        "announcement": announcement,
        "done": False,
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(GLOBAL_PATH, index=False)


def load_global_announcements() -> pd.DataFrame:
    try:
        df = pd.read_csv(GLOBAL_PATH)
        # 互換: done 列が無い場合は False で追加
        if "done" not in df.columns:
            df["done"] = False
        else:
            df["done"] = df["done"].fillna(False).astype(bool)
        if "date" in df.columns:
            try:
                df["date_dt"] = pd.to_datetime(df["date"], errors="coerce")
            except Exception:
                df["date_dt"] = pd.NaT
        return df
    except Exception:
        return pd.DataFrame(columns=["date", "user_id", "display_name", "announcement", "done", "date_dt"])  # 空


# =============================
# 画面レイアウト
# =============================
st.set_page_config(page_title="業務日報", page_icon="📝", layout="wide")

st.title("業務日報 / 全体申し送り")
if "auth" not in st.session_state:
    st.session_state.auth = None

with st.sidebar:
    st.header("全体への申し送り事項（最新順）")
    st.write("※要件が終了したら、『不要』チェックを入れてください。")
    gdf = load_global_announcements()
    if not gdf.empty:
        # done=False を上、done=True を下へ。各グループ内は新しい日付が上
        try:
            gdf_sorted = gdf.sort_values(by=["done", "date_dt"], ascending=[True, False], na_position="last")
        except Exception:
            gdf_sorted = gdf

        display_cols = [c for c in ["date", "display_name", "announcement", "done"] if c in gdf_sorted.columns]

        edited = st.data_editor(
            gdf_sorted[display_cols],
            use_container_width=True,
            hide_index=True,
            column_config={"done": "不要"},
        )

        # チェック状態が変わったら保存（インデックス差異を無視して比較）
        if "done" in gdf.columns:
            try:
                original_done = gdf_sorted["done"].to_numpy()
                edited_done = edited["done"].to_numpy()
                if original_done.shape == edited_done.shape and (original_done != edited_done).any():
                    # 並び替え前の行順に対応させて反映
                    gdf.loc[gdf_sorted.index, "done"] = edited_done
                    gdf.to_csv(GLOBAL_PATH, index=False)
                    st.toast("全体申し送りの『不要』状態を更新しました。")
                    st.rerun()
            except Exception:
                pass
    else:
        st.info("まだ全体申し送りはありません。")

if st.session_state.auth is None:
    st.subheader("ログイン")
    with st.form("login_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            user_id = st.text_input("ユーザーID", value="", key="login_user_id")
        with col2:
            password = st.text_input("パスワード", value="", type="password", key="login_password")
        submitted = st.form_submit_button("ログイン")
    if submitted:
        user = auth(user_id.strip(), password)
        if user:
            st.session_state.auth = user
            st.success(f"{user['display_name']} としてログインしました。")
            st.rerun()
        else:
            st.error("ユーザーID または パスワードが正しくありません。")
else:
    user = st.session_state.auth
    st.subheader(f"ようこそ、{user['display_name']} さん")
    if st.button("ログアウト"):
        st.session_state.auth = None
        for k in ["login_user_id", "login_password"]:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()

    st.markdown("---")

    recent_df = load_user_reports(user["user_id"])
    if not recent_df.empty:
        try:
            recent_sorted = recent_df.sort_values(by=["date_dt"], ascending=False)
        except Exception:
            recent_sorted = recent_df
        next_plan_text = str(recent_sorted.iloc[0].get("next_plan", "")).strip()
        if next_plan_text:
            st.info(f"予定: {next_plan_text}")
        else:
            st.info("直近の『次出勤日の予定』は未入力です。")
    else:
        st.info("まだ日報がありません。『日報の登録』から入力してください。")

    st.markdown("### 日報の登録")
    st.markdown("複数回記入した場合、その日最後に書いたものが残ります。")
    with st.form("report_form", clear_on_submit=True):
        d = st.date_input("日付", value=date.today())
        work = st.text_area("今日の業務内容", height=160, placeholder="本日の作業内容(詳細に書く必要はありませんが、 \n何名、何件など、できるだけ数字を入れて記載してください。)")
        announcement = st.text_area("全体への申し送り事項", height=120, placeholder="全員に共有したい内容があれば記入…（空欄可）")
        notes = st.text_area("備考（空欄可）", height=100, placeholder="補足やメモなど…")
        next_plan = st.text_area("次出勤日の予定", height=120, placeholder="次回出勤日に行う予定。次回日報を開いた際に表示します。")
        submitted = st.form_submit_button("保存")

    if submitted:
        date_str = d.strftime("%Y-%m-%d")
        result = save_user_report(user["user_id"], date_str, work.strip(), announcement.strip(), notes.strip(), next_plan.strip())
        append_global_announcement(user["user_id"], user["display_name"], date_str, announcement.strip())
        if result == "updated":
            st.success("当日分の記録を上書き保存しました。")
        else:
            st.success("保存しました。")
        st.rerun()

    st.markdown("## 履歴")
    df = load_user_reports(user["user_id"])
    if not df.empty:
        try:
            df_sorted = df.sort_values(by=["date_dt"], ascending=False)
        except Exception:
            df_sorted = df
        show_cols = ["date", "work", "announcement", "notes", "next_plan"]
        show_cols = [c for c in show_cols if c in df_sorted.columns]
        st.dataframe(df_sorted[show_cols], use_container_width=True, hide_index=True)
    else:
        st.info("まだ日報はありません。フォームから登録してください。")

st.caption(
    "日報の内容については、今後の業務分担、配置等の決定に活用します。　\n"
    "要望等あれば古川まで。可能な範囲で対応します。"
)