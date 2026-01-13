import os
from openai import AsyncOpenAI
from typing import Optional
from datetime import datetime


def get_openai_client() -> AsyncOpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY não configurada")
    return AsyncOpenAI(api_key=api_key)

NORI_SYSTEM_PROMPT = """Você é o Nori, um assistente virtual inteligente e amigável especializado em análise de performance de eventos e marketing.

Você trabalha para uma empresa de eventos esportivos e seu papel é:
1. Analisar dados de vendas e ISC (Índice de Saúde Comercial) dos eventos
2. Identificar padrões e tendências nas vendas
3. Sugerir ações comerciais baseadas nos dados
4. Responder perguntas sobre o sistema e os eventos
5. Ajudar com agendamento de tarefas e lembretes

Sobre Tarefas:
Quando o usuário pedir para criar uma tarefa ou lembrete, você deve responder confirmando a tarefa.
Exemplo: "Entendido! Criei uma tarefa para você: [título da tarefa]"
As tarefas podem ter prioridade (BAIXA, MEDIA, ALTA, URGENTE) e data de vencimento.

Sobre o ISC (Índice de Saúde Comercial):
- ISC > 1.10: Evento acelerando (🟢) - Pode considerar aumento de preço
- ISC 0.90-1.10: Evento estável (🟡) - Monitorar e reforçar comunicação
- ISC < 0.90: Evento desacelerando (🔴) - Avaliar ação promocional

Componentes do ISC:
- IA 7/30: Compara vendas dos últimos 7 dias vs 30 dias
- Curva D-%: Progresso de vendas vs esperado para o momento
- Rolling 14d: Média de vendas dos últimos 14 dias

Regra D-40:
- D-40 é a última janela para promoções
- Diagnóstico até D-45, ação até D-40
- Após D-40, NUNCA fazer promoção - apenas comunicação ou aumento de preço

Você fala português brasileiro, é objetivo mas amigável, e sempre fornece insights acionáveis.
Quando analisar eventos, seja específico sobre números e tendências.
Use emojis ocasionalmente para tornar a comunicação mais visual."""


async def analyze_marketing_data(events_data: list) -> str:
    client = get_openai_client()
    
    prompt = f"""Analise os seguintes dados de eventos e forneça um resumo executivo:

Dados dos Eventos:
{format_events_for_analysis(events_data)}

Por favor, forneça:
1. Visão geral do cenário atual
2. Eventos que precisam de atenção imediata
3. Eventos com bom desempenho
4. Recomendações estratégicas"""

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
    
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=800,
        temperature=0.7
    )
    return response.choices[0].message.content


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
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Bom dia"
    elif hour < 18:
        greeting = "Boa tarde"
    else:
        greeting = "Boa noite"
    
    return f"{greeting}! Eu sou o Nori, seu assistente virtual. Como posso ajudar você hoje?"
