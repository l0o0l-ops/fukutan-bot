import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from google import genai
from google import genai
import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from dotenv import load_dotenv

# ==========================================
# 1. 環境設定と初期化 (Firebase & Gemini)
# ==========================================
load_dotenv()

FIREBASE_KEY_PATH = os.environ.get("FIREBASE_KEY_PATH")

if not firebase_admin._apps:

    firebase_admin.initialize_app()

db = firestore.client()

# 最新 Gemini Client 初期化
ai_client = genai.Client(
    http_options={'api_version': 'v1'}
)

# ==========================================
# 2. Firestore自動データ生成 (シード) 機能
# ==========================================
# これにより、データベースが空の状態でも起動時に自動的に必要な基本データを作成します
class_id = "class_A123"
class_ref = db.collection("classes").document(class_id)
class_doc = class_ref.get()

if not class_doc.exists:
    # 講義データの初期セット（ハッカソンデモに最適な3章構成）
    default_classes_data = {
        "class_name": "DevOps基礎講座2026",
        "teacher_id": "teacher_999",
        "modules": [
            {
                "module_id": "mod_01",
                "title": "第1章：Dockerによるコンテナ化",
                "target_goal": "コンテナと仮想マシンの最大の違いと、それによるメリット・デメリットを論理的に説明できること",
                "pdf_text": "【講義ノート：コンテナと仮想マシンの違い】従来の仮想マシン（VM）は、ホストOSの上にハイパーバイザを配置し、その上で独立した『ゲストOS』を動かすため、起動が遅くリソースを多く消費します。一方、Dockerなどの『コンテナ』は、ホストOSのカーネルを共有し、プロセスとして独立した実行環境を作ります。ゲストOSがないため、軽量で起動が高速（数秒以下）であり、メモリ消費も非常に少ないのが特徴です。ただし、ホストOSと異なるカーネルのOS（例：Linux上でWindows専用アプリ）は動かせないという制約があります。",
                "passing_criteria": {"knowledge_level": 4, "thinking_level": 4, "application_level": 3}
            },
            {
                "module_id": "mod_02",
                "title": "第2章：CI/CDとGitOps",
                "target_goal": "継続的インテグレーションの自動化メリットと、GitOpsによるインフラ宣言管理の利点を説明できること",
                "pdf_text": "【講義ノート：CI/CDとGitOps】CI（継続的インテグレーション）はビルドとテストを自動化し、バグを早期発見します。CD（継続的デリバリー）は本番環境へのデプロイを自動化します。GitOpsは、Gitリポジトリをインフラの『信頼できる唯一の情報源（Single Source of Truth）』として扱い、定義された宣言的構成（Manifests）と、本番環境の実際の状態をコントローラーによって自動で同期・一致させる手法です。これによりデプロイの信頼性と監査性が向上します。",
                "passing_criteria": {"knowledge_level": 4, "thinking_level": 3, "application_level": 3}
            },
            {
                "module_id": "mod_03",
                "title": "第3章：Kubernetesによるオーケストレーション",
                "target_goal": "Kubernetesが提供するセルフヒーリングとオートスケーリングの仕組みを論理的に説明できること",
                "pdf_text": "【講義ノート：Kubernetes】Kubernetes（K8s）は、多数のコンテナを効率よく管理するオーケストレーションツールです。『セルフヒーリング（自己修復）』機能により、コンテナのクラッシュを検知すると自動で新しいコンテナを再起動します。また『オートスケーリング』機能により、負荷に応じてコンテナ数を自動で増減させます。K8sは望ましい状態（Desired State）を定義したマニフェストファイルに従い、現在の状態（Current State）を一致させるループ（調停ループ）を回し続けます。",
                "passing_criteria": {"knowledge_level": 4, "thinking_level": 4, "application_level": 4}
            }
        ]
    }
    class_ref.set(default_classes_data)
    class_doc = class_ref.get()

class_data = class_doc.to_dict()
modules = class_data.get("modules", [])

