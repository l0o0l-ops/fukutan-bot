import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from google import genai
from google.genai import types
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from dotenv import load_dotenv
from pypdf import PdfReader
import json
import io
import uuid

load_dotenv()

# ==========================================
# 1. 環境設定と初期化
# ==========================================
FIREBASE_KEY_PATH = os.environ.get("FIREBASE_KEY_PATH")
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "asia-northeast1")

@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        if FIREBASE_KEY_PATH and os.path.exists(FIREBASE_KEY_PATH):
            cred = credentials.Certificate(FIREBASE_KEY_PATH)
            firebase_admin.initialize_app(cred)
        else:
            firebase_admin.initialize_app()
    return firestore.client()

db = init_firebase()  # ← Firebase接続はキャッシュしてOK（変化しないため）

@st.cache_resource
def init_ai_client():
    if not PROJECT_ID:
        st.error("環境変数 GOOGLE_CLOUD_PROJECT が設定されていません。")
        st.stop()
    return genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

ai_client = init_ai_client()  # ← AIクライアントもキャッシュしてOK

def call_gemini(**kwargs):
    try:
        return ai_client.models.generate_content(**kwargs)
    except Exception as e:
        st.error(f"AIとの通信でエラーが発生しました。（詳細: {e}）")
        return None

# ==========================================
# 2. クラス管理（Classroom型：複数クラス対応）
# ==========================================
def ensure_default_class_exists():
    """初回起動時のみ、デモ用のデフォルトクラスをFirestoreに作成する。
    ⚠️ ここは st.cache_resource を使わない。キャッシュするとFirestoreの更新が
    画面に反映されなくなる（今回起きたバグの原因）。"""
    class_ref = db.collection("classes").document("class_A123")
    if not class_ref.get().exists:
        class_ref.set({
            "class_name": "DevOps基礎講座2026",
            "teacher_id": "teacher_999",
            "roster": [],  # [{"student_id": "...", "display_name": "..."}]
            "modules": [
                {
                    "module_id": "mod_01",
                    "title": "第1章：Dockerによるコンテナ化",
                    "target_goal": "コンテナと仮想マシンの最大の違いと、それによるメリット・デメリットを論理的に説明できること",
                    "pdf_text": "【講義ノート：コンテナと仮想マシンの違い】従来の仮想マシン（VM）は、ホストOSの上にハイパーバイザを配置し、その上で独立した『ゲストOS』を動かすため、起動が遅くリソースを多く消費します。一方、Dockerなどの『コンテナ』は、ホストOSのカーネルを共有し、プロセスとして独立した実行環境を作ります。",
                    "passing_criteria": {"knowledge_level": 4, "thinking_level": 4, "application_level": 3}
                }
            ]
        })

def list_all_classes():
    """全クラスを取得する。ここは毎回Firestoreから読む（キャッシュしない）"""
    docs = db.collection("classes").stream()
    return {doc.id: doc.to_dict() for doc in docs}

def create_new_class(class_name: str) -> str:
    new_id = f"class_{uuid.uuid4().hex[:8]}"
    db.collection("classes").document(new_id).set({
        "class_name": class_name,
        "teacher_id": "teacher_999",
        "roster": [],
        "modules": []
    })
    return new_id

ensure_default_class_exists()
all_classes = list_all_classes()  # 毎回フレッシュに取得

# ==========================================
# 3. サイドバー：クラス選択（Classroom型のトップ画面）
# ==========================================
st.sidebar.markdown("""
<div style="background-color: #f1f5f9; padding: 12px; border-radius: 12px; margin-bottom: 15px;">
    <h4 style="margin: 0; color: #334155; font-size: 0.9rem;">🏫 クラス選択</h4>
</div>
""", unsafe_allow_html=True)

class_display_options = {cid: cdata.get("class_name", cid) for cid, cdata in all_classes.items()}
selected_class_id = st.sidebar.selectbox(
    "授業を選択",
    options=list(class_display_options.keys()),
    format_func=lambda cid: class_display_options[cid],
    key="class_selector"
)

with st.sidebar.expander("＋ 新しい授業を作成"):
    new_class_name = st.text_input("授業名", key="new_class_name_input")
    if st.button("作成する", key="create_class_btn"):
        if new_class_name.strip():
            new_id = create_new_class(new_class_name.strip())
            st.success(f"「{new_class_name}」を作成しました")
            st.rerun()
        else:
            st.warning("授業名を入力してください")

