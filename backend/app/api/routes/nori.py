from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from app.services.nori_service import chat_with_nori, analyze_marketing_data, get_greeting, OpenAIQuotaError, OpenAIConfigError
from app.core.security import get_current_user
from app.models.user import Usuario

router = APIRouter(prefix="/nori", tags=["Assistente Nori"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    context: Optional[List[ChatMessage]] = None
    events_data: Optional[List[dict]] = None


class ChatResponse(BaseModel):
    response: str
    success: bool


class AnalysisRequest(BaseModel):
    events_data: List[dict]


@router.get("/greeting")
async def nori_greeting(current_user: Usuario = Depends(get_current_user)):
    return {"greeting": get_greeting(), "success": True}


@router.post("/chat", response_model=ChatResponse)
async def nori_chat(
    request: ChatRequest,
    current_user: Usuario = Depends(get_current_user)
):
    try:
        context_list = None
        if request.context:
            context_list = [{"role": m.role, "content": m.content} for m in request.context]
        
        response = await chat_with_nori(
            message=request.message,
            context=context_list,
            events_data=request.events_data
        )
        
        return ChatResponse(response=response, success=True)
    except OpenAIQuotaError as e:
        raise HTTPException(status_code=402, detail=str(e))
    except OpenAIConfigError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar mensagem: {str(e)}")


@router.post("/analyze", response_model=ChatResponse)
async def nori_analyze(
    request: AnalysisRequest,
    current_user: Usuario = Depends(get_current_user)
):
    try:
        response = await analyze_marketing_data(request.events_data)
        return ChatResponse(response=response, success=True)
    except OpenAIQuotaError as e:
        raise HTTPException(status_code=402, detail=str(e))
    except OpenAIConfigError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao analisar dados: {str(e)}")