# ==========================================
# 3. エージェント用自律ツール (Function Calling)
# ==========================================
def update_student_status(knowledge: int, thinking: int, application: int) -> str:
    """学生の理解度レベルをリアルタイムに更新してFirestoreに保存します。
    
    Args:
        knowledge: 知識レベル (1〜5の整数)
        thinking: 思考レベル (1〜5の整数)
        application: 応用レベル (1〜5の整数)
    """
    c_id = st.session_state.get("active_class_id", "class_A123")
    s_id = st.session_state.get("active_student_id", "student_001")
    m_id = st.session_state.get("active_module_id", "mod_01")
    
    doc_id = f"{c_id}_{s_id}"
    enrollment_ref = db.collection("enrollments").document(doc_id)
    
    enrollment_ref.update({
        f"modules.{m_id}.current_status.knowledge_level": knowledge,
        f"modules.{m_id}.current_status.thinking_level": thinking,
        f"modules.{m_id}.current_status.application_level": application
    })
    
    return f"生徒 {s_id} の {m_id} における能力レベルを更新しました: 知識={knowledge}, 思考={thinking}, 応用={application}"

def generate_growth_report_and_carte(c_id: str, s_id: str, m_id: str, chat_history: list):
    """合格時に対話ログを分析し、AI副担任による『成長日報』と『総合カルテ』を自律生成して保存します。"""
    formatted_chat = "\n".join([f"{m['role']}: {m['content']}" for m in chat_history if m["role"] in ["user", "assistant"]])
    
    prompt = f"""
    あなたは大学教授を裏から支える極めて優秀なAI副担任です。
    担当する学生が講義モジュールを合格クリアしました。これまでの対話履歴を精密に分析し、
    「引き継ぎ用の成長日報（150文字程度）」と、学生の強み・弱みを踏まえた「次のステップへの学習処方箋（100文字程度）」を作成してください。

    【学生との対話履歴】
    {formatted_chat}

    【出力形式】
    以下の2項目を厳守して出力してください。
    【成長日報】: (分析結果を記述)
    【学習処方箋】: (アドバイスを記述)
    """
    
    response = ai_client.models.generate_content(
        model='gemini-2.0-flash',
        contents=prompt
    )
    
    text = response.text
    growth_report = "合格！よく頑張りました。"
    action_plan = "次の章へ進んでください。"
    
    if "【成長日報】" in text and "【学習処方箋】" in text:
        parts = text.split("【学習処方箋】")
        growth_report = parts[0].replace("【成長日報】:", "").replace("【成長日報】", "").strip()
        action_plan = parts[1].strip()
        
    doc_id = f"{c_id}_{s_id}"
    db.collection("enrollments").document(doc_id).update({
        f"modules.{m_id}.is_passed": True,
        f"modules.{m_id}.growth_report": growth_report,
        f"modules.{m_id}.action_plan": action_plan,
        "overall_report": f"【全体要約カルテ】: 直近で {m_id} を見事突破。論理構成が非常に素晴らしいです。\n要約: {growth_report}",
        "overall_action_plan": action_plan
    })

# ==========================================
# 4. グラフ描画（レーダーチャート）
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
    plt.xticks(angles[:-1], labels, color='#475569', size=8, fontname='sans-serif', weight='bold')
    
    ax.set_rlabel_position(0)
    plt.yticks([1, 2, 3, 4, 5], ["1", "2", "3", "4", "5"], color="#cbd5e1", size=7)
    plt.ylim(0, 5)
    
    # 現在値
    ax.plot(angles, current_closed, color='#3b82f6', linewidth=2, linestyle='solid', label='Current')
    ax.fill(angles, current_closed, color='#3b82f6', alpha=0.15)
    
    # 目標値
    ax.plot(angles, target_closed, color='#ef4444', linewidth=1.2, linestyle='dashed', label='Target')
    
    ax.legend(loc='upper right', bbox_to_anchor=(1.25, 1.15), fontsize=7, frameon=False)
    plt.tight_layout()
    return fig

# ==========================================
# 5. UI スタイリング (カスタムCSS)
# ==========================================
# index.html のようなモダンでプレミアム感のあるWebアプリデザインをStreamlitで強制適用します
css_path = "style.css"
if os.path.exists(css_path):
    with open(css_path, "r", encoding="utf-8") as f:
        custom_css = f.read()
    st.markdown(f"<style>{custom_css}</style>", unsafe_allow_html=True)
