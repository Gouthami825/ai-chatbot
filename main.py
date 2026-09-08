from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai
from google.genai import types
import os

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Server is running!"}

class HistoryItem(BaseModel):
    role: str   # "user" or "model"
    text: str

class ChatRequest(BaseModel):
    message: str
    history: list[HistoryItem] = []

@app.post("/chat")
def chat(request: ChatRequest):
    contents = []
    for item in request.history:
        contents.append(
            types.Content(role=item.role, parts=[types.Part.from_text(text=item.text)])
        )
    contents.append(
        types.Content(role="user", parts=[types.Part.from_text(text=request.message)])
    )

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=contents
    )
    return {"reply": response.text}