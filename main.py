from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai
from google.genai import types
from twilio.twiml.messaging_response import MessagingResponse

import os
import time
import requests


# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")


# Gemini client
gemini_client = None

if GEMINI_API_KEY:
    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY
    )


# =========================================================
# FASTAPI APP
# =========================================================

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")
def health_check():

    return {
        "status": "ok",
        "message": "Server is running!",
        "gemini_configured": bool(GEMINI_API_KEY),
        "groq_configured": bool(GROQ_API_KEY),
        "whatsapp_configured": bool(
            WHATSAPP_ACCESS_TOKEN
            and WHATSAPP_PHONE_NUMBER_ID
        ),
    }


# =========================================================
# PRIVACY POLICY
# =========================================================

@app.get("/privacy", response_class=HTMLResponse)
def privacy_policy():

    return """
    <!DOCTYPE html>
    <html lang="en">

    <head>

        <meta charset="UTF-8">

        <meta
            name="viewport"
            content="width=device-width, initial-scale=1.0"
        >

        <title>
            Helios Chatbot - Privacy Policy
        </title>

        <style>

            body {
                font-family: Arial, sans-serif;
                max-width: 850px;
                margin: 40px auto;
                padding: 20px;
                line-height: 1.7;
                color: #222;
            }

            h1 {
                margin-bottom: 5px;
            }

            h2 {
                margin-top: 30px;
            }

        </style>

    </head>

    <body>

        <h1>
            Privacy Policy – Helios Chatbot
        </h1>

        <p>
            <strong>Last updated:</strong>
            September 21, 2026
        </p>

        <p>
            Helios Chatbot provides an AI-powered
            conversational service through WhatsApp
            and web-based interfaces.
        </p>


        <h2>Information We Process</h2>

        <p>
            When you interact with Helios Chatbot,
            we may process information such as your
            WhatsApp phone number, profile information
            made available through WhatsApp, and
            messages you send to the chatbot.
        </p>


        <h2>How We Use Information</h2>

        <p>
            We use this information to receive and
            respond to messages, operate the chatbot,
            provide customer support, and improve
            the service.
        </p>


        <h2>AI Processing</h2>

        <p>
            Messages may be processed using third-party
            AI and cloud service providers when necessary
            to generate chatbot responses and operate
            the service.
        </p>


        <h2>Data Sharing</h2>

        <p>
            We do not sell personal information.
            Information may be processed by service
            providers necessary for operating the
            chatbot, including messaging, hosting,
            and AI infrastructure providers.
        </p>


        <h2>Data Retention</h2>

        <p>
            Information is retained only for as long
            as reasonably necessary to provide and
            maintain the service or comply with
            applicable legal requirements.
        </p>


        <h2>Your Choices</h2>

        <p>
            You may stop interacting with the chatbot
            at any time. You may also contact us
            regarding questions about your information
            or requests concerning your data.
        </p>


        <h2>Contact</h2>

        <p>
            For privacy-related questions or requests:
            <br><br>
            Email: g1592781@gmail.com
        </p>


        <h2>Changes to This Policy</h2>

        <p>
            This Privacy Policy may be updated
            periodically. Updates will be published
            on this page with a revised effective date.
        </p>

    </body>

    </html>
    """


# =========================================================
# GROQ RESPONSE
# =========================================================

