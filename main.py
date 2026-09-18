from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai
from google.genai import types
from twilio.twiml.messaging_response import MessagingResponse

import os
import time
import httpx

# --------------------------------------------------
# ENVIRONMENT
# --------------------------------------------------

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")

client = genai.Client(api_key=GEMINI_API_KEY)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "message": "Server is running!"
    }


# --------------------------------------------------
# WEB CHATBOT
# --------------------------------------------------

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
            types.Content(
                role=item.role,
                parts=[
                    types.Part.from_text(text=item.text)
                ]
            )
        )

    contents.append(
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=request.message)
            ]
        )
    )

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=contents
    )

    return {
        "reply": response.text
    }


# --------------------------------------------------
# OLD TWILIO WHATSAPP ENDPOINT
# --------------------------------------------------

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

            print(
                f"TWILIO WHATSAPP ERROR "
                f"(attempt {attempt + 1}): {e}"
            )

            if attempt < max_retries - 1:
                time.sleep(2)

    if reply_text is None:
        reply_text = (
            "Sorry, I'm having trouble right now. "
            "Please try again in a moment."
        )

    twiml.message(reply_text)

    return Response(
        content=str(twiml),
        media_type="application/xml"
    )


# --------------------------------------------------
# META WEBHOOK VERIFICATION
# --------------------------------------------------

@app.get("/webhook")
async def verify_webhook(request: Request):

    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if (
        mode == "subscribe"
        and token == WHATSAPP_VERIFY_TOKEN
    ):

        print("META WEBHOOK VERIFIED")

        return Response(
            content=challenge,
            media_type="text/plain"
        )

    return Response(
        content="Verification failed",
        status_code=403
    )


# --------------------------------------------------
# SEND META WHATSAPP MESSAGE
# --------------------------------------------------

async def send_meta_whatsapp_message(
    phone_number_id: str,
    recipient: str,
    message: str
):

    if not WHATSAPP_ACCESS_TOKEN:
        print("ERROR: WHATSAPP_ACCESS_TOKEN is missing")
        return

    url = (
        f"https://graph.facebook.com/v26.0/"
        f"{phone_number_id}/messages"
    )

    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": message
        }
    }

    async with httpx.AsyncClient(timeout=30.0) as http_client:

        response = await http_client.post(
            url,
            headers=headers,
            json=payload
        )

        print(
            "META SEND RESPONSE:",
            response.status_code,
            response.text
        )

        response.raise_for_status()


# --------------------------------------------------
# META WHATSAPP WEBHOOK
# --------------------------------------------------

@app.post("/webhook")
async def receive_webhook(request: Request):

    try:

        data = await request.json()

        print("META WHATSAPP WEBHOOK:")
        print(data)

        # ------------------------------------------
        # Extract webhook data
        # ------------------------------------------

        entry = data.get("entry", [])

        if not entry:
            return {"status": "ok"}

        changes = entry[0].get("changes", [])

        if not changes:
            return {"status": "ok"}

        value = changes[0].get("value", {})

        # Ignore delivery/read/status notifications
        messages = value.get("messages")

        if not messages:
            return {"status": "ok"}

        message = messages[0]

        # Only process text messages for now
        if message.get("type") != "text":
            print(
                "IGNORED MESSAGE TYPE:",
                message.get("type")
            )

            return {"status": "ok"}

        sender = message.get("from")

        incoming_text = (
            message
            .get("text", {})
            .get("body", "")
            .strip()
        )

        metadata = value.get("metadata", {})

        phone_number_id = metadata.get(
            "phone_number_id"
        )

        if not sender or not incoming_text or not phone_number_id:

            print("Missing required WhatsApp message data")

            return {"status": "ok"}

        print("FROM:", sender)
        print("MESSAGE:", incoming_text)

        # ------------------------------------------
        # Generate Gemini response
        # ------------------------------------------

        reply_text = None

        max_retries = 2

        for attempt in range(max_retries):

            try:

                gemini_response = (
                    client.models.generate_content(
                        model="gemini-3.6-flash",
                        contents=incoming_text
                    )
                )

                reply_text = gemini_response.text

                break

            except Exception as e:

                print(
                    f"GEMINI WHATSAPP ERROR "
                    f"(attempt {attempt + 1}): {e}"
                )

                if attempt < max_retries - 1:
                    await __import__("asyncio").sleep(2)

        if not reply_text:

            reply_text = (
                "Sorry, I'm having trouble right now. "
                "Please try again in a moment."
            )

        # WhatsApp text messages have size limits.
        reply_text = reply_text[:4000]

        print("GEMINI REPLY:", reply_text)

        # ------------------------------------------
        # Send reply through Meta Cloud API
        # ------------------------------------------

        await send_meta_whatsapp_message(
            phone_number_id=phone_number_id,
            recipient=sender,
            message=reply_text
        )

        return {"status": "ok"}

    except Exception as e:

        # Log error but acknowledge webhook so Meta
        # does not repeatedly retry the same event.
        print("META WEBHOOK ERROR:", str(e))

        return {"status": "ok"}