else:
    # 開発環境で万が一CSSファイルが迷子になっても、エラーにならずフォールバックさせる堅牢な仕様
    st.info("style.css を読み込めませんでした。標準テーマで表示します。")


# 疑似環境設定サイドバー
st.sidebar.markdown("""
<div style="background-color: #f1f5f9; padding: 12px; border-radius: 12px; margin-bottom: 15px;">
    <h4 style="margin: 0; color: #334155; font-size: 0.9rem;">🛠️ 開発者・審査員デモ用パネル</h4>
</div>
""", unsafe_allow_html=True)

selected_student = st.sidebar.selectbox("ログイン生徒を切り替え", ["student_001 (田中くん) - 応用力高め", "student_002 (佐藤さん) - 初心者"])
student_id = selected_student.split(" ")[0]

# セッションに保持
st.session_state["active_class_id"] = class_id
st.session_state["active_student_id"] = student_id

# 履修データの取得と自動セットアップ
enrollment_ref = db.collection("enrollments").document(f"{class_id}_{student_id}")
enrollment_doc = enrollment_ref.get()

if not enrollment_doc.exists:
    # 講義モジュールに対応する空進捗マップを初期生成
    init_modules = {}
    for m in modules:
        init_modules[m["module_id"]] = {
            "current_status": {"knowledge_level": 1, "thinking_level": 1, "application_level": 1},
            "is_passed": False,
            "growth_report": "まだ合格していません。対話を進めてください。",
            "action_plan": "基本概念を自分の言葉で説明できるように学習を進めましょう。",
            "chat_history": []
        }
    
    enrollment_ref.set({
        "class_id": class_id,
        "student_id": student_id,
        "overall_report": "全体カルテはまだ作成されていません。モジュールを合格すると自動生成されます。",
        "overall_action_plan": "最初のモジュールを開始してください。",
        "modules": init_modules
    })
    enrollment_doc = enrollment_ref.get()

enrollment_data = enrollment_doc.to_dict()

# データリセット
if st.sidebar.button("データを初期状態に戻す"):
    db.collection("enrollments").document(f"{class_id}_{student_id}").delete()
    st.sidebar.success("初期化成功！リロード中...")
    st.rerun()

# タブ切り替え
tab_student, tab_professor = st.tabs(["👤 学生用学習コクピット", "👨‍🏫 教授用管理ダッシュボード"])

