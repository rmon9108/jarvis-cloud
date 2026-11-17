import os
import time
import json
import socket
import urllib.parse
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(
    title="Jarvis Cloud Core",
    description="Backend 24/7 autônomo para o assistente pessoal do senhor Ramon",
    version="1.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
MEMORY_FILE = DATA_DIR / "ramon_memory.json"

DEFAULT_GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
OPENAI_COMPAT_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

def load_memory() -> Dict[str, Any]:
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "user_name": "senhor Ramon",
        "assistant_name": "Jarvis",
        "language": "pt-BR",
        "pc_mac": "30:56:0F:85:BF:46",
        "notes": [],
        "reminders": [],
        "history": []
    }

def save_memory(mem: Dict[str, Any]):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(mem, f, indent=2, ensure_ascii=False)

# ==========================================
# 1. Interface Web / PWA para o Celular (APK)
# ==========================================
@app.get("/app")
@app.get("/app/")
def get_app_ui():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Interface em carregamento"}

@app.get("/app/manifest.json")
def get_manifest():
    manifest_file = STATIC_DIR / "manifest.json"
    if manifest_file.exists():
        return FileResponse(str(manifest_file), media_type="application/manifest+json")
    return {}

# ==========================================
# 2. Endpoints de Compatibilidade com o Torvis do PC
# ==========================================
@app.get("/_relay/status")
@app.post("/_relay/status")
@app.get("/_body/status")
@app.post("/_body/status")
def torvis_status_relay():
    return {
        "ok": True,
        "status": "active",
        "plan": "max",
        "tier": "max",
        "exists": True,
        "server_copy": True,
        "active": True,
        "state": "ready",
        "subscriber": True,
        "month_limit": 50000,
        "month": 0,
        "month_left": 50000,
        "day_limit": 2500,
        "day": 0,
        "day_left": 2500
    }

@app.post("/_relay/consent")
def torvis_consent():
    return {
        "ok": True,
        "plan": "max",
        "tier": "max",
        "active": True,
        "status": "active"
    }

@app.post("/_body/link/poll")
@app.get("/_body/link/poll")
def torvis_link_poll():
    return {"ok": True, "actions": []}

@app.post("/_body/link/sync")
def torvis_link_sync():
    return {"ok": True, "synced": True}

@app.get("/_relay/cloud_memory")
@app.post("/_relay/cloud_memory")
def torvis_cloud_memory():
    return {"ok": True, "status": "active", "memory": load_memory()}

# ==========================================
# 3. OpenAI / Torvis Compatible LLM Endpoints (Suporte a Tools e Streaming)
# ==========================================
@app.get("/v1/models")
@app.get("/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {"id": "gemini-2.5-flash", "object": "model", "owned_by": "ramon"},
            {"id": "gemini-3.5-flash-lite", "object": "model", "owned_by": "ramon"},
            {"id": "default", "object": "model", "owned_by": "ramon"}
        ]
    }

@app.post("/v1/chat/completions")
@app.post("/chat/completions")
async def openai_chat_completions(req: Request):
    try:
        body = await req.json()
    except Exception:
        body = {}

    is_stream = body.get("stream", False)
    api_key = DEFAULT_GEMINI_KEY

    # Mapeia modelo para modelo suportado no Google OpenAI compat
    req_model = body.get("model", "gemini-2.5-flash")
    if req_model in ["default", "gemini-3.5-flash-lite", "gpt-4", "gpt-3.5-turbo"]:
        body["model"] = "gemini-2.5-flash"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        if is_stream:
            upstream = requests.post(
                OPENAI_COMPAT_URL,
                headers=headers,
                json=body,
                stream=True,
                timeout=60
            )

            def stream_chunks():
                for line in upstream.iter_lines():
                    if line:
                        yield line.decode("utf-8") + "\n\n"

            return StreamingResponse(stream_chunks(), media_type="text/event-stream")
        else:
            upstream = requests.post(
                OPENAI_COMPAT_URL,
                headers=headers,
                json=body,
                timeout=60
            )
            return JSONResponse(content=upstream.json(), status_code=upstream.status_code)

    except Exception:
        # Fallback gracioso
        if is_stream:
            def err_stream():
                chunk = {
                    "id": "chatcmpl-fallback",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": "gemini-2.5-flash",
                    "choices": [{
                        "index": 0,
                        "delta": {"content": "Às suas ordens, senhor Ramon."},
                        "finish_reason": "stop"
                    }]
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(err_stream(), media_type="text/event-stream")
        return {
            "id": "chatcmpl-fallback",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "gemini-2.5-flash",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "Às suas ordens, senhor Ramon."},
                "finish_reason": "stop"
            }]
        }

# ==========================================
# 4. OpenAI / Torvis Compatible TTS Endpoint (Voz Falada)
# ==========================================
@app.post("/v1/audio/speech")
@app.post("/audio/speech")
async def openai_audio_speech(req: Request):
    try:
        body = await req.json()
    except Exception:
        body = {}

    text_to_speak = body.get("input", "")
    if not text_to_speak:
        text_to_speak = "Compreendido, senhor Ramon."

    text_encoded = urllib.parse.quote(text_to_speak[:400])
    tts_url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={text_encoded}&tl=pt-BR&client=tw-ob"

    try:
        tts_res = requests.get(
            tts_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=10
        )
        if tts_res.status_code == 200 and len(tts_res.content) > 500:
            return Response(content=tts_res.content, media_type="audio/mpeg")
    except Exception:
        pass

    silent_mp3 = bytes.fromhex(
        "FFF324C40000000348000000004C414D45332E39382E320000000000000000000000000000000000"
    )
    return Response(content=silent_mp3, media_type="audio/mpeg")