class_id = selected_class_id
class_data = all_classes[class_id]
modules = class_data.get("modules", [])
roster = class_data.get("roster", [])

def get_fresh_class_data(cid):
    """モジュール変更後などに最新状態を取り直すためのヘルパー"""
    return db.collection("classes").document(cid).get().to_dict()

# ==========================================
# 4. エージェント用自律ツール (Function Calling)
# ==========================================
def update_student_status(knowledge: int, thinking: int, application: int) -> str:
    """学生の理解度レベルをリアルタイムに更新してFirestoreに保存します。

    Args:
        knowledge: 知識レベル (1〜5の整数)
        thinking: 思考レベル (1〜5の整数)
        application: 応用レベル (1〜5の整数)
    """
    c_id = st.session_state.get("active_class_id")
    s_id = st.session_state.get("active_student_id")
    m_id = st.session_state.get("active_module_id")

    doc_id = f"{c_id}_{s_id}"
    db.collection("enrollments").document(doc_id).update({
        f"modules.{m_id}.current_status.knowledge_level": knowledge,
        f"modules.{m_id}.current_status.thinking_level": thinking,
        f"modules.{m_id}.current_status.application_level": application
    })
    return f"生徒 {s_id} の {m_id} における能力レベルを更新しました: 知識={knowledge}, 思考={thinking}, 応用={application}"

def generate_growth_report_and_carte(c_id: str, s_id: str, m_id: str, chat_history: list):
    formatted_chat = "\n".join([f"{m['role']}: {m['content']}" for m in chat_history if m["role"] in ["user", "assistant"]])
    prompt = f"""
    あなたは大学教授を裏から支える極めて優秀なAI副担任です。
    担当する学生が講義モジュールを合格クリアしました。これまでの対話履歴を精密に分析し、
    「引き継ぎ用の成長日報（150文字程度）」と「次のステップへの学習処方箋（100文字程度）」を作成してください。

    【学生との対話履歴】
    {formatted_chat}

    【出力形式】
    【成長日報】: (分析結果を記述)
    【学習処方箋】: (アドバイスを記述)
    """
    response = call_gemini(model='gemini-2.5-flash', contents=prompt)
    growth_report = "合格！よく頑張りました。"
    action_plan = "次の章へ進んでください。"

    if response and response.text and "【成長日報】" in response.text and "【学習処方箋】" in response.text:
        parts = response.text.split("【学習処方箋】")
        growth_report = parts[0].replace("【成長日報】:", "").replace("【成長日報】", "").strip()
        action_plan = parts[1].strip()

    doc_id = f"{c_id}_{s_id}"
    db.collection("enrollments").document(doc_id).update({
        f"modules.{m_id}.is_passed": True,
        f"modules.{m_id}.growth_report": growth_report,
        f"modules.{m_id}.action_plan": action_plan,
        "overall_report": f"【全体要約カルテ】: 直近で {m_id} を見事突破。\n要約: {growth_report}",
        "overall_action_plan": action_plan
    })

# ==========================================
# 5. PDFからモジュール自動生成
# ==========================================
def extract_pdf_text(uploaded_file) -> str:
    reader = PdfReader(io.BytesIO(uploaded_file.read()))
    text = ""
    for page in reader.pages:
        text += (page.extract_text() or "") + "\n"
    return text.strip()

def generate_module_from_pdf(pdf_text: str, module_number: int):
    prompt = f"""
    あなたは大学の教育設計を支援するAIです。
    以下の講義スライドのテキストを分析し、この章の学習モジュールを設計してください。

    【講義スライドの内容】
    {pdf_text[:8000]}

    以下のJSON形式で、他の文章を含めず出力してください：
    {{
      "title": "第{module_number}章：（内容に基づいた章タイトル）",
      "target_goal": "生徒がこの章を通して説明できるべきことを1文で",
      "passing_criteria": {{
        "knowledge_level": (1-5の整数),
        "thinking_level": (1-5の整数),
        "application_level": (1-5の整数)
      }}
    }}
    """
    response = call_gemini(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.3)
    )
    if not response or not response.text:
        return None
    try:
        parsed = json.loads(response.text)
        parsed["module_id"] = f"mod_{module_number:02d}"
        parsed["pdf_text"] = pdf_text[:8000]
        return parsed
    except json.JSONDecodeError:
        st.error("AIが有効なJSON形式で応答しませんでした。")
        return None

