"""
インテリジェント・シラバス (Intelligent Syllabus)
FastAPI + Firestore + Vertex AI (Gemini Enterprise Agent Platform) 構成

Streamlit版から、UIの自由度とAPI応答速度を優先してFastAPI + バニラJSへ移行。
Firestoreのデータ構造(classes / enrollments)は既存のものをそのまま利用する。
"""

import io
import json
import os
import uuid
from typing import Optional

import firebase_admin
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from firebase_admin import credentials, firestore
from google import genai
from google.genai import types
from pypdf import PdfReader
from starlette.requests import Request

# ==========================================
# 環境設定と初期化
# ==========================================
FIREBASE_KEY_PATH = os.environ.get("FIREBASE_KEY_PATH")
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "asia-northeast1")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

if not firebase_admin._apps:
    if FIREBASE_KEY_PATH and os.path.exists(FIREBASE_KEY_PATH):
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred)
    else:
        # Cloud Run本番: アタッチされたサービスアカウントを自動使用
        firebase_admin.initialize_app()

db = firestore.client()

if not PROJECT_ID:
    raise RuntimeError(
        "環境変数 GOOGLE_CLOUD_PROJECT が設定されていません。"
        "Cloud Runのサービス設定で追加してください。"
    )

ai_client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

app = FastAPI(title="Intelligent Syllabus")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"))

DEFAULT_CRITERIA = {"knowledge_level": 4, "thinking_level": 4, "application_level": 3}


def call_gemini(**kwargs):
    """Gemini呼び出しを一箇所に集約し、失敗時にAPIとして安全な形で例外化する"""
    try:
        return ai_client.models.generate_content(**kwargs)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AIとの通信でエラーが発生しました: {e}")


# ==========================================
# Firestoreヘルパー
# ==========================================
def get_class_ref(class_id: str):
    return db.collection("classes").document(class_id)


def get_class_or_404(class_id: str) -> dict:
    doc = get_class_ref(class_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="クラスが見つかりません")
    return doc.to_dict()


def get_enrollment_ref(class_id: str, student_id: str):
    return db.collection("enrollments").document(f"{class_id}_{student_id}")


def ensure_enrollment(class_id: str, student_id: str, modules: list) -> dict:
    ref = get_enrollment_ref(class_id, student_id)
    doc = ref.get()
    if doc.exists:
        return doc.to_dict()

    init_modules = {}
    for m in modules:
        init_modules[m["module_id"]] = {
            "current_status": {"knowledge_level": 1, "thinking_level": 1, "application_level": 1},
            "is_passed": False,
            "growth_report": "まだ合格していません。対話を進めてください。",
            "action_plan": "基本概念を自分の言葉で説明できるように学習を進めましょう。",
            "chat_history": [],
        }

    data = {
        "class_id": class_id,
        "student_id": student_id,
        "overall_report": "全体カルテはまだ作成されていません。モジュールを合格すると自動生成されます。",
        "overall_action_plan": "最初のモジュールを開始してください。",
        "modules": init_modules,
    }
    ref.set(data)
    return data


def ensure_seed_class():
    """デモ用のデフォルトクラスが1つも存在しない場合だけ、初回に作成する"""
    existing = list(db.collection("classes").limit(1).stream())
    if existing:
        return

    get_class_ref("class_A123").set(
        {
            "class_name": "DevOps基礎講座2026",
            "teacher_id": "teacher_999",
            "roster": [],
            "modules": [
                {
                    "module_id": "mod_01",
                    "title": "第1章：Dockerによるコンテナ化",
                    "target_goal": "コンテナと仮想マシンの最大の違いと、それによるメリット・デメリットを論理的に説明できること",
                    "pdf_text": (
                        "【講義ノート：コンテナと仮想マシンの違い】従来の仮想マシン（VM）は、"
                        "ホストOSの上にハイパーバイザを配置し、その上で独立した『ゲストOS』を動かすため、"
                        "起動が遅くリソースを多く消費します。一方、Dockerなどの『コンテナ』は、ホストOSの"
                        "カーネルを共有し、プロセスとして独立した実行環境を作ります。ゲストOSがないため、"
                        "軽量で起動が高速（数秒以下）であり、メモリ消費も非常に少ないのが特徴です。ただし、"
                        "ホストOSと異なるカーネルのOS（例：Linux上でWindows専用アプリ）は動かせないという"
                        "制約があります。"
                    ),
                    "passing_criteria": {"knowledge_level": 4, "thinking_level": 4, "application_level": 3},
                }
            ],
        }
    )


