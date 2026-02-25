from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
import re
from ...core import database as db_module
from ...core.database import get_db

router = APIRouter(prefix="/atletas-externos", tags=["Atletas Externos (MySQL via SSH)"])

cache_data = {}
CACHE_TTL_SECONDS = 300
MAX_CACHE_ENTRIES = 100

class AtletaExternoResumo(BaseModel):
    evento: str
    sku: str
    categoria: Optional[str]
    local_inscricao: str
    data_evento: Optional[str]
    qtd_atletas: int
    valor_total_inscricao: float

class AtletaExternoPorEvento(BaseModel):
    sku: str
    evento: str
    data_evento: Optional[str]
    qtd_total: int
    qtd_por_categoria: List[dict]
    qtd_por_local: List[dict]
    qtd_por_periodo: List[dict]

def get_cache(key: str):
    if key in cache_data:
        cached_at, data = cache_data[key]
        if datetime.now() - cached_at < timedelta(seconds=CACHE_TTL_SECONDS):
            return data
        del cache_data[key]
    return None

def set_cache(key: str, data):
    global cache_data
    if len(cache_data) >= MAX_CACHE_ENTRIES:
        oldest_key = min(cache_data.keys(), key=lambda k: cache_data[k][0])
        del cache_data[oldest_key]
    cache_data[key] = (datetime.now(), data)

def validate_date(date_str: Optional[str]) -> Optional[str]:
    if date_str is None:
        return None
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return date_str
    raise HTTPException(status_code=400, detail=f"Data inválida: {date_str}. Use formato YYYY-MM-DD")

def validate_sku(sku: Optional[str]) -> Optional[str]:
    if sku is None:
        return None
    if re.match(r'^[A-Za-z0-9_\-]+$', sku):
        return sku
    raise HTTPException(status_code=400, detail=f"SKU inválido: {sku}. Use apenas letras, números, hífen e underscore")

@router.get("/resumo")
def get_atletas_externos_resumo(
    id_evento: Optional[int] = Query(None, description="ID do evento para filtrar"),
    sku: Optional[str] = Query(None, description="SKU (id_campanha_salesforce) para filtrar"),
    data_inicio: Optional[str] = Query(None, description="Data início do período (YYYY-MM-DD)"),
    data_fim: Optional[str] = Query(None, description="Data fim do período (YYYY-MM-DD)")
):
    """
    Retorna resumo de atletas do banco externo via SSH tunnel.
    Agrupado por evento, categoria, local de inscrição e período.
    Cache de 5 minutos para otimização de performance.
    """
    if db_module.engine_ssh is None:
        raise HTTPException(status_code=503, detail="Conexão SSH com banco externo não disponível")
    
    data_inicio = validate_date(data_inicio)
    data_fim = validate_date(data_fim)
    sku = validate_sku(sku)
    
    cache_key = f"resumo_{id_evento}_{sku}_{data_inicio}_{data_fim}"
    cached = get_cache(cache_key)
    if cached:
        return {"status": "success", "cached": True, "data": cached}
    
    params = {
        "id_evento": id_evento if id_evento else None,
        "sku": sku if sku else None,
        "data_inicio": data_inicio if data_inicio else None,
        "data_fim": data_fim if data_fim else None,
    }

    query = text("""
    SELECT
        b.ds_evento AS evento,
        b.id_campanha_salesforce AS sku,
        h.ds_categoria AS categoria,
        DATE(b.dt_evento) AS data_evento,
        CASE
            WHEN c.fl_local_inscricao = '1' THEN 'Site'
            WHEN c.fl_local_inscricao = '2' THEN 'Balcão'
            WHEN c.fl_local_inscricao = '3' THEN 'Entrega'
            ELSE COALESCE(c.fl_local_inscricao, 'Outros')
        END AS local_inscricao,
        COUNT(DISTINCT a.id_pedido_evento) AS qtd_atletas,
        SUM(
            IF(a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0) < 0, 0,
               a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0))
        ) AS valor_total_inscricao
    FROM sa_pedido_evento AS a
    INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
    INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
    LEFT JOIN sa_modalidade_categoria AS h ON a.id_categoria = h.id_categoria
    WHERE c.id_pedido_status = 2
      AND (:id_evento IS NULL OR b.id_evento = :id_evento)
      AND (:sku IS NULL OR b.id_campanha_salesforce = :sku)
      AND (:data_inicio IS NULL OR c.dt_pedido >= :data_inicio)
      AND (:data_fim IS NULL OR c.dt_pedido <= :data_fim)
    GROUP BY b.ds_evento, b.id_campanha_salesforce, h.ds_categoria, DATE(b.dt_evento), local_inscricao
    ORDER BY b.ds_evento, h.ds_categoria
    """)
    
    try:
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(query, params)
            rows = result.fetchall()
            
            data = []
            for row in rows:
                data.append({
                    "evento": row[0],
                    "sku": row[1],
                    "categoria": row[2],
                    "data_evento": str(row[3]) if row[3] else None,
                    "local_inscricao": row[4],
                    "qtd_atletas": int(row[5] or 0),
                    "valor_total_inscricao": float(row[6] or 0)
                })
            
            set_cache(cache_key, data)
            return {"status": "success", "cached": False, "count": len(data), "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar banco externo: {str(e)}")

