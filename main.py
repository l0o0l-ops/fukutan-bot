import os
import json
import io
from pathlib import Path
from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import firebase_admin
from firebase_admin import firestore
from google import genai
from google.genai import types
from pypdf import PdfReader

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ==========================================
# 1. 接続初期化
# ==========================================
if not firebase_admin._apps:
    firebase_admin.initialize_app()
db = firestore.client()

ai_client = genai.Client(
    vertexai=True,
    project=os.environ.get("GOOGLE_CLOUD_PROJECT", "fukutan-bot"),
    location=os.environ.get("GOOGLE_CLOUD_LOCATION", "asia-northeast1")
)

# ==========================================
# 2. UI ルーティング
# ==========================================
@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/student", response_class=HTMLResponse)
async def get_student(request: Request):
    return templates.TemplateResponse(request=request, name="student.html")

@app.get("/professor", response_class=HTMLResponse)
async def get_professor(request: Request):
    return templates.TemplateResponse(request=request, name="professor.html")

@app.get("/settings", response_class=HTMLResponse)
async def get_settings(request: Request):
    return templates.TemplateResponse(request=request, name="settings.html")

# ==========================================
# 3. コア API エンドポイント (本番接続)
# ==========================================

@app.get("/api/classes")
async def api_get_classes():
    docs = db.collection("classes").stream()
    classes = []
    for doc in docs:
        d = doc.to_dict()
        classes.append({
            "id": doc.id,
            "class_name": d.get("name", "無題の授業"),
            "studentCount": len(d.get("roster", [])),
            "currentModule": d.get("modules", [{}])[0].get("title", "未設定") if d.get("modules") else "未設定"
        })
    return JSONResponse({"classes": classes})

@app.post("/api/classes")
async def api_create_class(class_name: str = Form(...)):
    doc_ref = db.collection("classes").document()
    class_data = {
        "name": class_name,
        "modules": [],
        "roster": []
    }
    doc_ref.set(class_data)
    return JSONResponse({"id": doc_ref.id, "class_name": class_name, "studentCount": 0, "currentModule": "未設定"})

@app.get("/api/classes/{class_id}")
async def api_get_class(class_id: str):
    doc = db.collection("classes").document(class_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="授業が見つかりません")
    d = doc.to_dict()
    return JSONResponse({
        "id": doc.id,
        "class_name": d.get("name"),
        "modules": d.get("modules", []),
        "roster": d.get("roster", [])
    })

@app.delete("/api/classes/{class_id}")
async def api_delete_class(class_id: str):
    db.collection("classes").document(class_id).delete()
    return JSONResponse({"status": "success"})

@app.post("/api/classes/{class_id}/students")
async def api_add_student(class_id: str, display_name: str = Form(...)):
    class_ref = db.collection("classes").document(class_id)
    doc = class_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Class not found")
    
    student_id = f"std_{doc.id}_{len(doc.to_dict().get('roster', [])) + 1}"
    new_student = {"student_id": student_id, "display_name": display_name}
    
    class_ref.update({"roster": firestore.ArrayUnion([new_student])})
    
    # 履修の初期構造を作成
    db.collection("enrollments").document(f"{class_id}_{student_id}").set({
        "class_id": class_id,
        "student_id": student_id,
        "overall_report": "対話が始まると分析が生成されます。",
        "overall_action_plan": "",
        "modules": {}
    })
    return JSONResponse(new_student)

@app.delete("/api/classes/{class_id}/students/{student_id}")
async def api_delete_student(class_id: str, student_id: str):
    class_ref = db.collection("classes").document(class_id)
    doc = class_ref.get()
    if doc.exists:
        roster = doc.to_dict().get("roster", [])
        updated_roster = [s for s in roster if s["student_id"] != student_id]
        class_ref.update({"roster": updated_roster})
    db.collection("enrollments").document(f"{class_id}_{student_id}").delete()
    return JSONResponse({"status": "success"})

@app.get("/api/classes/{class_id}/students/{student_id}/enrollment")
async def api_get_enrollment(class_id: str, student_id: str):
    doc = db.collection("enrollments").document(f"{class_id}_{student_id}").get()
    if not doc.exists:
        return JSONResponse({"modules": {}})
    return JSONResponse(doc.to_dict())

@app.delete("/api/classes/{class_id}/modules/{module_id}")
async def api_delete_module(class_id: str, module_id: str):
    class_ref = db.collection("classes").document(class_id)
    doc = class_ref.get()
    if doc.exists:
        modules = doc.to_dict().get("modules", [])
        updated_modules = [m for m in modules if m["module_id"] != module_id]
        class_ref.update({"modules": updated_modules})
    return JSONResponse({"status": "success"})

@app.post("/api/classes/{class_id}/modules/from-pdf")
async def api_upload_pdf(class_id: str, file: UploadFile = File(...)):
    contents = await file.read()
    reader = PdfReader(io.BytesIO(contents))
    pdf_text = "".join([page.extract_text() + "\n" for page in reader.pages])

    prompt = f"以下の講義スライドから学習モジュールを設計しJSONでのみ出力してください:\n{pdf_text[:7000]}\n" \
             f"出力形式: {{\n  \"title\": \"第X章: タイトル\",\n  \"target_goal\": \"目標文\",\n" \
             f"  \"passing_criteria\": {{\n    \"knowledge_level\": 4, \"thinking_level\": 4, \"application_level\": 3\n  }}\n}}"
    
    response = ai_client.models.generate_content(
        model='gemini-2.5-flash', contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.3)
    )
    
    module_data = json.loads(response.text)
    module_data["module_id"] = f"mod_{int(firestore.SERVER_TIMESTAMP.timestamp() if hasattr(firestore.SERVER_TIMESTAMP, 'timestamp') else 123456789)}"
    module_data["pdf_text"] = pdf_text
    
    db.collection("classes").document(class_id).update({"modules": firestore.ArrayUnion([module_data])})
    return JSONResponse(module_data)