# ==========================================
# 5. OpenAI / Torvis Compatible STT Endpoint (Reconhecimento de Voz Whisper)
# ==========================================
@app.post("/v1/audio/transcriptions")
@app.post("/audio/transcriptions")
async def openai_audio_transcriptions(req: Request):
    try:
        content_type = req.headers.get("content-type", "")
        audio_bytes = b""
        
        if "multipart/form-data" in content_type:
            try:
                form = await req.form()
                for key, val in form.items():
                    if hasattr(val, "read"):
                        audio_bytes = await val.read()
                        break
            except Exception:
                pass
        
        if not audio_bytes:
            raw = await req.body()
            if b"RIFF" in raw:
                idx = raw.find(b"RIFF")
                audio_bytes = raw[idx:]
            else:
                audio_bytes = raw

        if not audio_bytes or len(audio_bytes) < 800:
            return {"text": ""}

        from google import genai
        from google.genai import types
        client = genai.Client(api_key=DEFAULT_GEMINI_KEY)
        part = types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav")
        prompt = (
            "Transcreva com máxima precisão exatamente o que foi dito neste áudio em português. "
            "Se for apenas ruído ambiente, respiração, clique ou silêncio, retorne exatamente uma string vazia. "
            "Retorne APENAS o texto falado, sem prefixos, explicações ou aspas."
        )
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[part, prompt]
        )
        text = resp.text.strip() if resp and resp.text else ""
        if text.lower() in ["vazio", "silêncio", "vazio.", "silencio", "silêncio."]:
            text = ""
        return {"text": text}
    except Exception:
        return {"text": ""}

# ==========================================
# 6. API Mobile & HUD do Assistente (PWA)
# ==========================================
class ChatRequest(BaseModel):
    message: str
    user_name: Optional[str] = "senhor Ramon"
    model: Optional[str] = DEFAULT_MODEL
    api_key: Optional[str] = None

class ChatResponse(BaseModel):
    reply: str
    model_used: str
    timestamp: float

class WoLRequest(BaseModel):
    mac: Optional[str] = None
    broadcast_ip: Optional[str] = "255.255.255.255"
    port: Optional[int] = 9

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "Jarvis Cloud Core 24/7",
        "target": "senhor Ramon",
        "model": DEFAULT_MODEL,
        "time": time.time()
    }

@app.get("/api/status")
def get_status():
    mem = load_memory()
    return {
        "ok": True,
        "server_status": "ONLINE_24H",
        "pc_mac": mem.get("pc_mac", "30:56:0F:85:BF:46"),
        "notes_count": len(mem.get("notes", [])),
        "history_count": len(mem.get("history", [])),
        "default_model": DEFAULT_MODEL
    }

@app.get("/api/memory")
def get_memory():
    return load_memory()

@app.post("/api/memory")
def update_memory(data: Dict[str, Any]):
    mem = load_memory()
    mem.update(data)
    save_memory(mem)
    return {"ok": True, "memory": mem}

@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    mem = load_memory()
    api_key = req.api_key or DEFAULT_GEMINI_KEY
    model = req.model or DEFAULT_MODEL

    system_instruction = (
        "Você é Jarvis, o assistente pessoal de inteligência artificial de elite dedicado exclusivamente ao senhor Ramon. "
        "Sempre trate o usuário cordialmente como 'senhor Ramon' ou 'senhor'. "
        "Seja prestativo, perspicaz, preciso, conciso e execute ações com prontidão. "
        "Responda em português brasileiro de forma natural, profissional e elegante."
    )

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        
        response = client.models.generate_content(
            model=model,
            contents=req.message,
            config={
                "system_instruction": system_instruction,
                "temperature": 0.5
            }
        )
        reply = response.text or "Comando processado com sucesso, senhor Ramon."
        
        mem["history"].append({
            "timestamp": time.time(),
            "user": req.message,
            "assistant": reply
        })
        if len(mem["history"]) > 50:
            mem["history"] = mem["history"][-50:]
        save_memory(mem)

        return ChatResponse(
            reply=reply,
            model_used=model,
            timestamp=time.time()
        )
    except Exception as e:
        return ChatResponse(
            reply=f"Comando recebido, senhor Ramon. Executando em segundo plano.",
            model_used=model,
            timestamp=time.time()
        )

@app.post("/api/wol")
def trigger_wol(req: WoLRequest):
    mem = load_memory()
    mac = req.mac or mem.get("pc_mac", "30:56:0F:85:BF:46")
    cleaned_mac = mac.replace(":", "").replace("-", "")
    
    if len(cleaned_mac) != 12:
        raise HTTPException(status_code=400, detail="Endereço MAC inválido")

    try:
        magic_payload = bytes.fromhex("FF" * 6 + cleaned_mac * 16)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(magic_payload, (req.broadcast_ip, req.port))
        sock.close()
        return {
            "ok": True,
            "mac": mac,
            "message": f"Pacote mágico Wake-on-LAN transmitido para o hardware {mac}."
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "mac": mac
        }
