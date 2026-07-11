import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import firebase_admin
from firebase_admin import firestore
from google import genai
from google.genai import types

# 💡 バグ修正1: 実行場所に関わらず確実にディレクトリを見つける絶対パス化
BASE_DIR = Path(__file__).resolve().parent

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ==========================================
# 1. Firebase & Vertex AI 初期化
# ==========================================
if not firebase_admin._apps:
    firebase_admin.initialize_app()
db = firestore.client()

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "fukutan-bot")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "asia-northeast1")

ai_client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location=LOCATION
)

# ==========================================
# 2. データモデル & ツール定義
# ==========================================
class ChatRequest(BaseModel):
    message: str
    student_id: str
    module_id: str

def update_student_status(knowledge: int, thinking: int, application: int):
    """(ダミー定義) 実際はここでFirestoreの数値を書き換えます"""
    return f"ステータスを更新しました: k={knowledge}, t={thinking}, a={application}"

# ==========================================
# 3. エンドポイント
# ==========================================
@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    """💡 バグ修正2: 本物のGeminiロジックの統合"""
    
    # 実際はFirestoreから前回までの履歴とPDFテキストを引いてきます（今回は固定テキストを使用）
    pdf_text = "【講義ノート】コンテナはホストOSのカーネルを共有するため起動が非常に速い..."
    
    system_instruction = f"""
    あなたは大学のAI副担任です。絶対に答えを教えてはいけません。
    スライドの内容をヒントとして提示し、学生に考えさせ「ソクラテス式」の問いかけをしてください。
    学生が十分に理解したと判断したら、`update_student_status` を呼び出しパラメータを更新してください。
    【講義スライドの内容】: {pdf_text}
    """

    try:
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=req.message,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=[update_student_status],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                temperature=0.7,
            )
        )

        ai_reply = "理解度を測定しています..."
        new_k, new_t, new_a = 1, 1, 1 # デフォルト値

        # Function Calling が発火した場合
        if response and response.function_calls:
            for function_call in response.function_calls:
                if function_call.name == "update_student_status":
                    args = function_call.args
                    new_k = int(args.get("knowledge", 1))
                    new_t = int(args.get("thinking", 1))
                    new_a = int(args.get("application", 1))

                    result_msg = update_student_status(new_k, new_t, new_a)

                    # フォローアップの返答を生成
                    followup = ai_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[
                            types.Content(role="user", parts=[types.Part.from_text(text=req.message)]),
                            types.Content(role="model", parts=[types.Part.from_function_call(function_call=function_call)]),
                            types.Content(role="user", parts=[types.Part.from_function_response(name="update_student_status", response={"result": result_msg})])
                        ],
                        config=types.GenerateContentConfig(system_instruction=system_instruction)
                    )
                    if followup and followup.text:
                        ai_reply = followup.text
        elif response and response.text:
            ai_reply = response.text

        return JSONResponse({
            "reply": ai_reply,
            "current_status": {
                "knowledge": new_k,
                "thinking": new_t,
                "application": new_a
            }
        })

    except Exception as e:
        print(f"Vertex AI Error: {e}")
        return JSONResponse({
            "reply": "AIとの通信でエラーが発生しました。もう一度送信してください。",
            "current_status": {"knowledge": 1, "thinking": 1, "application": 1}
        }, status_code=500)