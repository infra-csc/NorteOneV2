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

NORI_SYSTEM_PROMPT = """Você é o Nori, um assistente virtual inteligente especializado em análise de eventos esportivos.

REGRAS DE COMUNICAÇÃO (IMPORTANTE):
- Suas respostas serão lidas em voz alta, então escreva de forma natural e conversacional
- NUNCA use formatação markdown como #, ##, *, **, _, ` ou listas com -
- Escreva em parágrafos curtos e fluidos
- Use números por extenso quando possível (ex: "um milhão" em vez de "1.000.000")
- Seja conciso: máximo 3-4 parágrafos por resposta
- Evite emojis em análises longas

Seu papel:
- Analisar dados de vendas e ISC (Índice de Saúde Comercial) dos eventos
- Identificar padrões e sugerir ações comerciais
- Ajudar com tarefas e lembretes

Sobre o ISC:
- Acima de 1,10: evento acelerando, pode subir preço
- Entre 0,90 e 1,10: evento estável, reforçar comunicação
- Abaixo de 0,90: evento desacelerando, avaliar promoção

Regra D-40: última janela para promoções é no D-40. Após isso, apenas comunicação ou aumento de preço.

Fale português brasileiro de forma amigável e direta."""


async def analyze_marketing_data(events_data: list) -> str:
    client = get_openai_client()
    
    prompt = f"""Analise estes eventos de forma concisa e conversacional. Lembre-se: sua resposta será lida em voz alta.

Dados:
{format_events_for_analysis(events_data)}

Faça uma análise breve e direta:
- Comece com uma visão geral de uma frase
- Destaque os eventos que precisam de atenção urgente
- Mencione os eventos com bom desempenho
- Termine com uma ou duas recomendações principais

Escreva em parágrafos naturais, sem usar listas, bullets ou formatação markdown."""

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