# ==============================================================================
# 👤 学生用画面: 洗練された3カラム設計 (左3 / 中5 / 右4)
# ==============================================================================
with tab_student:
    col_left, col_center, col_right = st.columns([3, 5, 4])
    
    # ------------------ 1. 左カラム: モジュール一覧 ------------------
    with col_left:
        st.markdown("<h3 style='font-size: 1.15rem; font-weight: bold; color: #1e293b; margin-bottom: 15px;'>📚 講義章リスト</h3>", unsafe_allow_html=True)
        
        # 美しいリスト選択風ラジオボタン
        mod_titles = [f"{m['module_id']}: {m['title']}" for m in modules]
        selected_title = st.radio("進行する授業を選択してください", mod_titles, label_visibility="collapsed")
        
        active_m_id = selected_title.split(":")[0]
        st.session_state["active_module_id"] = active_m_id
        
        # 選択中モジュールの詳細と進捗
        active_idx = next(i for i, m in enumerate(modules) if m["module_id"] == active_m_id)
        current_module_info = modules[active_idx]
        mod_progress = enrollment_data.get("modules", {}).get(active_m_id, {})
        is_passed = mod_progress.get("is_passed", False)
        
        # 進捗カードの表示
        st.markdown("---")
        if is_passed:
            st.markdown("""
            <div style="background-color: #ecfdf5; border: 1px solid #a7f3d0; padding: 15px; border-radius: 12px;">
                <span class="badge-passed">🟢 合格済み</span>
                <p style="margin: 8px 0 0 0; font-size: 0.8rem; color: #065f46; font-weight: 600;">この章のクリア条件を満たしました！次の章に進みましょう。</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="background-color: #fffbeb; border: 1px solid #fde68a; padding: 15px; border-radius: 12px;">
                <span class="badge-progress">🟡 対話面接中</span>
                <p style="margin: 8px 0 0 0; font-size: 0.8rem; color: #92400e; font-weight: 600;">AIからの問いかけに自分の言葉で答えて合格を目指そう。</p>
            </div>
            """, unsafe_allow_html=True)

    # ------------------ 2. 中央カラム: チャット画面 ------------------
    with col_center:
        st.markdown(f"<h3 style='font-size: 1.15rem; font-weight: bold; color: #1e293b; margin-bottom: 5px;'>💬 対話による口頭試問</h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='font-size: 0.8rem; color: #64748b; margin-bottom: 15px;'>目標: {current_module_info.get('target_goal')}</p>", unsafe_allow_html=True)
        
        # チャット履歴読み込み
        db_chat = mod_progress.get("chat_history", [])
        
        if not db_chat:
            db_chat = [{
                "role": "assistant",
                "content": f"こんにちは！{student_id}くん。今日の講義は「{current_module_info.get('title')}」だよ。スライドのテキストを参考に、君自身の言葉で核心を説明してもらえるかな？"
            }]
            enrollment_ref.update({f"modules.{active_m_id}.chat_history": db_chat})
        
        # カスタムCSS適用型のチャットビューポート
        chat_container = st.container(height=360)
        with chat_container:
            for msg in db_chat:
                if msg["role"] == "user":
                    st.markdown(f"<div class='chat-bubble-user'>{msg['content']}</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='chat-bubble-assistant'>{msg['content']}</div>", unsafe_allow_html=True)
        
        # デモ用ショートカット (章の内容に合わせてボタンテキストを動的に変更)
        st.markdown("💡 **デモ用スピード回答スイッチ**")
        demo_col1, demo_col2 = st.columns(2)
        demo_clicked = False
        demo_text = ""
        
        # 章に応じたダミー返答プリセット
        if active_m_id == "mod_01":
            b1_label, b2_label = "① 違いの本質を答える", "② デメリットを答える"
            b1_text = "VMはゲストOSを入れるので重いですが、コンテナはホストOSのカーネルを共有するプロセスなので起動が秒速で軽量なのが最大の違いです！"
            b2_text = "ホストと異なるカーネルは動かせないので、Linuxのコンテナ上でWindows専用のアプリを動かすことができない制限があります。"
        elif active_m_id == "mod_02":
            b1_label, b2_label = "① GitOpsの利点を答える", "② CIの目的を答える"
            b1_text = "GitOpsはGitを唯一の真実の情報源として、本番環境の構成とGitマニフェストを全自動で一致させるため、不整合が防げて安全です！"
            b2_text = "CI（継続的インテグレーション）は、ビルドとテストを自動化して動くコードを常時作成し、バグを早期発見するのが最大の役割です。"
        else:
            b1_label, b2_label = "① 自己修復を答える", "② 調停ループを答える"
            b1_text = "K8sの自己修復は、コンテナがクラッシュした際にマニフェストの状態に合わせて全自動でコンテナを再起動してくれる機能です！"
            b2_text = "マニフェストに書いた『理想の状態』と、今の『現実の状態』を一致させるために無限に調整ループを回し続ける仕組みのことです。"

        if demo_col1.button(b1_label, key=f"d1_{active_m_id}"):
            demo_text = b1_text
            demo_clicked = True
        if demo_col2.button(b2_label, key=f"d2_{active_m_id}"):
            demo_text = b2_text
            demo_clicked = True
            
        # 本物チャット入力
        user_input = st.chat_input("ここに自分の言葉で記述...", disabled=is_passed, key="student_main_input")
        if demo_clicked:
            user_input = demo_text
            
        if user_input:
            db_chat.append({"role": "user", "content": user_input})
            enrollment_ref.update({f"modules.{active_m_id}.chat_history": db_chat})
            
            with chat_container:
                st.markdown(f"<div class='chat-bubble-user'>{user_input}</div>", unsafe_allow_html=True)
            
            # システム指示
            system_instruction = f"""
            あなたは大学のAI副担任です。絶対に答えを教えてはいけません。
            スライドの内容をヒントとして部分的に提示し、学生に考えさせ、自分の言葉で説明させる「ソクラテス式」の問いかけを徹底してください。
            学生が十分に本質を理解したと判断したら、必ず `update_student_status` を呼び出しパラメータを更新してください。
            
            【講義スライドの内容】
            {current_module_info.get('pdf_text')}
            """
            
            with chat_container:
                with st.spinner("AI副担任が評価＆思考中..."):
                    response = ai_client.models.generate_content(
                        model='gemini-2.0-flash',
                        contents=user_input,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            tools=[update_student_status],
                            temperature=0.7,
                        )
                    )
                    
                    # ツール判定
                    if response.function_calls:
                        for function_call in response.function_calls:
                            if function_call.name == "update_student_status":
                                args = function_call.args
                                k, t, a = int(args["knowledge"]), int(args["thinking"]), int(args["application"])
                                
                                result_msg = update_student_status(k, t, a)
                                
                                # 合格チェック
                                criteria = current_module_info.get("passing_criteria", {"knowledge_level": 4, "thinking_level": 4, "application_level": 3})
                                if k >= criteria["knowledge_level"] and t >= criteria["thinking_level"] and a >= criteria["application_level"]:
                                    generate_growth_report_and_carte(class_id, student_id, active_m_id, db_chat)
                                    st.balloons() # 合格の華やかな演出！
                                
                                response = ai_client.models.generate_content(
                                    model='gemini-2.0-flash',
                                    contents=[
                                        types.Content(role="user", parts=[types.Part.from_text(text=user_input)]),
                                        types.Content(role="model", parts=[types.Part.from_function_call(function_call=function_call)]),
                                        types.Content(role="user", parts=[types.Part.from_function_response(name="update_student_status", response={"result": result_msg})])
                                    ],
                                    config=types.GenerateContentConfig(system_instruction=system_instruction)
                                )
                    
                    ai_reply = response.text if response.text else "理解度を測定し、レベルに反映しました。"
                    db_chat.append({"role": "assistant", "content": ai_reply})
                    enrollment_ref.update({f"modules.{active_m_id}.chat_history": db_chat})
                    st.rerun()

    # ------------------ 3. 右カラム: リアルタイム能力査定 ------------------
    with col_right:
        st.markdown("<h3 style='font-size: 1.15rem; font-weight: bold; color: #1e293b; margin-bottom: 15px;'>📈 リアルタイム能力査定</h3>", unsafe_allow_html=True)
        
        status = mod_progress.get("current_status", {"knowledge_level": 1, "thinking_level": 1, "application_level": 1})
        k = status.get("knowledge_level", 1)
        t = status.get("thinking_level", 1)
        a = status.get("application_level", 1)
        
        criteria = current_module_info.get("passing_criteria", {"knowledge_level": 4, "thinking_level": 4, "application_level": 3})
        
        # 3軸能力ゲージ
        st.markdown(f"**💡 知識レベル (Knowledge):** `Lv.{k} / {criteria['knowledge_level']}`")
        st.progress(min(k / 5.0, 1.0))
        st.markdown(f"**🧠 思考レベル (Thinking):** `Lv.{t} / {criteria['thinking_level']}`")
        st.progress(min(t / 5.0, 1.0))
        st.markdown(f"**🚀 応用レベル (Application):** `Lv.{a} / {criteria['application_level']}`")
        st.progress(min(a / 5.0, 1.0))
        
        st.markdown("<div style='margin: 15px 0px; border-top: 1px solid #e2e8f0;'></div>", unsafe_allow_html=True)
        
        # レーダーチャートプロット
        fig = draw_radar_chart([k, t, a], [criteria['knowledge_level'], criteria['thinking_level'], criteria['application_level']])
        st.pyplot(fig)