# ==========================================
# 4. 🔥 ソクラテス対話 & Function Calling エンドポイント
# ==========================================
def update_student_status(knowledge: int, thinking: int, application: int):
    """
    学生の理解度を評価し、ステータスを更新するツールです。
    各パラメータは必ず【1から5の整数】で評価してください。
    - knowledge (知識): 専門用語や事実の正確な記憶・理解度（例: 用語を出せたら2、意味を説明できたら4）
    - thinking (思考): 論理的な説明能力、自分の言葉への置き換え（例: 丸暗記でなく筋道が通っていれば3以上）
    - application (応用): 具体例の提示、実運用でのメリット・デメリットへの言及（例: 実践的な視点があれば3以上）
    """
    return f"理解度パラメータを更新: 知識={knowledge}, 思考={thinking}, 応用={application}"

@app.post("/api/chat")
async def api_chat(class_id: str = Form(...), student_id: str = Form(...), module_id: str = Form(...), message: str = Form(...)):
    class_doc = db.collection("classes").document(class_id).get().to_dict()
    mod_info = next((m for m in class_doc.get("modules", []) if m["module_id"] == module_id), {})
    
    enroll_ref = db.collection("enrollments").document(f"{class_id}_{student_id}")
    enroll_doc = enroll_ref.get().to_dict() or {"modules": {}}
    
    mod_progress = enroll_doc.get("modules", {}).get(module_id, {
        "chat_history": [],
        "current_status": {"knowledge_level": 1, "thinking_level": 1, "application_level": 1},
        "is_passed": False
    })
    
    history = mod_progress.get("chat_history", [])
    history.append({"role": "user", "content": message})
    
    system_instruction = f"""
    あなたは大学のAI副担任です。生徒を対話に基づき、理解度を評価します。
    【重要：リアルタイム評価の実行】
    学生の発言に少しでも理解の進捗（正しいキーワードの使用、論理的な推測など）が見られた場合は、
    会話の返答を行うと同時に、必ず `update_student_status` ツールを呼び出して現在のレベルを【1〜5】で再評価してください。
    出し惜しみせず、学生の回答のレベルに合わせてこまめに数値を引き上げてください。【講義内容】: {mod_info.get('pdf_text', '')[:4000]}
    """
    
    response = ai_client.models.generate_content(
        model='gemini-2.5-flash', contents=message,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[update_student_status],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=0.7
        )
    )
    
    ai_reply = "内容を吟味しています..."
    is_passed_now = False
    
    if response and response.function_calls:
        for fc in response.function_calls:
            if fc.name == "update_student_status":
                args = fc.args
                k = int(args.get("knowledge", 1))
                t = int(args.get("thinking", 1))
                a = int(args.get("application", 1))
                
                mod_progress["current_status"] = {"knowledge_level": k, "thinking_level": t, "application_level": a}
                
                criteria = mod_info.get("passing_criteria", {"knowledge_level": 4, "thinking_level": 4, "application_level": 3})
                if k >= criteria["knowledge_level"] and t >= criteria["thinking_level"] and a >= criteria["application_level"]:
                    mod_progress["is_passed"] = True
                    is_passed_now = True
                    mod_progress["growth_report"] = "AI評価: 核心的な概念への深い理解と応用力が認められます。"
                    mod_progress["action_plan"] = "次の発展的な授業モジュールへ進んでください。"
                
                res_msg = update_student_status(k, t, a)
                followup = ai_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[
                        types.Content(role="user", parts=[types.Part.from_text(text=message)]),
                        types.Content(role="model", parts=[types.Part.from_function_call(function_call=fc)]),
                        types.Content(role="user", parts=[types.Part.from_function_response(name="update_student_status", response={"result": res_msg})])
                    ],
                    config=types.GenerateContentConfig(system_instruction=system_instruction)
                )
                if followup and followup.text:
                    ai_reply = followup.text
    elif response and response.text:
        ai_reply = response.text
        
    history.append({"role": "assistant", "content": ai_reply})
    mod_progress["chat_history"] = history
    
    enroll_doc["modules"][module_id] = mod_progress
    enroll_ref.set(enroll_doc)
    
    return JSONResponse({
        "chat_history": history,
        "current_status": mod_progress["current_status"],
        "is_passed": mod_progress["is_passed"],
        "is_passed_now": is_passed_now,
        "growth_report": mod_progress.get("growth_report", ""),
        "action_plan": mod_progress.get("action_plan", "")
    })

@app.get("/api/classes/{class_id}/professor-view")
async def api_professor_view(class_id: str):
    class_doc = db.collection("classes").document(class_id).get().to_dict() or {}
    modules = class_doc.get("modules", [])
    roster = class_doc.get("roster", [])
    
    students_data = []
    for s in roster:
        sid = s["student_id"]
        enroll_doc = db.collection("enrollments").document(f"{class_id}_{sid}").get().to_dict() or {}
        students_data.append({
            "student_id": sid,
            "display_name": s["display_name"],
            "enrollment": enroll_doc
        })
        
    return JSONResponse({"modules": modules, "students": students_data})