def generate_groq_reply(message):

    if not GROQ_API_KEY:

        print("GROQ_API_KEY IS MISSING")

        return None


    url = (
        "https://api.groq.com/openai/v1/"
        "chat/completions"
    )


    headers = {

        "Authorization":
            f"Bearer {GROQ_API_KEY}",

        "Content-Type":
            "application/json",
    }


    payload = {

        "model":
            "openai/gpt-oss-120b",

        "messages": [

            {
    "role": "system",
    "content": (
        "You are Helios AI Assistant, the AI chatbot for Helios. "
        "Never claim that you were created by Google, Groq, Meta, "
        "OpenAI, or any other AI provider. "
        "If asked who you are, say: "
        "'I am Helios AI Assistant.' "
        "Be helpful, concise, friendly, and professional."
    ),
},

            {
                "role": "user",
                "content": message,
            },
        ],

        "temperature": 0.7,

        "max_tokens": 500,
    }


    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30,
        )


        print(
            "GROQ STATUS:",
            response.status_code
        )


        if response.status_code == 200:

            data = response.json()

            reply = (
                data
                .get("choices", [{}])[0]
                .get("message", {})
                .get("content")
            )


            if reply:

                print(
                    "GROQ RESPONSE SUCCESS"
                )

                return reply.strip()


        print(
            "GROQ API ERROR:",
            response.text
        )


    except Exception as e:

        print(
            "GROQ REQUEST ERROR:",
            e
        )


    return None


# =========================================================
# GEMINI RESPONSE
# =========================================================

def generate_gemini_reply(message):

    if not gemini_client:

        print("GEMINI_API_KEY IS MISSING")

        return None


    try:

        response = (
            gemini_client.models.generate_content(
                model="gemini-3.6-flash",
                contents=message,
            )
        )


        if response.text:

            print(
                "GEMINI RESPONSE SUCCESS"
            )

            return response.text.strip()


    except Exception as e:

        print(
            "GEMINI ERROR:",
            e
        )


    return None


# =========================================================
# MAIN AI ROUTER
#
# 1. Try Gemini
# 2. If Gemini fails/quota exceeded -> Groq
# =========================================================

def generate_ai_reply(message):

    # -----------------------------------------
    # TRY GEMINI FIRST
    # -----------------------------------------

    print("TRYING GEMINI...")


    gemini_reply = generate_gemini_reply(
        message
    )


    if gemini_reply:

        print("AI PROVIDER: GEMINI")

        return gemini_reply


    # -----------------------------------------
    # GEMINI FAILED -> GROQ FALLBACK
    # -----------------------------------------

    print(
        "GEMINI FAILED - TRYING GROQ..."
    )


    groq_reply = generate_groq_reply(
        message
    )


    if groq_reply:

        print("AI PROVIDER: GROQ")

        return groq_reply


    # -----------------------------------------
    # BOTH FAILED
    # -----------------------------------------

    print(
        "ALL AI PROVIDERS FAILED"
    )


    return (
        "Sorry, I'm having trouble right now. "
        "Please try again in a moment."
    )


# =========================================================
# WEB CHATBOT
# =========================================================

class HistoryItem(BaseModel):

    role: str
    text: str


class ChatRequest(BaseModel):

    message: str
    history: list[HistoryItem] = []


@app.post("/chat")
def chat(request: ChatRequest):

    # For now the common AI router is used.
    # If Gemini quota is exhausted, Groq is automatic.

    reply = generate_ai_reply(
        request.message
    )


    return {
        "reply": reply
    }


# =========================================================
# OLD TWILIO WHATSAPP ENDPOINT
# =========================================================

@app.post("/whatsapp")
async def whatsapp_reply(request: Request):

    form = await request.form()

    incoming_msg = form.get(
        "Body",
        ""
    ).strip()


    twiml = MessagingResponse()


    if not incoming_msg:

        twiml.message(
            "Please send a text message."
        )

        return Response(
            content=str(twiml),
            media_type="application/xml",
        )


    reply_text = generate_ai_reply(
        incoming_msg
    )


    twiml.message(
        reply_text
    )


    return Response(
        content=str(twiml),
        media_type="application/xml",
    )


# =========================================================
# META WHATSAPP WEBHOOK VERIFICATION
# =========================================================

@app.get("/webhook")
async def verify_webhook(request: Request):

    mode = request.query_params.get(
        "hub.mode"
    )

    token = request.query_params.get(
        "hub.verify_token"
    )

    challenge = request.query_params.get(
        "hub.challenge"
    )


    if (
        mode == "subscribe"
        and token == WHATSAPP_VERIFY_TOKEN
    ):

        print(
            "META WEBHOOK VERIFIED"
        )

        return Response(
            content=challenge,
            media_type="text/plain",
        )


    print(
        "META WEBHOOK VERIFICATION FAILED"
    )


    return Response(
        content="Verification failed",
        status_code=403,
    )