ensure_seed_class()


# ==========================================
# エージェント用自律ツール (Function Calling)
# ==========================================
def update_student_status(knowledge: int, thinking: int, application: int) -> str:
    """学生の理解度レベルをリアルタイムに更新してFirestoreに保存します。

    Args:
        knowledge: 知識レベル (1〜5の整数)
        thinking: 思考レベル (1〜5の整数)
        application: 応用レベル (1〜5の整数)
    """
    # この関数はcall_gemini経由のfunction_call解釈から呼ばれるため、
    # 対象のclass_id/student_id/module_idは呼び出し元から直接渡す
    raise NotImplementedError  # 実処理はチャットエンドポイント内でインライン化(下記参照)


def _apply_status_update(class_id: str, student_id: str, module_id: str, knowledge: int, thinking: int, application: int) -> str:
    ref = get_enrollment_ref(class_id, student_id)
    ref.update(
        {
            f"modules.{module_id}.current_status.knowledge_level": knowledge,
            f"modules.{module_id}.current_status.thinking_level": thinking,
            f"modules.{module_id}.current_status.application_level": application,
        }
    )
    return f"生徒 {student_id} の {module_id} における能力レベルを更新しました: 知識={knowledge}, 思考={thinking}, 応用={application}"


def _generate_growth_report(class_id: str, student_id: str, module_id: str, chat_history: list):
    formatted_chat = "\n".join(
        f"{m['role']}: {m['content']}" for m in chat_history if m["role"] in ("user", "assistant")
    )
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
    response = call_gemini(model=GEMINI_MODEL, contents=prompt)
    growth_report = "合格！よく頑張りました。"
    action_plan = "次の章へ進んでください。"

    text = response.text or ""
    if "【成長日報】" in text and "【学習処方箋】" in text:
        parts = text.split("【学習処方箋】")
        growth_report = parts[0].replace("【成長日報】:", "").replace("【成長日報】", "").strip()
        action_plan = parts[1].strip()

    get_enrollment_ref(class_id, student_id).update(
        {
            f"modules.{module_id}.is_passed": True,
            f"modules.{module_id}.growth_report": growth_report,
            f"modules.{module_id}.action_plan": action_plan,
            "overall_report": f"【全体要約カルテ】: 直近で {module_id} を見事突破。論理構成が非常に素晴らしいです。\n要約: {growth_report}",
            "overall_action_plan": action_plan,
        }
    )


def extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    text = ""
    for page in reader.pages:
        text += (page.extract_text() or "") + "\n"
    return text.strip()


