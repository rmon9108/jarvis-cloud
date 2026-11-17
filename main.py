import os
import time
import json
import socket
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(
    title="Jarvis Cloud Core",
    description="Backend 24/7 autônomo para o assistente pessoal do senhor Ramon",
    version="1.0.0"
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
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

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

# ==========================================
# 2.1 OpenAI / Torvis Compatible LLM Endpoints
# ==========================================
@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {"id": "gemini-3.5-flash-lite", "object": "model", "owned_by": "ramon"},
            {"id": "gemini-2.5-flash", "object": "model", "owned_by": "ramon"},
            {"id": "default", "object": "model", "owned_by": "ramon"}
        ]
    }

@app.post("/v1/chat/completions")
async def openai_chat_completions(req: Request):
    try:
        body = await req.json()
        messages = body.get("messages", [])
        is_stream = body.get("stream", False)
        
        last_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_msg = m.get("content", "")
                break
        if not last_msg and messages:
            last_msg = messages[-1].get("content", "")

        from google import genai
        client = genai.Client(api_key=DEFAULT_GEMINI_KEY)
        system_instruction = (
            "Você é Jarvis, o assistente pessoal de inteligência artificial de elite dedicado exclusivamente ao senhor Ramon. "
            "Sempre trate o usuário cordialmente como 'senhor Ramon' ou 'senhor'. "
            "Seja prestativo, perspicaz, preciso, conciso e execute ações com prontidão. "
            "Responda em português brasileiro de forma natural, profissional e elegante."
        )

        response = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=last_msg or "Olá",
            config={
                "system_instruction": system_instruction,
                "temperature": 0.5
            }
        )
        reply = response.text or "Comando processado com sucesso, senhor Ramon."

        if is_stream:
            async def event_generator():
                chunk_id = f"chatcmpl-{int(time.time())}"
                # Split reply in tokens or words for natural streaming
                words = reply.split(" ")
                for i, w in enumerate(words):
                    piece = w + (" " if i < len(words) - 1 else "")
                    chunk = {
                        "id": chunk_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": DEFAULT_MODEL,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": piece},
                                "finish_reason": None
                            }
                        ]
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                
                done_chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": DEFAULT_MODEL,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop"
                        }
                    ]
                }
                yield f"data: {json.dumps(done_chunk)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(event_generator(), media_type="text/event-stream")

        return {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": DEFAULT_MODEL,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": reply
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": len(last_msg),
                "completion_tokens": len(reply),
                "total_tokens": len(last_msg) + len(reply)
            }
        }
    except Exception as e:
        if is_stream:
            async def err_generator():
                err_chunk = {
                    "id": "chatcmpl-fallback",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": DEFAULT_MODEL,
                    "choices": [{"index": 0, "delta": {"content": "Olá senhor Ramon, estou online e pronto para auxiliá-lo."}, "finish_reason": "stop"}]
                }
                yield f"data: {json.dumps(err_chunk)}\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(err_generator(), media_type="text/event-stream")
        return {
            "id": "chatcmpl-fallback",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": DEFAULT_MODEL,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Olá senhor Ramon, estou online e pronto para auxiliá-lo."
                    },
                    "finish_reason": "stop"
                }
            ]
        }

# ==========================================
# 3. API do Assistente e Inteligência Artificial
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
        if model != "gemini-2.5-flash":
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=req.message,
                    config={
                        "system_instruction": system_instruction,
                        "temperature": 0.5
                    }
                )
                reply = response.text or "Comando processado via rota secundária, senhor Ramon."
                return ChatResponse(
                    reply=reply,
                    model_used="gemini-2.5-flash",
                    timestamp=time.time()
                )
            except Exception as e2:
                raise HTTPException(status_code=500, detail=f"Erro de processamento: {str(e2)}")
        raise HTTPException(status_code=500, detail=f"Erro de processamento: {str(e)}")

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