# =========================================================
# SEND META WHATSAPP MESSAGE
# =========================================================

def send_whatsapp_message(
    to_number,
    message
):

    if not WHATSAPP_ACCESS_TOKEN:

        print(
            "ERROR: WHATSAPP_ACCESS_TOKEN "
            "is missing"
        )

        return False


    if not WHATSAPP_PHONE_NUMBER_ID:

        print(
            "ERROR: WHATSAPP_PHONE_NUMBER_ID "
            "is missing"
        )

        return False


    url = (
        "https://graph.facebook.com/v26.0/"
        f"{WHATSAPP_PHONE_NUMBER_ID}/messages"
    )


    headers = {

        "Authorization":
            f"Bearer {WHATSAPP_ACCESS_TOKEN}",

        "Content-Type":
            "application/json",
    }


    payload = {

        "messaging_product":
            "whatsapp",

        "recipient_type":
            "individual",

        "to":
            to_number,

        "type":
            "text",

        "text": {

            "preview_url":
                False,

            "body":
                message,
        },
    }


    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30,
        )


        print(
            "META SEND STATUS:",
            response.status_code
        )


        print(
            "META SEND RESPONSE:",
            response.text
        )


        if response.status_code in [
            200,
            201,
        ]:

            print(
                "WHATSAPP REPLY "
                "SENT SUCCESSFULLY"
            )

            return True


        print(
            "WHATSAPP SEND FAILED"
        )

        return False


    except Exception as e:

        print(
            "WHATSAPP SEND ERROR:",
            e
        )

        return False


# =========================================================
# META WHATSAPP INCOMING WEBHOOK
# =========================================================

@app.post("/webhook")
async def receive_webhook(request: Request):

    try:

        data = await request.json()


        print(
            "META WHATSAPP WEBHOOK:"
        )

        print(data)


        entries = data.get(
            "entry",
            []
        )


        for entry in entries:

            changes = entry.get(
                "changes",
                []
            )


            for change in changes:

                value = change.get(
                    "value",
                    {}
                )


                # ---------------------------------
                # IGNORE DELIVERY / READ STATUS
                # ---------------------------------

                messages = value.get(
                    "messages"
                )


                if not messages:

                    continue


                for message in messages:

                    sender = message.get(
                        "from"
                    )

                    message_type = message.get(
                        "type"
                    )


                    if not sender:

                        continue


                    # =============================
                    # TEXT MESSAGE
                    # =============================

                    if message_type == "text":

                        text_data = message.get(
                            "text",
                            {}
                        )


                        incoming_text = (
                            text_data
                            .get(
                                "body",
                                ""
                            )
                            .strip()
                        )


                        if not incoming_text:

                            continue


                        print(
                            "FROM:",
                            sender
                        )


                        print(
                            "MESSAGE:",
                            incoming_text
                        )


                        # -------------------------
                        # GENERATE AI RESPONSE
                        # -------------------------

                        ai_reply = (
                            generate_ai_reply(
                                incoming_text
                            )
                        )


                        print(
                            "AI REPLY:",
                            ai_reply
                        )


                        # -------------------------
                        # SEND WHATSAPP RESPONSE
                        # -------------------------

                        send_whatsapp_message(
                            sender,
                            ai_reply
                        )


                    else:

                        print(
                            "IGNORED MESSAGE TYPE:",
                            message_type
                        )


        # Meta expects HTTP 200

        return {
            "status": "ok"
        }


    except Exception as e:

        print(
            "META WEBHOOK ERROR:",
            e
        )


        # Return 200 so Meta does not keep
        # retrying malformed webhook events.

        return {
            "status": "ok"
        }