def generate_module_from_pdf(pdf_text: str, module_number: int) -> Optional[dict]:
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
    "knowledge_level": (1-5の整数、この章の難易度に応じた知識レベルの合格基準),
    "thinking_level": (1-5の整数),
    "application_level": (1-5の整数)
  }}
}}
"""
    response = call_gemini(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.3),
    )
    try:
        parsed = json.loads(response.text)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=502, detail="AIが有効なJSON形式で応答しませんでした。もう一度試してください。")

    parsed["module_id"] = f"mod_{module_number:02d}"
    parsed["pdf_text"] = pdf_text[:8000]
    return parsed


# ==========================================
# ページ (HTML)
# ==========================================
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request=request, 
        name="index.html"
    )


@app.get("/class/{class_id}", response_class=HTMLResponse)
def class_select_page(request: Request, class_id: str):
    get_class_or_404(class_id)  # 存在確認
    return templates.TemplateResponse(
        request=request,
        name="class_select.html",
        context={"class_id": class_id}
    )


@app.get("/class/{class_id}/student", response_class=HTMLResponse)
def student_page(request: Request, class_id: str):
    get_class_or_404(class_id)
    return templates.TemplateResponse(
        request=request,
        name="student.html",
        context={"class_id": class_id}
    )


@app.get("/class/{class_id}/professor", response_class=HTMLResponse)
def professor_page(request: Request, class_id: str):
    get_class_or_404(class_id)
    return templates.TemplateResponse(
        request=request,
        name="professor.html",
        context={"class_id": class_id}
    )


# ==========================================
# API: クラス
# ==========================================
@app.get("/api/classes")
def api_list_classes():
    docs = db.collection("classes").stream()
    return [{"class_id": d.id, "class_name": d.to_dict().get("class_name", d.id)} for d in docs]


@app.post("/api/classes")
def api_create_class(class_name: str = Form(...)):
    if not class_name.strip():
        raise HTTPException(status_code=400, detail="授業名を入力してください")
    new_id = f"class_{uuid.uuid4().hex[:8]}"
    get_class_ref(new_id).set(
        {"class_name": class_name.strip(), "teacher_id": "teacher_999", "roster": [], "modules": []}
    )
    return {"class_id": new_id}


@app.get("/api/classes/{class_id}")
def api_get_class(class_id: str):
    data = get_class_or_404(class_id)
    data["class_id"] = class_id
    return data


# ==========================================
# API: 生徒 (roster)
# ==========================================
@app.post("/api/classes/{class_id}/students")
def api_add_student(class_id: str, display_name: str = Form(...)):
    if not display_name.strip():
        raise HTTPException(status_code=400, detail="生徒名を入力してください")
    class_data = get_class_or_404(class_id)
    roster = class_data.get("roster", [])
    new_sid = f"student_{uuid.uuid4().hex[:6]}"
    roster.append({"student_id": new_sid, "display_name": display_name.strip()})
    get_class_ref(class_id).update({"roster": roster})
    return {"student_id": new_sid, "display_name": display_name.strip()}


@app.delete("/api/classes/{class_id}/students/{student_id}")
def api_delete_student(class_id: str, student_id: str):
    class_data = get_class_or_404(class_id)
    roster = [s for s in class_data.get("roster", []) if s["student_id"] != student_id]
    get_class_ref(class_id).update({"roster": roster})
    get_enrollment_ref(class_id, student_id).delete()
    return {"deleted": student_id}


# ==========================================
# API: 章 (modules)
# ==========================================
@app.delete("/api/classes/{class_id}/modules/{module_id}")
def api_delete_module(class_id: str, module_id: str):
    class_data = get_class_or_404(class_id)
    modules = [m for m in class_data.get("modules", []) if m["module_id"] != module_id]
    get_class_ref(class_id).update({"modules": modules})
    return {"deleted": module_id}


@app.post("/api/classes/{class_id}/modules/from-pdf")
def api_create_module_from_pdf(class_id: str, file: UploadFile = File(...)):
    class_data = get_class_or_404(class_id)
    modules = class_data.get("modules", [])

    file_bytes = file.file.read()
    pdf_text = extract_pdf_text(file_bytes)
    if len(pdf_text) < 50:
        raise HTTPException(
            status_code=400,
            detail="PDFからテキストを抽出できませんでした。画像だけのPDFには対応していません。",
        )

    existing_numbers = [int(m["module_id"].split("_")[1]) for m in modules] or [0]
    next_number = max(existing_numbers) + 1
    new_module = generate_module_from_pdf(pdf_text, next_number)

    modules.append(new_module)
    get_class_ref(class_id).update({"modules": modules})
    return new_module


# ==========================================
# API: 履修 (enrollment) と対話
# ==========================================
@app.get("/api/classes/{class_id}/students/{student_id}/enrollment")
def api_get_enrollment(class_id: str, student_id: str):
    class_data = get_class_or_404(class_id)
    modules = class_data.get("modules", [])
    return ensure_enrollment(class_id, student_id, modules)


@app.post("/api/classes/{class_id}/students/{student_id}/reset")
def api_reset_enrollment(class_id: str, student_id: str):
    get_enrollment_ref(class_id, student_id).delete()
    return {"reset": True}


@app.post("/api/chat")
def api_chat(
    class_id: str = Form(...),
    student_id: str = Form(...),
    module_id: str = Form(...),
    message: str = Form(...),
):
    class_data = get_class_or_404(class_id)
    modules = class_data.get("modules", [])
    module_info = next((m for m in modules if m["module_id"] == module_id), None)
    if not module_info:
        raise HTTPException(status_code=404, detail="章が見つかりません")

    enrollment = ensure_enrollment(class_id, student_id, modules)
    mod_progress = enrollment.get("modules", {}).get(module_id, {})
    chat_history = mod_progress.get("chat_history", [])

    chat_history.append({"role": "user", "content": message})

    system_instruction = f"""