# ==========================================
# 6. グラフ描画
# ==========================================
def draw_radar_chart(current, target):
    labels = ['Knowledge', 'Thinking', 'Application']
    num_vars = len(labels)
    angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
    angles += angles[:1]
    current_closed = current + current[:1]
    target_closed = target + target[:1]

    fig, ax = plt.subplots(figsize=(2.8, 2.8), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor('#ffffff')
    ax.set_facecolor('#f8fafc')
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    plt.xticks(angles[:-1], labels, color='#475569', size=8, weight='bold')
    ax.set_rlabel_position(0)
    plt.yticks([1, 2, 3, 4, 5], ["1", "2", "3", "4", "5"], color="#cbd5e1", size=7)
    plt.ylim(0, 5)
    ax.plot(angles, current_closed, color='#3b82f6', linewidth=2, linestyle='solid', label='Current')
    ax.fill(angles, current_closed, color='#3b82f6', alpha=0.15)
    ax.plot(angles, target_closed, color='#ef4444', linewidth=1.2, linestyle='dashed', label='Target')
    ax.legend(loc='upper right', bbox_to_anchor=(1.25, 1.15), fontsize=7, frameon=False)
    plt.tight_layout()
    return fig

# ==========================================
# 7. UIスタイル
# ==========================================
css_path = os.path.join(os.path.dirname(__file__), "style.css")
if os.path.exists(css_path):
    with open(css_path, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

st.set_page_config(page_title="インテリジェント・シラバス", layout="wide")
st.title(f"📘 {class_data.get('class_name', class_id)}")

# ==========================================
# 8. 生徒選択（このクラスのrosterから）
# ==========================================
st.sidebar.markdown("---")
st.sidebar.markdown("<h4 style='font-size: 0.9rem; color: #334155;'>👤 生徒切り替え（デモ用）</h4>", unsafe_allow_html=True)

if not roster:
    st.sidebar.info("このクラスにはまだ生徒がいません。教授タブから追加してください。")
    student_id = None
else:
    roster_options = {s["student_id"]: s["display_name"] for s in roster}
    student_id = st.sidebar.selectbox(
        "ログイン生徒",
        options=list(roster_options.keys()),
        format_func=lambda sid: roster_options[sid],
        key="student_selector"
    )

if student_id:
    st.session_state["active_class_id"] = class_id
    st.session_state["active_student_id"] = student_id

    enrollment_ref = db.collection("enrollments").document(f"{class_id}_{student_id}")
    enrollment_doc = enrollment_ref.get()

    if not enrollment_doc.exists:
        init_modules = {}
        for m in modules:
            init_modules[m["module_id"]] = {
                "current_status": {"knowledge_level": 1, "thinking_level": 1, "application_level": 1},
                "is_passed": False,
                "growth_report": "まだ合格していません。",
                "action_plan": "基本概念を自分の言葉で説明できるように学習を進めましょう。",
                "chat_history": []
            }
        enrollment_ref.set({
            "class_id": class_id,
            "student_id": student_id,
            "overall_report": "全体カルテはまだ作成されていません。",
            "overall_action_plan": "最初のモジュールを開始してください。",
            "modules": init_modules
        })
        enrollment_doc = enrollment_ref.get()

    enrollment_data = enrollment_doc.to_dict()

    if st.sidebar.button("この生徒のデータを初期化"):
        enrollment_ref.delete()
        st.rerun()

tab_student, tab_professor = st.tabs(["👤 学生用学習コクピット", "👨‍🏫 教授用管理ダッシュボード"])

# ==============================================================================
# 👤 学生用画面
# ==============================================================================
with tab_student:
    if not student_id:
        st.warning("このクラスにはまだ生徒がいません。教授タブから生徒を追加してください。")
    elif not modules:
        st.warning("このクラスにはまだ章がありません。教授タブからPDFをアップロードして章を作成してください。")
    else:
        col_left, col_center, col_right = st.columns([3, 5, 4])

        with col_left:
            st.markdown("<h3 style='font-size: 1.15rem; font-weight: bold; color: #1e293b;'>📚 講義章リスト</h3>", unsafe_allow_html=True)
            mod_titles = [f"{m['module_id']}: {m['title']}" for m in modules]
            selected_title = st.radio("進行する授業を選択してください", mod_titles, label_visibility="collapsed")
            active_m_id = selected_title.split(":")[0]
            st.session_state["active_module_id"] = active_m_id

            active_idx = next(i for i, m in enumerate(modules) if m["module_id"] == active_m_id)
            current_module_info = modules[active_idx]
            mod_progress = enrollment_data.get("modules", {}).get(active_m_id, {})
            is_passed = mod_progress.get("is_passed", False)

            st.markdown("---")
            if is_passed:
                st.markdown("<div style='background-color:#ecfdf5;border:1px solid #a7f3d0;padding:15px;border-radius:12px;'><span class='badge-passed'>🟢 合格済み</span></div>", unsafe_allow_html=True)
            else:
                st.markdown("<div style='background-color:#fffbeb;border:1px solid #fde68a;padding:15px;border-radius:12px;'><span class='badge-progress'>🟡 対話面接中</span></div>", unsafe_allow_html=True)

        with col_center:
            st.markdown("<h3 style='font-size: 1.15rem; font-weight: bold; color: #1e293b;'>💬 対話による口頭試問</h3>", unsafe_allow_html=True)
            st.markdown(f"<p style='font-size: 0.8rem; color: #64748b;'>目標: {current_module_info.get('target_goal')}</p>", unsafe_allow_html=True)

            db_chat = mod_progress.get("chat_history", [])
            if not db_chat:
                db_chat = [{"role": "assistant", "content": f"こんにちは！今日の講義は「{current_module_info.get('title')}」だよ。自分の言葉で核心を説明してもらえるかな？"}]
                enrollment_ref.update({f"modules.{active_m_id}.chat_history": db_chat})

            chat_container = st.container(height=360)
            with chat_container:
                for msg in db_chat:
                    cls = "chat-bubble-user" if msg["role"] == "user" else "chat-bubble-assistant"
                    st.markdown(f"<div class='{cls}'>{msg['content']}</div>", unsafe_allow_html=True)

            user_input = st.chat_input("ここに自分の言葉で記述...", disabled=is_passed, key="student_main_input")

            if user_input:
                db_chat.append({"role": "user", "content": user_input})
                enrollment_ref.update({f"modules.{active_m_id}.chat_history": db_chat})

                system_instruction = f"""
                あなたは大学のAI副担任です。絶対に答えを教えてはいけません。
                スライドの内容をヒントとして部分的に提示し、学生に考えさせ、自分の言葉で説明させる「ソクラテス式」の問いかけを徹底してください。
                学生が十分に本質を理解したと判断したら、必ず update_student_status を呼び出してください。

                【講義スライドの内容】
                {current_module_info.get('pdf_text')}
                """

                with st.spinner("AI副担任が評価＆思考中..."):
                    response = call_gemini(
                        model='gemini-2.5-flash',
                        contents=user_input,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            tools=[update_student_status],
                            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                            temperature=0.7,
                        )
                    )
                    ai_reply = "理解度を測定し、レベルに反映しました。"

                    if response and response.function_calls:
                        for function_call in response.function_calls:
                            if function_call.name == "update_student_status":
                                args = function_call.args
                                k, t, a = int(args.get("knowledge", 1)), int(args.get("thinking", 1)), int(args.get("application", 1))
                                result_msg = update_student_status(k, t, a)

                                criteria = current_module_info.get("passing_criteria", {"knowledge_level": 4, "thinking_level": 4, "application_level": 3})
                                if k >= criteria["knowledge_level"] and t >= criteria["thinking_level"] and a >= criteria["application_level"]:
                                    generate_growth_report_and_carte(class_id, student_id, active_m_id, db_chat)
                                    st.balloons()

                                followup = call_gemini(
                                    model='gemini-2.5-flash',
                                    contents=[
                                        types.Content(role="user", parts=[types.Part.from_text(text=user_input)]),
                                        types.Content(role="model", parts=[types.Part.from_function_call(function_call=function_call)]),
                                        types.Content(role="user", parts=[types.Part.from_function_response(name="update_student_status", response={"result": result_msg})])
                                    ],
                                    config=types.GenerateContentConfig(system_instruction=system_instruction)
                                )
                                if followup and followup.text:
                                    ai_reply = followup.text
                    elif response and response.text:
                        ai_reply = response.text

                    db_chat.append({"role": "assistant", "content": ai_reply})
                    enrollment_ref.update({f"modules.{active_m_id}.chat_history": db_chat})
                    st.rerun()  # ← これで右カラムのグラフも最新状態で再描画される

        with col_right:
            st.markdown("<h3 style='font-size: 1.15rem; font-weight: bold; color: #1e293b;'>📈 リアルタイム能力査定</h3>", unsafe_allow_html=True)
            status = mod_progress.get("current_status", {"knowledge_level": 1, "thinking_level": 1, "application_level": 1})
            k, t, a = status.get("knowledge_level", 1), status.get("thinking_level", 1), status.get("application_level", 1)
            criteria = current_module_info.get("passing_criteria", {"knowledge_level": 4, "thinking_level": 4, "application_level": 3})

            st.markdown(f"**💡 知識レベル:** `Lv.{k} / {criteria['knowledge_level']}`")
            st.progress(min(k / 5.0, 1.0))
            st.markdown(f"**🧠 思考レベル:** `Lv.{t} / {criteria['thinking_level']}`")
            st.progress(min(t / 5.0, 1.0))
            st.markdown(f"**🚀 応用レベル:** `Lv.{a} / {criteria['application_level']}`")
            st.progress(min(a / 5.0, 1.0))
            st.pyplot(draw_radar_chart([k, t, a], [criteria['knowledge_level'], criteria['thinking_level'], criteria['application_level']]))

# ==============================================================================
# 👨‍🏫 教授用画面
# ==============================================================================
with tab_professor:
    col_prof_left, col_prof_center, col_prof_right = st.columns([3, 5, 4])

    with col_prof_left:
        st.markdown("<h3 style='font-size: 1.15rem; font-weight: bold; color: #1e293b;'>👤 受講生名簿</h3>", unsafe_allow_html=True)

        # ---------- 生徒追加 ----------
        with st.expander("＋ 生徒を追加"):
            new_student_name = st.text_input("生徒の名前", key="new_student_name")
            if st.button("追加する", key="add_student_btn"):
                if new_student_name.strip():
                    new_sid = f"student_{uuid.uuid4().hex[:6]}"
                    updated_roster = roster + [{"student_id": new_sid, "display_name": new_student_name.strip()}]
                    db.collection("classes").document(class_id).update({"roster": updated_roster})
                    st.success(f"{new_student_name} を追加しました")
                    st.rerun()
                else:
                    st.warning("名前を入力してください")

        prof_student_options = {s["student_id"]: s["display_name"] for s in roster}
        if not prof_student_options:
            st.info("受講生がまだ登録されていません。")
            s_data = {}
            active_prof_s_id = None
        else:
            active_prof_s_id = st.radio(
                "カルテを開く生徒を選択",
                options=list(prof_student_options.keys()),
                format_func=lambda sid: prof_student_options[sid],
                key="prof_student_radio"
            )
            enroll_doc = db.collection("enrollments").document(f"{class_id}_{active_prof_s_id}").get()
            s_data = enroll_doc.to_dict() if enroll_doc.exists else {}

        # ---------- 章の管理（追加・削除） ----------
        st.markdown("---")
        st.markdown("<h4 style='font-size: 0.95rem; font-weight: bold; color: #334155;'>📄 章の管理</h4>", unsafe_allow_html=True)

        for m in modules:
            c1, c2 = st.columns([4, 1])
            c1.write(f"**{m['module_id']}**: {m['title']}")
            if c2.button("🗑削除", key=f"delete_{m['module_id']}"):
                updated_modules = [mm for mm in modules if mm["module_id"] != m["module_id"]]
                db.collection("classes").document(class_id).update({"modules": updated_modules})
                st.rerun()

        uploaded_pdf = st.file_uploader("授業スライド(PDF)をアップロード", type="pdf", key="pdf_uploader")
        if uploaded_pdf is not None:
            if st.button("AIに章を設計させる", key="generate_module_btn"):
                with st.spinner("PDFを解析し、学習目標を設計中..."):
                    pdf_text = extract_pdf_text(uploaded_pdf)
                    if len(pdf_text) < 50:
                        st.error("PDFからテキストを抽出できませんでした。")
                    else:
                        existing_ids = [int(m["module_id"].split("_")[1]) for m in modules] or [0]
                        next_module_number = max(existing_ids) + 1
                        new_module = generate_module_from_pdf(pdf_text, next_module_number)
                        if new_module:
                            updated_modules = modules + [new_module]
                            db.collection("classes").document(class_id).update({"modules": updated_modules})
                            st.success(f"「{new_module['title']}」を追加しました！")
                            st.rerun()

    if not prof_student_options:
        st.stop()

    with col_prof_center:
        st.markdown("<h3 style='font-size: 1.15rem; font-weight: bold; color: #1e293b;'>📋 講義・カルテ対象</h3>", unsafe_allow_html=True)
        mod_keys = ["総合俯瞰評価"] + [f"{m['module_id']}: {m['title']}" for m in modules]
        selected_prof_mod = st.selectbox("授業カルテを切り替え", mod_keys, key="prof_mod_selectbox")
        st.markdown("---")

        if selected_prof_mod == "総合俯瞰評価":
            s_modules = s_data.get("modules", {})
            if s_modules:
                ks = [m.get("current_status", {}).get("knowledge_level", 1) for m in s_modules.values()]
                ts = [m.get("current_status", {}).get("thinking_level", 1) for m in s_modules.values()]
                aps = [m.get("current_status", {}).get("application_level", 1) for m in s_modules.values()]
                avg_current = [sum(ks)/len(ks), sum(ts)/len(ts), sum(aps)/len(aps)]
                tk = [m2.get("passing_criteria", {}).get("knowledge_level", 4) for m2 in modules] or [4]
                tt = [m2.get("passing_criteria", {}).get("thinking_level", 4) for m2 in modules] or [4]
                ta = [m2.get("passing_criteria", {}).get("application_level", 4) for m2 in modules] or [4]
                avg_target = [sum(tk)/len(tk), sum(tt)/len(tt), sum(ta)/len(ta)]
                st.pyplot(draw_radar_chart(avg_current, avg_target))
            else:
                st.info("まだ対話データがありません。")
        else:
            p_m_id = selected_prof_mod.split(":")[0]
            student_mod_progress = s_data.get("modules", {}).get(p_m_id, {})
            p_status = student_mod_progress.get("current_status", {"knowledge_level": 1, "thinking_level": 1, "application_level": 1})
            pk, pt, pa = p_status.get("knowledge_level", 1), p_status.get("thinking_level", 1), p_status.get("application_level", 1)
            p_criteria = next(m for m in modules if m["module_id"] == p_m_id).get("passing_criteria", {"knowledge_level": 4, "thinking_level": 4, "application_level": 3})
            st.write(f"・知識: **Lv.{pk}** / {p_criteria['knowledge_level']} | ・思考: **Lv.{pt}** / {p_criteria['thinking_level']} | ・応用: **Lv.{pa}** / {p_criteria['application_level']}")
            st.pyplot(draw_radar_chart([pk, pt, pa], [p_criteria['knowledge_level'], p_criteria['thinking_level'], p_criteria['application_level']]))

    with col_prof_right:
        st.markdown("<h3 style='font-size: 1.15rem; font-weight: bold; color: #1e293b;'>🩺 AI副担任の臨床カルテ</h3>", unsafe_allow_html=True)
        if selected_prof_mod == "総合俯瞰評価":
            st.text_area("📝 総合AIカルテ分析", value=s_data.get("overall_report", "対話が始まると分析が生成されます。"), height=180, disabled=True)
            st.text_area("💡 個別学習処方箋", value=s_data.get("overall_action_plan", "まずは第1章のテストに合格するよう促してください。"), height=110, disabled=True)
        else:
            p_m_id = selected_prof_mod.split(":")[0]
            student_mod_progress = s_data.get("modules", {}).get(p_m_id, {})
            st.text_area("📝 AI副担任からの引き継ぎ成長日報", value=student_mod_progress.get("growth_report", "現在対話を進めています。"), height=180, disabled=True)
            st.text_area("💡 次ステップ学習処方箋", value=student_mod_progress.get("action_plan", "現在、会話による能力評価プロセスの最中です。"), height=110, disabled=True)
