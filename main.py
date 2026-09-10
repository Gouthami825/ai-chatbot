from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai
from google.genai import types
from twilio.twiml.messaging_response import MessagingResponse
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
    role: str
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


import time

@app.post("/whatsapp")
async def whatsapp_reply(request: Request):
    form = await request.form()
    incoming_msg = form.get("Body", "")

    twiml = MessagingResponse()
    max_retries = 2
    reply_text = None

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=incoming_msg
            )
            reply_text = response.text
            break
        except Exception as e:
            print(f"WHATSAPP ERROR (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)

    if reply_text is None:
        reply_text = "Sorry, I'm having trouble right now. Please try again in a moment."

    twiml.message(reply_text)
    return Response(content=str(twiml), media_type="application/xml")