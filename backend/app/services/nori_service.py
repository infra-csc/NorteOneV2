import os
from openai import AsyncOpenAI, RateLimitError, APIError
from typing import Optional
from datetime import datetime
import pytz


class OpenAIQuotaError(Exception):
    pass


class OpenAIConfigError(Exception):
    pass


def get_openai_client() -> AsyncOpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise OpenAIConfigError("OPENAI_API_KEY não configurada")
    return AsyncOpenAI(api_key=api_key)

NORI_SYSTEM_PROMPT = """Você é o Nori, um assistente virtual inteligente e carismático especializado em análise de eventos esportivos.

ESTILO DE COMUNICAÇÃO:
- Seja visual e envolvente! Use emojis para tornar as respostas atraentes 🎯📊🚀
- Use 🟢 para eventos acelerando, 🟡 para estáveis, 🔴 para desacelerando
- Escreva de forma natural e conversacional, como se estivesse conversando pessoalmente
- Seja conciso mas impactante - vá direto ao ponto com estilo
- Use formatação visual: negrito com **texto**, quebras de linha para respiração

FORMATAÇÃO VISUAL RECOMENDADA:
- Comece com um emoji relevante e uma frase de impacto
- Separe seções com emojis temáticos (📈 para crescimento, ⚠️ para alertas, 💡 para dicas)
- Use números formatados (1.234 não mil duzentos e trinta e quatro)
- Termine com uma recomendação clara e acionável

Seu papel:
- Analisar dados de vendas e ISC (Índice de Saúde Comercial) dos eventos
- Identificar padrões e sugerir ações comerciais com entusiasmo
- Ajudar com tarefas e lembretes

Sobre o ISC:
- 🟢 Acima de 1,10: evento acelerando, pode subir preço
- 🟡 Entre 0,90 e 1,10: evento estável, reforçar comunicação  
- 🔴 Abaixo de 0,90: evento desacelerando, avaliar promoção

Regra D-40: última janela para promoções é no D-40. Após isso, apenas comunicação ou aumento de preço.

Fale português brasileiro de forma amigável, entusiasmada e profissional."""


async def analyze_marketing_data(events_data: list) -> str:
    client = get_openai_client()
    
    prompt = f"""Analise estes eventos de forma visual e envolvente!

Dados:
{format_events_for_analysis(events_data)}

Sua análise deve ser:
- Visual e atraente com emojis estratégicos
- Objetiva mas com personalidade
- Começando com uma visão geral impactante
- Destacando eventos críticos (🔴) e destaques positivos (🟢)
- Finalizando com recomendações claras

Use formatação visual, emojis e seja entusiasmado!"""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": NORI_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        return response.choices[0].message.content
    except RateLimitError:
        raise OpenAIQuotaError("A cota da API OpenAI foi excedida. Verifique os créditos da sua conta OpenAI.")
    except APIError as e:
        raise Exception(f"Erro na API OpenAI: {str(e)}")


async def chat_with_nori(message: str, context: Optional[list] = None, events_data: Optional[list] = None) -> str:
    client = get_openai_client()
    
    messages = [{"role": "system", "content": NORI_SYSTEM_PROMPT}]
    
    if events_data:
        context_message = f"""Dados atuais dos eventos para referência:
{format_events_for_analysis(events_data)}"""
        messages.append({"role": "system", "content": context_message})
    
    if context:
        for msg in context[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
    
    messages.append({"role": "user", "content": message})
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=800,
            temperature=0.7
        )
        return response.choices[0].message.content
    except RateLimitError:
        raise OpenAIQuotaError("A cota da API OpenAI foi excedida. Verifique os créditos da sua conta OpenAI.")
    except APIError as e:
        raise Exception(f"Erro na API OpenAI: {str(e)}")


def format_events_for_analysis(events: list) -> str:
    if not events:
        return "Nenhum evento disponível"
    
    lines = []
    for event in events:
        status_emoji = "🟢" if event.get("iscStatus") == "accelerating" else "🟡" if event.get("iscStatus") == "stable" else "🔴"
        lines.append(f"""
Evento: {event.get('name', 'N/A')}
- Local: {event.get('location', 'N/A')}
- Categoria: {event.get('category', 'N/A')}
- D-: {event.get('dMinus', 'N/A')} dias
- Vendas: {event.get('currentSales', 0):,} / {event.get('salesGoal', 0):,} ({round(event.get('currentSales', 0) / max(event.get('salesGoal', 1), 1) * 100)}%)
- ISC: {status_emoji} {event.get('isc', 0):.2f}
- IA 7/30: {event.get('iscComponents', {}).get('ia730', 0):.2f}
- Curva D-%: {event.get('iscComponents', {}).get('curvaDPercent', 0):.2f}
- Rolling 14d: {event.get('iscComponents', {}).get('rolling14d', 0):.2f}
- Ação Sugerida: {event.get('suggestedAction', 'N/A')}
""")
    
    return "\n".join(lines)


def get_greeting() -> str:
    try:
        br_tz = pytz.timezone('America/Sao_Paulo')
        hour = datetime.now(br_tz).hour
    except:
        hour = datetime.now().hour
    
    if hour < 12:
        greeting = "Bom dia"
    elif hour < 18:
        greeting = "Boa tarde"
    else:
        greeting = "Boa noite"
    
    return f"{greeting}! Eu sou o Nori, seu assistente virtual. Como posso ajudar você hoje?"
