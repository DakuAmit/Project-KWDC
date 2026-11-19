import os
import sys
import json
import traceback

# Add backend directory to sys.path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

try:
    from app.main import app as fastapi_app
    
    async def app(scope, receive, send):
        if scope["type"] == "http":
            try:
                await fastapi_app(scope, receive, send)
            except Exception as exc:
                err_trace = traceback.format_exc()
                print(f"[FATAL SERVERLESS APP ERROR] {err_trace}")
                payload = json.dumps({
                    "error": "Serverless Execution Error",
                    "detail": str(exc),
                    "traceback": err_trace
                }).encode("utf-8")
                await send({
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(payload)).encode("utf-8")),
                    ],
                })
                await send({
                    "type": "http.response.body",
                    "body": payload,
                })
        else:
            await fastapi_app(scope, receive, send)
            
    handler = app

except Exception as import_error:
    err_trace = traceback.format_exc()
    print(f"[FATAL BACKEND IMPORT ERROR] {err_trace}")
    
    async def fallback_handler(scope, receive, send):
        if scope["type"] == "http":
            payload = json.dumps({
                "error": "Backend Import Error",
                "detail": str(import_error),
                "traceback": err_trace
            }).encode("utf-8")
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode("utf-8")),
                ],
            })
            await send({
                "type": "http.response.body",
                "body": payload,
            })
            
    handler = fallback_handler
    app = fallback_handler