@router.get("/por-evento")
def get_atletas_por_evento(
    id_evento: Optional[int] = Query(None, description="ID do evento para filtrar"),
    sku: Optional[str] = Query(None, description="SKU (id_campanha_salesforce) para filtrar"),
    data_inicio: Optional[str] = Query(None, description="Data início (YYYY-MM-DD)"),
    data_fim: Optional[str] = Query(None, description="Data fim (YYYY-MM-DD)")
):
    """
    Retorna dados de atletas agrupados por evento com breakdown por:
    - Categoria/Modalidade
    - Local de Inscrição (Site, Balcão, Entrega)
    - Período (por dia)
    """
    if db_module.engine_ssh is None:
        raise HTTPException(status_code=503, detail="Conexão SSH com banco externo não disponível")
    
    data_inicio = validate_date(data_inicio)
    data_fim = validate_date(data_fim)
    sku = validate_sku(sku)
    
    cache_key = f"por_evento_{id_evento}_{sku}_{data_inicio}_{data_fim}"
    cached = get_cache(cache_key)
    if cached:
        return {"status": "success", "cached": True, "data": cached}
    
    params = {
        "id_evento": id_evento,
        "sku": sku,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
    }

    query_eventos = text("""
    SELECT
        b.id_campanha_salesforce AS sku,
        b.ds_evento AS evento,
        DATE(b.dt_evento) AS data_evento,
        COUNT(DISTINCT a.id_pedido_evento) AS qtd_total
    FROM sa_pedido_evento AS a
    INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
    INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
    WHERE
        c.id_pedido_status = 2
        AND (:id_evento IS NULL OR b.id_evento = :id_evento)
        AND (:sku IS NULL OR b.id_campanha_salesforce = :sku)
        AND (:data_inicio IS NULL OR c.dt_pedido >= :data_inicio)
        AND (:data_fim IS NULL OR c.dt_pedido <= :data_fim)
    GROUP BY b.id_campanha_salesforce, b.ds_evento, DATE(b.dt_evento)
    ORDER BY b.ds_evento
    """)

    query_por_categoria = text("""
    SELECT
        b.id_campanha_salesforce AS sku,
        h.ds_categoria AS categoria,
        COUNT(DISTINCT a.id_pedido_evento) AS qtd
    FROM sa_pedido_evento AS a
    INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
    INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
    LEFT JOIN sa_modalidade_categoria AS h ON a.id_categoria = h.id_categoria
    WHERE
        c.id_pedido_status = 2
        AND (:id_evento IS NULL OR b.id_evento = :id_evento)
        AND (:sku IS NULL OR b.id_campanha_salesforce = :sku)
        AND (:data_inicio IS NULL OR c.dt_pedido >= :data_inicio)
        AND (:data_fim IS NULL OR c.dt_pedido <= :data_fim)
    GROUP BY b.id_campanha_salesforce, h.ds_categoria
    """)

    query_por_local = text("""
    SELECT
        b.id_campanha_salesforce AS sku,
        CASE
            WHEN c.fl_local_inscricao = '1' THEN 'Site'
            WHEN c.fl_local_inscricao = '2' THEN 'Balcão'
            WHEN c.fl_local_inscricao = '3' THEN 'Entrega'
            ELSE COALESCE(c.fl_local_inscricao, 'Outros')
        END AS local_inscricao,
        COUNT(DISTINCT a.id_pedido_evento) AS qtd
    FROM sa_pedido_evento AS a
    INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
    INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
    WHERE
        c.id_pedido_status = 2
        AND (:id_evento IS NULL OR b.id_evento = :id_evento)
        AND (:sku IS NULL OR b.id_campanha_salesforce = :sku)
        AND (:data_inicio IS NULL OR c.dt_pedido >= :data_inicio)
        AND (:data_fim IS NULL OR c.dt_pedido <= :data_fim)
    GROUP BY b.id_campanha_salesforce, local_inscricao
    """)

    query_por_periodo = text("""
    SELECT
        b.id_campanha_salesforce AS sku,
        DATE(c.dt_pedido) AS data_pedido,
        COUNT(DISTINCT a.id_pedido_evento) AS qtd
    FROM sa_pedido_evento AS a
    INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
    INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
    WHERE
        c.id_pedido_status = 2
        AND (:id_evento IS NULL OR b.id_evento = :id_evento)
        AND (:sku IS NULL OR b.id_campanha_salesforce = :sku)
        AND (:data_inicio IS NULL OR c.dt_pedido >= :data_inicio)
        AND (:data_fim IS NULL OR c.dt_pedido <= :data_fim)
    GROUP BY b.id_campanha_salesforce, DATE(c.dt_pedido)
    ORDER BY DATE(c.dt_pedido)
    """)
    
    try:
        with db_module.engine_ssh.connect() as conn:
            eventos_result = conn.execute(query_eventos, params)
            eventos_rows = eventos_result.fetchall()

            categorias_result = conn.execute(query_por_categoria, params)
            categorias_rows = categorias_result.fetchall()

            locais_result = conn.execute(query_por_local, params)
            locais_rows = locais_result.fetchall()

            periodos_result = conn.execute(query_por_periodo, params)
            periodos_rows = periodos_result.fetchall()
            
            categorias_por_sku = {}
            for row in categorias_rows:
                sku_key = row[0]
                if sku_key not in categorias_por_sku:
                    categorias_por_sku[sku_key] = []
                categorias_por_sku[sku_key].append({
                    "categoria": row[1] or "Sem categoria",
                    "qtd": int(row[2] or 0)
                })
            
            locais_por_sku = {}
            for row in locais_rows:
                sku_key = row[0]
                if sku_key not in locais_por_sku:
                    locais_por_sku[sku_key] = []
                locais_por_sku[sku_key].append({
                    "local": row[1],
                    "qtd": int(row[2] or 0)
                })
            
            periodos_por_sku = {}
            for row in periodos_rows:
                sku_key = row[0]
                if sku_key not in periodos_por_sku:
                    periodos_por_sku[sku_key] = []
                periodos_por_sku[sku_key].append({
                    "data": str(row[1]) if row[1] else None,
                    "qtd": int(row[2] or 0)
                })
            
            data = []
            for row in eventos_rows:
                sku_key = row[0]
                data.append({
                    "sku": sku_key,
                    "evento": row[1],
                    "data_evento": str(row[2]) if row[2] else None,
                    "qtd_total": int(row[3] or 0),
                    "qtd_por_categoria": categorias_por_sku.get(sku_key, []),
                    "qtd_por_local": locais_por_sku.get(sku_key, []),
                    "qtd_por_periodo": periodos_por_sku.get(sku_key, [])
                })
            
            set_cache(cache_key, data)
            return {"status": "success", "cached": False, "count": len(data), "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar banco externo: {str(e)}")