あなたは大学のAI副担任です。絶対に答えを教えてはいけません。
スライドの内容をヒントとして部分的に提示し、学生に考えさせ、自分の言葉で説明させる
「ソクラテス式」の問いかけを徹底してください。
学生が十分に本質を理解したと判断したら、必ず update_student_status を呼び出しパラメータを更新してください。
1回のやり取りだけで即断せず、複数回のやり取りを踏まえて評価してください。

【講義スライドの内容】
{module_info.get('pdf_text')}
"""

    response = call_gemini(
        model=GEMINI_MODEL,
        contents=message,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[update_student_status],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=0.7,
        ),
    )

    ai_reply = "理解度を測定し、レベルに反映しました。"
    is_passed_now = False

    if response.function_calls:
        for function_call in response.function_calls:
            if function_call.name == "update_student_status":
                args = function_call.args
                k = int(args.get("knowledge", 1))
                t = int(args.get("thinking", 1))
                a = int(args.get("application", 1))

                result_msg = _apply_status_update(class_id, student_id, module_id, k, t, a)

                criteria = module_info.get("passing_criteria", DEFAULT_CRITERIA)
                if k >= criteria["knowledge_level"] and t >= criteria["thinking_level"] and a >= criteria["application_level"]:
                    _generate_growth_report(class_id, student_id, module_id, chat_history)
                    is_passed_now = True

                followup = call_gemini(
                    model=GEMINI_MODEL,
                    contents=[
                        types.Content(role="user", parts=[types.Part.from_text(text=message)]),
                        types.Content(role="model", parts=[types.Part.from_function_call(function_call=function_call)]),
                        types.Content(
                            role="user",
                            parts=[types.Part.from_function_response(name="update_student_status", response={"result": result_msg})],
                        ),
                    ],
                    config=types.GenerateContentConfig(system_instruction=system_instruction),
                )
                if followup.text:
                    ai_reply = followup.text
    elif response.text:
        ai_reply = response.text

    chat_history.append({"role": "assistant", "content": ai_reply})
    get_enrollment_ref(class_id, student_id).update({f"modules.{module_id}.chat_history": chat_history})

    updated_enrollment = get_enrollment_ref(class_id, student_id).get().to_dict()
    updated_progress = updated_enrollment.get("modules", {}).get(module_id, {})

    return {
        "ai_reply": ai_reply,
        "chat_history": chat_history,
        "current_status": updated_progress.get("current_status"),
        "is_passed": updated_progress.get("is_passed", False),
        "is_passed_now": is_passed_now,
        "growth_report": updated_progress.get("growth_report"),
        "action_plan": updated_progress.get("action_plan"),
    }


# ==========================================
# API: 教授用カルテ表示
# ==========================================
@app.get("/api/classes/{class_id}/professor-view")
def api_professor_view(class_id: str):
    class_data = get_class_or_404(class_id)
    roster = class_data.get("roster", [])
    modules = class_data.get("modules", [])

    students = []
    for s in roster:
        doc = get_enrollment_ref(class_id, s["student_id"]).get()
        enrollment = doc.to_dict() if doc.exists else {}
        students.append(
            {
                "student_id": s["student_id"],
                "display_name": s["display_name"],
                "enrollment": enrollment,
            }
        )

    return {"modules": modules, "students": students}


@app.get("/healthz")
def healthz():
    return JSONResponse({"status": "ok"})