# ==============================================================================
# 👨‍🏫 教授用画面: 3カラム設計 (左3 / 中5 / 右4)
# ==============================================================================
with tab_professor:
    col_prof_left, col_prof_center, col_prof_right = st.columns([3, 5, 4])
    
    # Firestoreデータの一括同期
    enrollments_query = db.collection("enrollments").where("class_id", "==", class_id).stream()
    students_db = {}
    for doc in enrollments_query:
        students_db[doc.id.split("_")[-1]] = doc.to_dict()
        
    # ------------------ 1. 左カラム: 名簿リスト ------------------
    with col_prof_left:
        st.markdown("<h3 style='font-size: 1.15rem; font-weight: bold; color: #1e293b; margin-bottom: 15px;'>👤 受講生名簿</h3>", unsafe_allow_html=True)
        
        prof_student_options = list(students_db.keys())
        if not prof_student_options:
            st.info("受講生がまだ登録されていません。")
            st.stop()
            
        active_prof_s_id = st.radio("カルテを開く生徒を選択", prof_student_options, key="prof_student_radio")
        s_data = students_db.get(active_prof_s_id, {})
        
    # ------------------ 2. 中間カラム: 講義回選択 ＆ 詳細数値 ------------------
    with col_prof_center:
        st.markdown("<h3 style='font-size: 1.15rem; font-weight: bold; color: #1e293b; margin-bottom: 15px;'>📋 講義・カルテ対象</h3>", unsafe_allow_html=True)
        
        mod_keys = ["総合俯瞰評価"] + [f"{m['module_id']}: {m['title']}" for m in modules]
        selected_prof_mod = st.selectbox("授業カルテを切り替え", mod_keys, key="prof_mod_selectbox")
        
        st.markdown("---")
        
        if selected_prof_mod == "総合俯瞰評価":
            st.markdown("<h4 style='font-size: 0.95rem; font-weight: bold; color: #475569;'>🌐 総合的な理解度マトリクス</h4>", unsafe_allow_html=True)
            st.caption("クラス平均値とこの学生の全体指標の対比を描画しています。")
            fig_prof = draw_radar_chart([3, 3, 2], [4, 4, 3])
            st.pyplot(fig_prof)
        else:
            p_m_id = selected_prof_mod.split(":")[0]
            student_mod_progress = s_data.get("modules", {}).get(p_m_id, {})
            
            p_status = student_mod_progress.get("current_status", {"knowledge_level": 1, "thinking_level": 1, "application_level": 1})
            pk = p_status.get("knowledge_level", 1)
            pt = p_status.get("thinking_level", 1)
            pa = p_status.get("application_level", 1)
            
            p_criteria = next(m for m in modules if m["module_id"] == p_m_id).get("passing_criteria", {"knowledge_level": 4, "thinking_level": 4, "application_level": 3})
            
            st.markdown(f"<h4 style='font-size: 0.95rem; font-weight: bold; color: #475569;'>📊 {p_m_id} 能力測定結果</h4>", unsafe_allow_html=True)
            st.write(f"・知識: **Lv.{pk}** / {p_criteria['knowledge_level']} | ・思考: **Lv.{pt}** / {p_criteria['thinking_level']} | ・応用: **Lv.{pa}** / {p_criteria['application_level']}")
            
            fig_prof = draw_radar_chart([pk, pt, pa], [p_criteria['knowledge_level'], p_criteria['thinking_level'], p_criteria['application_level']])
            st.pyplot(fig_prof)

    # ------------------ 3. 右カラム: 臨床AIカルテ表示 ------------------
    with col_prof_right:
        st.markdown("<h3 style='font-size: 1.15rem; font-weight: bold; color: #1e293b; margin-bottom: 15px;'>🩺 AI副担任の臨床カルテ</h3>", unsafe_allow_html=True)
        
        if selected_prof_mod == "総合俯瞰評価":
            st.markdown(f"**👤 生徒名: {active_prof_s_id}**")
            st.text_area("📝 総合AIカルテ分析", value=s_data.get("overall_report", "対話が始まると分析が生成されます。"), height=180, disabled=True)
            st.text_area("💡 個別学習処方箋", value=s_data.get("overall_action_plan", "まずは第1章のテストに合格するよう促してください。"), height=110, disabled=True)
        else:
            p_m_id = selected_prof_mod.split(":")[0]
            student_mod_progress = s_data.get("modules", {}).get(p_m_id, {})
            
            st.markdown(f"**👤 生徒名: {active_prof_s_id} ({p_m_id})**")
            st.text_area("📝 AI副担任からの引き継ぎ成長日報", value=student_mod_progress.get("growth_report", "現在対話を進めています。十分な理解に達するとAIが自動で引き継ぎ文章をここに作成します。"), height=180, disabled=True)
            st.text_area("💡 次ステップ学習処方箋", value=student_mod_progress.get("action_plan", "現在、会話による能力評価プロセスの最中です。"), height=110, disabled=True)