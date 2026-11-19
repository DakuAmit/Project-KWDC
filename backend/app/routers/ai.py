from fastapi import APIRouter, Depends
from typing import Dict, Any
from app.services.ai_service import AIService
from app.schemas.ai import AIChatRequest, AIDispatchAdvisorRequest, VoiceCommandRequest

router = APIRouter(prefix="/ai", tags=["AI Copilot & Logistics Assistant"])
api_router = APIRouter(prefix="/api/ai", tags=["AI Copilot API"])

@api_router.post("/chat")
@router.post("/chat")
async def chat_support(payload: AIChatRequest) -> Dict[str, Any]:
    response = await AIService.generate_response(payload.message)
    return {"status": "success", "reply": response}

@api_router.post("/dispatch-advisor")
@router.post("/dispatch-advisor")
async def dispatch_advisor(payload: AIDispatchAdvisorRequest) -> Dict[str, Any]:
    advice = await AIService.dispatch_advisor(
        pickup=payload.pickup_address,
        destination=payload.destination_address,
        cargo_type=payload.cargo_type or "General Cargo"
    )
    return advice

@api_router.post("/voice-command")
@router.post("/voice-command")
async def handle_voice(payload: VoiceCommandRequest) -> Dict[str, Any]:
    advice = await AIService.dispatch_advisor(
        pickup="Kalimati Depot",
        destination="Pokhara Hub",
        cargo_type="Perishable Apples"
    )
    return {
        "action": "dispatch_recommendation",
        "command_processed": payload.command,
        "details": advice
    }
