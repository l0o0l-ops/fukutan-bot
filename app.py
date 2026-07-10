import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from google import genai
from google.genai import types
import json

# ==========================================
# 1. 認証情報の設定（環境に合わせて書き換えてください）
# ==========================================
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
FIREBASE_KEY_PATH = "path/to/your/firebase-adminsdk-key.json"

# Firebaseの初期化
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Geminiクライアントの初期化
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 2. エージェントの「手足」となる関数（ツール）の定義
# ==========================================
def update_student_status(knowledge: int, thinking: int, application: int) -> str:
    """学生の理解度ステータス（パラメータ）をリアルタイムに更新します。
    学生が十分な理解を示した、あるいは新しい概念を応用できたと判断した際に呼び出してください。
    
    Args:
        knowledge: 知識レベル (1から5の整数)
        thinking: 思考レベル (1から5の整数)
        application: 応用レベル (1から5の整数)
    """
    # Streamlitのセッションから現在のクラス・生徒IDを取得
    c_id = st.session_state.get("class_id")
    s_id = st.session_state.get("student_id")
    
    if c_id and s_id:
        doc_id = f"{c_id}_{s_id}"
        db.collection("enrollments").document(doc_id).update({
            "current_status.knowledge_level": knowledge,
            "current_status.thinking_level": thinking,
            "current_status.application_level": application
        })
        return f"生徒 {s_id} のステータスを更新しました: 知識={knowledge}, 思考={thinking}, 応用={application}"
    return "エラー: クラスIDまたは生徒IDが指定されていません。"

# ==========================================
# 3. Streamlit UI 画面の構築
# ==========================================
st.set_page_config(page_title="インテリジェント・シラバス", layout="wide")
st.title("🎓 インテリジェント・シラバス (AI Agent MVP)")

# デモ用切り替えスイッチ
st.sidebar.header("⚙️ デモ環境設定")
selected_class = st.sidebar.selectbox("1. 授業（クラス）を選択", ["class_A123 (DevOps基礎)", "class_B456 (データサイエンス)"])
selected_student = st.sidebar.selectbox("2. 生徒を選択", ["student_001 (田中くん)", "student_002 (佐藤さん)"])

class_id = selected_class.split(" ")[0]
student_id = selected_student.split(" ")[0]

# セッション状態にIDを保持（ツール関数からアクセスするため）
st.session_state["class_id"] = class_id
st.session_state["student_id"] = student_id

# タブ切り替え
tab_student, tab_professor = st.tabs(["👤 学生用画面 (チャット面接)", "👨‍🏫 教授用画面 (管理ダッシュボード)"])

# ------------------------------------------
# 【学生用画面】
# ------------------------------------------
with tab_student:
    st.subheader("📚 AIエージェントとの対話（ソクラテス式面接）")
    
    # Firestoreから最新のステータスを取得してメーター表示
    enrollment_ref = db.collection("enrollments").document(f"{class_id}_{student_id}")
    enrollment_doc = enrollment_ref.get()
    
    if enrollment_doc.exists:
        status = enrollment_doc.to_dict().get("current_status", {})
        col1, col2, col3 = st.columns(3)
        col1.metric("💡 知識レベル", f"Lv.{status.get('knowledge_level', 1)}")
        col2.metric("🧠 思考レベル", f"Lv.{status.get('thinking_level', 1)}")
        col3.metric("🚀 応用レベル", f"Lv.{status.get('application_level', 1)}")
    else:
        st.error("生徒の初期データがありません。Firestoreを確認してください。")
        st.stop()

    # Firestoreから講義スライドの前提知識（pdf_text）を取得
    class_doc = db.collection("classes").document(class_id).get()
    pdf_context = ""
    if class_doc.exists:
        modules = class_doc.to_dict().get("modules", [])
        if modules:
            pdf_context = modules[0].get("pdf_text", "")

    # セッション内にチャット履歴のUI表示用リストを保持
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "こんにちは！今日の講義スライドの内容について、あなた自身の言葉で説明してもらうよ。準備はいいかい？"}]

    # 過去のメッセージを表示
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # 学生のチャット入力処理
    if user_input := st.chat_input("ここに回答を入力..."):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # Gemini Agentへのプロンプト組み立て
        system_instruction = f"""
        あなたは大学の講義を担当する厳格かつ親切なAI副担任です。
        以下の【講義スライドの内容】を基に、学生に「ソクラテス式対話（答えを教えず、問いかける）」を行ってください。

        【講義スライドの内容】
        {pdf_context}

        【行動ルール】
        1. 答えを直接教えてはいけません。ヒントを与え、学生自身の言葉で説明させてください。
        2. 学生の回答を分析し、理解が進んだ（例：ただの暗記ではなく概念の理由を説明できた、など）と判断したら、
           必ず `update_student_status` ツールを呼び出して、パラメータを適切なレベル（1〜5）に更新してください。
        3. ツールを実行した場合は、学生への返答の中で「理解度が向上したため、ステータスを更新しました」と伝えてください。
        """

        # チャット履歴をGeminiの形式に変換
        gemini_history = []
        for m in st.session_state.messages[:-1]: # 最新の入力以外
            gemini_history.append(
                types.Content(role="user" if m["role"] == "user" else "model", parts=[types.Part.from_text(text=m["content"])])
            )

        with st.chat_message("assistant"):
            # Gemini APIの呼び出し（Function Callingを有効化）
            response = ai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=user_input,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=[update_student_status], # ツール（関数）をエージェントに渡す
                    temperature=0.7,
                )
            )
            
            # エージェントが関数を呼び出すべきと判断した場合の処理
            if response.function_calls:
                for function_call in response.function_calls:
                    if function_call.name == "update_student_status":
                        # 引数をパースして関数を実行
                        args = function_call.args
                        result_msg = update_student_status(
                            knowledge=int(args["knowledge"]),
                            thinking=int(args["thinking"]),
                            application=int(args["application"])
                        )
                        # ツール実行結果を再度Geminiにフィードバックして、最終的な返答を得る
                        response = ai_client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=[
                                types.Content(role="user", parts=[types.Part.from_text(text=user_input)]),
                                types.Content(role="model", parts=[types.Part.from_function_call(function_call=function_call)]),
                                types.Content(role="user", parts=[types.Part.from_function_response(
                                    name="update_student_status",
                                    response={"result": result_msg}
                                )])
                            ],
                            config=types.GenerateContentConfig(system_instruction=system_instruction)
                        )

            # 最終的なAIのメッセージを表示・保存
            ai_reply = response.text
            st.markdown(ai_reply)
            st.session_state.messages.append({"role": "assistant", "content": ai_reply})
            
            # ステータスメーターを最新にするために画面をリロード
            st.rerun()

# ------------------------------------------
# 【教授用画面】
# ------------------------------------------
with tab_professor:
    st.subheader("📊 授業全体の進捗ダッシュボード")
    st.write(f"選択中の講義: **{selected_class}**")
    st.info("Phase 2でここにクラス全体の統計グラフや、AIが生成した成長日報を表示します。")