@router.get("/vincular-projetos")
def vincular_atletas_projetos(
    db: Session = Depends(get_db)
):
    """
    Retorna lista de projetos internos (dim_projeto) com seus SKUs para vinculação
    com os dados do banco externo.
    """
    from ...models.dimensoes import DimProjeto
    
    projetos = db.query(
        DimProjeto.id,
        DimProjeto.codigo,
        DimProjeto.evento,
        DimProjeto.data_evento,
        DimProjeto.status
    ).filter(
        DimProjeto.status != 'CANCELADO'
    ).order_by(DimProjeto.data_evento.desc()).all()
    
    return {
        "status": "success",
        "projetos": [
            {
                "id": p.id,
                "codigo_sku": p.codigo,
                "evento": p.evento,
                "data_evento": str(p.data_evento) if p.data_evento else None,
                "status": p.status
            }
            for p in projetos
        ]
    }

@router.get("/por-projeto/{codigo_sku}")
def get_atletas_por_projeto_sku(
    codigo_sku: str,
    data_inicio: Optional[str] = Query(None, description="Data início (YYYY-MM-DD)"),
    data_fim: Optional[str] = Query(None, description="Data fim (YYYY-MM-DD)")
):
    """
    Retorna dados de atletas do banco externo filtrando pelo SKU (codigo do projeto interno).
    Vincula dim_projeto.codigo com id_campanha_salesforce do banco externo.
    """
    if db_module.engine_ssh is None:
        raise HTTPException(status_code=503, detail="Conexão SSH com banco externo não disponível")
    
    data_inicio = validate_date(data_inicio)
    data_fim = validate_date(data_fim)
    codigo_sku = validate_sku(codigo_sku)
    
    if not codigo_sku:
        raise HTTPException(status_code=400, detail="SKU é obrigatório")
    
    cache_key = f"projeto_{codigo_sku}_{data_inicio}_{data_fim}"
    cached = get_cache(cache_key)
    if cached:
        return {"status": "success", "cached": True, "data": cached}
    
    params = {
        "codigo_sku": codigo_sku,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
    }

    query_total = text("""
    SELECT
        b.id_campanha_salesforce AS sku,
        b.ds_evento AS evento,
        DATE(b.dt_evento) AS data_evento,
        COUNT(DISTINCT a.id_pedido_evento) AS qtd_total,
        SUM(
            IF(a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0) < 0, 0,
               a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0))
        ) AS receita_total
    FROM sa_pedido_evento AS a
    INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
    INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
    LEFT JOIN sa_modalidade_categoria AS h ON a.id_categoria = h.id_categoria
    WHERE c.id_pedido_status = 2
      AND b.id_campanha_salesforce = :codigo_sku
      AND (:data_inicio IS NULL OR c.dt_pedido >= :data_inicio)
      AND (:data_fim IS NULL OR c.dt_pedido <= :data_fim)
    GROUP BY b.id_campanha_salesforce, b.ds_evento, DATE(b.dt_evento)
    """)

    query_por_categoria = text("""
    SELECT
        h.ds_categoria AS categoria,
        COUNT(DISTINCT a.id_pedido_evento) AS qtd,
        SUM(
            IF(a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0) < 0, 0,
               a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0))
        ) AS receita
    FROM sa_pedido_evento AS a
    INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
    INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
    LEFT JOIN sa_modalidade_categoria AS h ON a.id_categoria = h.id_categoria
    WHERE c.id_pedido_status = 2
      AND b.id_campanha_salesforce = :codigo_sku
      AND (:data_inicio IS NULL OR c.dt_pedido >= :data_inicio)
      AND (:data_fim IS NULL OR c.dt_pedido <= :data_fim)
    GROUP BY h.ds_categoria
    ORDER BY qtd DESC
    """)

    query_por_local = text("""
    SELECT
        CASE
            WHEN c.fl_local_inscricao = '1' THEN 'Site'
            WHEN c.fl_local_inscricao = '2' THEN 'Balcão'
            WHEN c.fl_local_inscricao = '3' THEN 'Entrega'
            ELSE COALESCE(c.fl_local_inscricao, 'Outros')
        END AS local_inscricao,
        COUNT(DISTINCT a.id_pedido_evento) AS qtd,
        SUM(
            IF(a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0) < 0, 0,
               a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0))
        ) AS receita
    FROM sa_pedido_evento AS a
    INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
    INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
    LEFT JOIN sa_modalidade_categoria AS h ON a.id_categoria = h.id_categoria
    WHERE c.id_pedido_status = 2
      AND b.id_campanha_salesforce = :codigo_sku
      AND (:data_inicio IS NULL OR c.dt_pedido >= :data_inicio)
      AND (:data_fim IS NULL OR c.dt_pedido <= :data_fim)
    GROUP BY local_inscricao
    ORDER BY qtd DESC
    """)

    query_por_dia = text("""
    SELECT
        DATE(c.dt_pedido) AS data_pedido,
        COUNT(DISTINCT a.id_pedido_evento) AS qtd,
        SUM(
            IF(a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0) < 0, 0,
               a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0))
        ) AS receita
    FROM sa_pedido_evento AS a
    INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
    INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
    LEFT JOIN sa_modalidade_categoria AS h ON a.id_categoria = h.id_categoria
    WHERE c.id_pedido_status = 2
      AND b.id_campanha_salesforce = :codigo_sku
      AND (:data_inicio IS NULL OR c.dt_pedido >= :data_inicio)
      AND (:data_fim IS NULL OR c.dt_pedido <= :data_fim)
    GROUP BY DATE(c.dt_pedido)
    ORDER BY DATE(c.dt_pedido)
    """)
    
    try:
        with db_module.engine_ssh.connect() as conn:
            total_result = conn.execute(query_total, params)
            total_row = total_result.fetchone()
            
            if not total_row:
                return {
                    "status": "success", 
                    "cached": False, 
                    "data": {
                        "sku": codigo_sku,
                        "evento": None,
                        "data_evento": None,
                        "qtd_total": 0,
                        "receita_total": 0,
                        "por_categoria": [],
                        "por_local": [],
                        "por_dia": []
                    }
                }
            
            categorias_result = conn.execute(query_por_categoria, params)
            por_categoria = [
                {"categoria": row[0] or "Sem categoria", "qtd": int(row[1] or 0), "receita": float(row[2] or 0)}
                for row in categorias_result.fetchall()
            ]
            
            locais_result = conn.execute(query_por_local, params)
            por_local = [
                {"local": row[0], "qtd": int(row[1] or 0), "receita": float(row[2] or 0)}
                for row in locais_result.fetchall()
            ]
            
            dias_result = conn.execute(query_por_dia, params)
            por_dia = [
                {"data": str(row[0]) if row[0] else None, "qtd": int(row[1] or 0), "receita": float(row[2] or 0)}
                for row in dias_result.fetchall()
            ]
            
            data = {
                "sku": total_row[0],
                "evento": total_row[1],
                "data_evento": str(total_row[2]) if total_row[2] else None,
                "qtd_total": int(total_row[3] or 0),
                "receita_total": float(total_row[4] or 0),
                "por_categoria": por_categoria,
                "por_local": por_local,
                "por_dia": por_dia
            }
            
            set_cache(cache_key, data)
            return {"status": "success", "cached": False, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar banco externo: {str(e)}")

@router.delete("/cache")
def limpar_cache():
    """
    Limpa o cache de dados externos para forçar nova consulta.
    """
    global cache_data
    count = len(cache_data)
    cache_data = {}
    return {"status": "success", "message": f"Cache limpo. {count} entradas removidas."}
