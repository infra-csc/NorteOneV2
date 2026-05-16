from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from pydantic import BaseModel
from app.core.database import get_db
from app.models.dimensoes import SkuMapping, EventoGrupo
from app.models.vendas_snapshot import CurvaHistoricaSnapshot, VendasDiariaSnapshot
from app.schemas.dimensoes import (
    SkuMappingCreate, SkuMappingUpdate, SkuMappingResponse,
    EventoGrupoCreate, EventoGrupoUpdate, EventoGrupoResponse
)
from app.core.security import get_current_user, require_admin, require_permission
from app.models.user import Usuario
import app.core.database as db_module
from sqlalchemy import text, func
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import logging
import re
import threading
import time as _time

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/sku-mappings", tags=["SKU Mappings"])

# Debounce de rebuild de snapshot por (evento_grupo, ano). Evita pile-up de
# threads quando _invalidate_snapshot é chamado em rajada (ex.: usuário corrige
# vários campos do mesmo mapeamento em sequência, ou bulk-update). Janela curta
# é suficiente: o objetivo é colapsar disparos quase simultâneos, não bloquear
# refresh legítimos espaçados.
_REBUILD_DEBOUNCE_SECONDS = 30
_rebuild_debounce_lock = threading.Lock()
_rebuild_debounce_ts: dict = {}


def _should_dispatch_rebuild(evento_grupo: str, ano: int) -> bool:
    """Retorna True se nenhum rebuild para essa chave foi disparado nos
    últimos _REBUILD_DEBOUNCE_SECONDS segundos. Atualiza o registro
    atomicamente para evitar corrida entre múltiplas requisições."""
    key = (evento_grupo, ano)
    now = _time.monotonic()
    with _rebuild_debounce_lock:
        last = _rebuild_debounce_ts.get(key)
        if last is not None and (now - last) < _REBUILD_DEBOUNCE_SECONDS:
            return False
        _rebuild_debounce_ts[key] = now
        return True


def _proactive_eventos_list_refresh(ano: int):
    """Dispara um refresh completo da lista de eventos em background,
    sem esperar por uma requisição do usuário.
    Garante que novos grupos/mappings apareçam no ISC imediatamente.
    """
    import threading

    def _runner():
        try:
            from app.core.database import SessionLocal
            from app.api.routes.marketing import get_marketing_events
            _db = SessionLocal()
            try:
                get_marketing_events(ano=ano, db=_db, current_user=None)
                logger.info(f"[SKUMapping] Proactive eventos_list refresh concluído ano={ano}")
            finally:
                _db.close()
        except Exception as e:
            logger.warning(f"[SKUMapping] Proactive eventos_list refresh falhou: {e}")

    threading.Thread(target=_runner, daemon=True).start()


def _invalidate_all_marketing_caches(trigger_refresh: bool = True):
    """Invalida todos os caches de marketing (ISC, detalhe de evento, lista de eventos).
    Deve ser chamado sempre que mapeamentos SKU ou grupos de eventos forem alterados.
    Se trigger_refresh=True (padrão), dispara imediatamente um refresh da lista
    para que novos eventos apareçam sem esperar requisição do usuário.
    """
    try:
        from app.core.cache import isc_cache as _smart_isc_cache, event_detail_cache, eventos_list_cache
        _smart_isc_cache.invalidate()
        event_detail_cache.invalidate()
        eventos_list_cache.invalidate()
    except Exception as e:
        logger.warning(f"Falha ao invalidar caches de marketing: {e}")

    if trigger_refresh:
        try:
            from datetime import datetime as _dt
            _ano = _dt.now().year
            _proactive_eventos_list_refresh(_ano)
        except Exception as e:
            logger.warning(f"Falha ao disparar proactive refresh: {e}")


def _invalidate_curva_cache(evento_grupo: str, ano: int, db: Session = None):
    if not evento_grupo:
        return
    try:
        from app.core.cache import curva_cache
        prev_ano = ano - 1
        next_ano = ano + 1
        for y in [prev_ano, ano, next_ano]:
            curva_cache.invalidate(f"{y}_grp_{evento_grupo}_curva")
            curva_cache.invalidate(f"{y}_grp_{evento_grupo}_insights")

        if db:
            try:
                from app.models.dimensoes import DimProjeto
                grupo_mappings = db.query(SkuMapping).filter(
                    SkuMapping.evento_grupo == evento_grupo,
                    SkuMapping.ativo == True
                ).all()
                skus = set(m.sku for m in grupo_mappings if m.sku)
                if skus:
                    projetos = db.query(DimProjeto).filter(
                        DimProjeto.codigo.in_(skus)
                    ).all()
                    for p in projetos:
                        for y in [prev_ano, ano, next_ano]:
                            curva_cache.invalidate(f"{y}_{p.id}_curva")
                            curva_cache.invalidate(f"{y}_{p.id}_insights")
                    if projetos:
                        logger.info(f"Individual project cache invalidado: projetos={[p.id for p in projetos]} anos={prev_ano},{ano},{next_ano}")
            except Exception as e:
                logger.warning(f"Failed to invalidate individual project cache: {e}")

        logger.info(f"Curva cache invalidado: '{evento_grupo}' anos={prev_ano},{ano},{next_ano}")
    except Exception as e:
        logger.warning(f"Failed to invalidate curva cache for '{evento_grupo}': {e}")


def _invalidate_snapshot(db: Session, evento_grupo: str, ano: int):
    if not evento_grupo:
        return

    last_updated = db.query(func.max(VendasDiariaSnapshot.updated_at)).filter(
        VendasDiariaSnapshot.evento_grupo == evento_grupo
    ).scalar()
    cooldown_ok = (not last_updated) or (datetime.now() - last_updated > timedelta(minutes=10))

    if cooldown_ok:
        deleted_curva = db.query(CurvaHistoricaSnapshot).filter(
            CurvaHistoricaSnapshot.evento_grupo == evento_grupo,
            CurvaHistoricaSnapshot.ano_referencia == ano
        ).delete()
        deleted_vendas = db.query(VendasDiariaSnapshot).filter(
            VendasDiariaSnapshot.evento_grupo == evento_grupo
        ).delete(synchronize_session=False)
        if deleted_curva or deleted_vendas:
            db.commit()
            logger.info(f"Snapshot invalidado: '{evento_grupo}' ano={ano} (curva={deleted_curva}, vendas={deleted_vendas})")

        # Debounce: se já há um rebuild recente para essa chave, não dispara
        # outro. Evita pile-up quando vários campos do mesmo mapeamento são
        # editados em sequência (cada PATCH cairia aqui).
        if not _should_dispatch_rebuild(evento_grupo, ano):
            logger.info(
                f"Rebuild debounce ativo para '{evento_grupo}' ano={ano}: "
                f"thread anterior disparada há <{_REBUILD_DEBOUNCE_SECONDS}s, pulando"
            )
            _invalidate_curva_cache(evento_grupo, ano, db)
            _invalidate_all_marketing_caches()
            return

        import threading
        def _rebuild():
            try:
                from app.core.database import SessionLocal
                from app.services.snapshot_service import consolidar_vendas_grupo, save_curva_historica_snapshot
                rebuild_db = SessionLocal()
                try:
                    consolidar_vendas_grupo(rebuild_db, evento_grupo, ano)
                    logger.info(f"Snapshot reconstruído em background: '{evento_grupo}' ano={ano}")
                    try:
                        from app.api.routes.marketing import _fetch_previous_year_cumulative_pattern
                        pattern = _fetch_previous_year_cumulative_pattern(rebuild_db, evento_grupo, ano + 1)
                        if pattern:
                            save_curva_historica_snapshot(rebuild_db, evento_grupo, ano, pattern, len(pattern), origem="historico")
                            logger.info(f"CurvaHistoricaSnapshot reconstruída em background: '{evento_grupo}' ano_referencia={ano}")
                    except Exception as ce:
                        logger.warning(f"Falha ao reconstruir CurvaHistoricaSnapshot para '{evento_grupo}' ano={ano}: {ce}")
                finally:
                    rebuild_db.close()
            except Exception as e:
                logger.error(f"Falha ao reconstruir snapshot em background para '{evento_grupo}': {e}")
        threading.Thread(target=_rebuild, daemon=True).start()
    else:
        logger.info(f"Cooldown ativo para '{evento_grupo}': snapshot atualizado há menos de 10 min, apenas invalidando cache")

    _invalidate_curva_cache(evento_grupo, ano, db)
    _invalidate_all_marketing_caches()


class EventoExterno(BaseModel):
    id_evento: str
    nome_evento: str
    sku_original: Optional[str] = None
    data_evento: Optional[str] = None
    fonte: str
    ano: int


class EventoSugerido(BaseModel):
    id_evento: str
    nome_evento: str
    sku_original: Optional[str] = None
    data_evento: Optional[str] = None
    fonte: str
    ano: int
    sku_sugerido: Optional[str] = None
    evento_grupo_sugerido: Optional[str] = None
    match_origem: Optional[str] = None  # "nome" ou "sku"


class DescobertaEventosResponse(BaseModel):
    status: str
    ano: int
    total_ativo: int
    total_magento: int
    eventos_sugeridos: List[EventoSugerido]
    eventos_sem_match: List[EventoExterno]


def normalize_nome_evento(nome: str) -> str:
    """Normaliza o nome do evento para matching."""
    if not nome:
        return ""
    nome = nome.lower().strip()
    nome = re.sub(r'\s+', ' ', nome)
    nome = re.sub(r'20\d{2}', '', nome)
    nome = re.sub(r'\d+[ªº°]?\s*etapa', '', nome)
    nome = re.sub(r'etapa\s*\d+', '', nome)
    nome = nome.strip()
    return nome


def normalize_sku_for_match(sku: str) -> str:
    """Normaliza SKU removendo o ano para matching cross-year."""
    if not sku or len(sku) < 5:
        return ""
    base = sku[:3] + sku[5:] if len(sku) >= 6 else sku
    return base.upper()


def fetch_eventos_ativo(ano: int = None) -> List[Dict]:
    """Busca eventos distintos do Ativo (ano atual e anterior)."""
    if db_module.engine_ssh is None:
        logger.error("SSH tunnel para Ativo não configurado")
        return []
    
    query = """
    SELECT
        b.id_evento,
        b.id_campanha_salesforce AS sku,
        b.ds_evento AS nome_evento,
        DATE(b.dt_evento) AS data_evento
    FROM sa_evento AS b 
    WHERE 
        YEAR(b.dt_evento) IN (YEAR(CURDATE()), YEAR(CURDATE()) - 1)
        AND (b.id_campanha_salesforce NOT LIKE '701d0000000%' OR b.id_campanha_salesforce IS NULL)
    ORDER BY b.dt_evento
    """
    
    try:
        with db_module.engine_ssh.connect() as connection:
            result = connection.execute(text(query))
            rows = result.fetchall()
            return [
                {
                    "id_evento": str(row[0]),
                    "sku_original": row[1] or "",
                    "nome_evento": row[2] or "",
                    "data_evento": str(row[3]) if row[3] else None
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Erro ao buscar eventos Ativo: {e}")
        return []


def fetch_eventos_magento(ano: int = None) -> List[Dict]:
    """Busca eventos distintos do Magento (ano atual e anterior)."""
    if db_module.engine_magento is None:
        logger.error("Conexão Magento não configurada")
        return []
    
    query = """
    SELECT
        wl.location_id AS id_evento,
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
            REPLACE(wl.`name`, 'Retirada de kit - CE', 'Circuito das Estações'),
            'Retirada de Kit - CE', 'Circuito das Estações'),'Retirada de KIt - CE', 'Circuito das Estações'),
            'Retirada de Kit- CE', 'Circuito das Estações'),'Retirada de Kit - ', ''),'Retirada de kit - ', ''),
            'SSA', 'Salvador') AS nome_evento,
        wl.final_date AS data_evento
    FROM webpos_location AS wl 
    WHERE 
        YEAR(wl.final_date) IN (YEAR(CURDATE()), YEAR(CURDATE()) - 1)
    ORDER BY wl.final_date
    """
    
    from app.core.db_retry import magento_run

    def _eventos_magento_work(conn):
        return conn.execute(text(query)).fetchall()

    try:
        rows = magento_run(_eventos_magento_work, label="sku_mappings:eventos-magento", profile="request")
        return [
            {
                "id_evento": str(row[0]),
                "nome_evento": row[1] or "",
                "data_evento": str(row[2]) if row[2] else None,
                "sku_original": ""
            }
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Erro ao buscar eventos Magento: {e}")
        return []


@router.get("", response_model=List[SkuMappingResponse])
def list_sku_mappings(
    fonte: Optional[str] = None,
    ano: Optional[int] = None,
    evento_grupo: Optional[str] = None,
    ativo: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_sku_mappings", "pode_visualizar"))
):
    query = db.query(SkuMapping)
    
    if fonte:
        query = query.filter(SkuMapping.fonte == fonte)
    if ano:
        query = query.filter(SkuMapping.ano == ano)
    if evento_grupo:
        query = query.filter(SkuMapping.evento_grupo.ilike(f"%{evento_grupo}%"))
    if ativo is not None:
        query = query.filter(SkuMapping.ativo == ativo)
    
    return query.order_by(SkuMapping.evento_grupo, SkuMapping.ano.desc(), SkuMapping.fonte).all()


@router.get("/grupos", response_model=List[str])
def list_evento_grupos(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_sku_mappings", "pode_visualizar"))
):
    result = db.query(SkuMapping.evento_grupo).distinct().order_by(SkuMapping.evento_grupo).all()
    return [r[0] for r in result]


@router.get("/anos", response_model=List[int])
def list_anos(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_sku_mappings", "pode_visualizar"))
):
    result = db.query(SkuMapping.ano).distinct().order_by(SkuMapping.ano.desc()).all()
    return [r[0] for r in result]


@router.get("/{mapping_id}", response_model=SkuMappingResponse)
def get_sku_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_sku_mappings", "pode_visualizar"))
):
    mapping = db.query(SkuMapping).filter(SkuMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapeamento não encontrado")
    return mapping


@router.post("", response_model=SkuMappingResponse)
def create_sku_mapping(
    mapping: SkuMappingCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin())
):
    existing = db.query(SkuMapping).filter(
        SkuMapping.fonte == mapping.fonte,
        SkuMapping.id_externo == mapping.id_externo,
        SkuMapping.ano == mapping.ano
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Já existe um mapeamento para {mapping.fonte} ID {mapping.id_externo} no ano {mapping.ano}"
        )
    
    db_mapping = SkuMapping(**mapping.model_dump())
    db.add(db_mapping)
    db.commit()
    db.refresh(db_mapping)
    if db_mapping.data_evento:
        _invalidate_snapshot(db, db_mapping.evento_grupo, db_mapping.ano)
    else:
        _invalidate_curva_cache(db_mapping.evento_grupo, db_mapping.ano, db)
    return db_mapping


@router.put("/{mapping_id}", response_model=SkuMappingResponse)
def update_sku_mapping(
    mapping_id: int,
    mapping: SkuMappingUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin())
):
    db_mapping = db.query(SkuMapping).filter(SkuMapping.id == mapping_id).first()
    if not db_mapping:
        raise HTTPException(status_code=404, detail="Mapeamento não encontrado")
    
    update_data = mapping.model_dump(exclude_unset=True)
    
    if update_data:
        new_fonte = update_data.get('fonte', db_mapping.fonte)
        new_id_externo = update_data.get('id_externo', db_mapping.id_externo)
        new_ano = update_data.get('ano', db_mapping.ano)
        
        existing = db.query(SkuMapping).filter(
            SkuMapping.fonte == new_fonte,
            SkuMapping.id_externo == new_id_externo,
            SkuMapping.ano == new_ano,
            SkuMapping.id != mapping_id
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Já existe um mapeamento para {new_fonte} ID {new_id_externo} no ano {new_ano}"
            )
    
    old_data_evento = db_mapping.data_evento
    old_evento_grupo = db_mapping.evento_grupo
    old_ano = db_mapping.ano
    old_id_externo = db_mapping.id_externo
    old_fonte = db_mapping.fonte

    for key, value in update_data.items():
        setattr(db_mapping, key, value)
    
    db.commit()
    db.refresh(db_mapping)

    data_evento_changed = db_mapping.data_evento != old_data_evento
    grupo_or_ano_changed = db_mapping.evento_grupo != old_evento_grupo or db_mapping.ano != old_ano
    # Mudanças em id_externo/fonte também invalidam o snapshot persistente:
    # o vendas_diaria_snapshot é populado a partir do par (fonte, id_externo),
    # então corrigir um ID errado precisa derrubar o snapshot atual e
    # reconstruí-lo — caso contrário a UI continua mostrando vendas do ID
    # antigo até a próxima rodada do job noturno.
    ids_changed = (
        db_mapping.id_externo != old_id_externo
        or db_mapping.fonte != old_fonte
    )

    if data_evento_changed or grupo_or_ano_changed or ids_changed:
        invalidated = set()
        if old_evento_grupo:
            key = (old_evento_grupo, old_ano)
            if key not in invalidated:
                _invalidate_snapshot(db, old_evento_grupo, old_ano)
                invalidated.add(key)
        key = (db_mapping.evento_grupo, db_mapping.ano)
        if key not in invalidated:
            _invalidate_snapshot(db, db_mapping.evento_grupo, db_mapping.ano)
    else:
        _invalidate_curva_cache(db_mapping.evento_grupo, db_mapping.ano, db)
        _invalidate_all_marketing_caches()

    return db_mapping


@router.delete("/{mapping_id}")
def delete_sku_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin())
):
    db_mapping = db.query(SkuMapping).filter(SkuMapping.id == mapping_id).first()
    if not db_mapping:
        raise HTTPException(status_code=404, detail="Mapeamento não encontrado")
    
    evento_grupo = db_mapping.evento_grupo
    ano = db_mapping.ano
    db.delete(db_mapping)
    db.commit()
    _invalidate_curva_cache(evento_grupo, ano, db)
    _invalidate_all_marketing_caches()
    return {"message": "Mapeamento excluído com sucesso"}


@router.post("/bulk", response_model=List[SkuMappingResponse])
def bulk_create_sku_mappings(
    mappings: List[SkuMappingCreate],
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin())
):
    created = []
    for mapping in mappings:
        existing = db.query(SkuMapping).filter(
            SkuMapping.fonte == mapping.fonte,
            SkuMapping.id_externo == mapping.id_externo,
            SkuMapping.ano == mapping.ano
        ).first()
        
        if not existing:
            db_mapping = SkuMapping(**mapping.model_dump())
            db.add(db_mapping)
            created.append(db_mapping)
    
    db.commit()
    for m in created:
        db.refresh(m)
    
    invalidated = set()
    for m in created:
        if m.data_evento:
            key = (m.evento_grupo, m.ano)
            if key not in invalidated:
                _invalidate_snapshot(db, m.evento_grupo, m.ano)
                invalidated.add(key)

    return created


@router.get("/descobrir-eventos", response_model=DescobertaEventosResponse)
def descobrir_eventos_externos(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_sku_mappings", "pode_visualizar"))
):
    """
    Descobre eventos dos bancos externos (Ativo e Magento) para o ano atual e anterior.
    Sugere mapeamentos baseados nos eventos já cadastrados.
    """
    from datetime import datetime
    ano_atual = datetime.now().year
    
    executor = ThreadPoolExecutor(max_workers=2)
    
    ativo_future = executor.submit(fetch_eventos_ativo)
    magento_future = executor.submit(fetch_eventos_magento)
    
    try:
        eventos_ativo_result = ativo_future.result(timeout=60.0)
    except Exception as e:
        logger.error(f"Erro ao buscar eventos Ativo: {e}")
        eventos_ativo_result = []
    
    try:
        eventos_magento_result = magento_future.result(timeout=60.0)
    except Exception as e:
        logger.error(f"Erro ao buscar eventos Magento: {e}")
        eventos_magento_result = []
    
    eventos_ativo = eventos_ativo_result if isinstance(eventos_ativo_result, list) else []
    eventos_magento = eventos_magento_result if isinstance(eventos_magento_result, list) else []
    
    mapeamentos_existentes_all = db.query(SkuMapping).filter(
        SkuMapping.ativo == True
    ).all()
    
    ids_ja_mapeados = {
        (m.fonte, str(m.id_externo)) for m in mapeamentos_existentes_all
    }
    
    nome_to_mapping = {}
    sku_base_to_mapping = {}
    
    for m in mapeamentos_existentes_all:
        nome_norm = normalize_nome_evento(m.nome_evento)
        if nome_norm:
            nome_to_mapping[nome_norm] = m
        
        sku_base = normalize_sku_for_match(m.sku)
        if sku_base:
            sku_base_to_mapping[sku_base] = m
    
    eventos_sugeridos = []
    eventos_sem_match = []
    
    def processar_eventos(eventos: List[Dict], fonte: str):
        for ev in eventos:
            if (fonte, ev["id_evento"]) in ids_ja_mapeados:
                continue
            
            ev_ano = ano_atual
            if ev.get("data_evento"):
                try:
                    ev_ano = int(str(ev["data_evento"])[:4])
                except (ValueError, IndexError):
                    ev_ano = ano_atual
            
            match_encontrado = None
            match_origem = None
            
            nome_norm = normalize_nome_evento(ev["nome_evento"])
            if nome_norm and nome_norm in nome_to_mapping:
                match_encontrado = nome_to_mapping[nome_norm]
                match_origem = "nome"
            
            if not match_encontrado:
                sku_base = normalize_sku_for_match(ev.get("sku_original") or "")
                if sku_base and sku_base in sku_base_to_mapping:
                    match_encontrado = sku_base_to_mapping[sku_base]
                    match_origem = "sku"
            
            if match_encontrado:
                sku_sugerido = match_encontrado.sku[:3] + str(ev_ano)[-2:] + match_encontrado.sku[5:] if len(match_encontrado.sku) >= 5 else match_encontrado.sku
                
                eventos_sugeridos.append(EventoSugerido(
                    id_evento=ev["id_evento"],
                    nome_evento=ev["nome_evento"],
                    sku_original=ev.get("sku_original"),
                    data_evento=ev.get("data_evento"),
                    fonte=fonte,
                    ano=ev_ano,
                    sku_sugerido=sku_sugerido,
                    evento_grupo_sugerido=match_encontrado.evento_grupo,
                    match_origem=match_origem
                ))
            else:
                eventos_sem_match.append(EventoExterno(
                    id_evento=ev["id_evento"],
                    nome_evento=ev["nome_evento"],
                    sku_original=ev.get("sku_original"),
                    data_evento=ev.get("data_evento"),
                    fonte=fonte,
                    ano=ev_ano
                ))
    
    if eventos_ativo:
        processar_eventos(eventos_ativo, "ATIVO")
    if eventos_magento:
        processar_eventos(eventos_magento, "MAGENTO")
    
    return DescobertaEventosResponse(
        status="success",
        ano=ano_atual,
        total_ativo=len(eventos_ativo),
        total_magento=len(eventos_magento),
        eventos_sugeridos=eventos_sugeridos,
        eventos_sem_match=eventos_sem_match
    )


grupo_router = APIRouter(prefix="/api/admin/evento-grupos", tags=["Evento Grupos"])


@grupo_router.get("", response_model=List[EventoGrupoResponse])
def list_evento_grupos_crud(
    ativo: Optional[bool] = None,
    busca: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_sku_mappings", "pode_visualizar"))
):
    query = db.query(EventoGrupo)
    if ativo is not None:
        query = query.filter(EventoGrupo.ativo == ativo)
    if busca:
        query = query.filter(EventoGrupo.nome.ilike(f"%{busca}%"))
    return query.order_by(EventoGrupo.nome).all()


@grupo_router.post("", response_model=EventoGrupoResponse)
def create_evento_grupo(
    grupo: EventoGrupoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin())
):
    existing = db.query(EventoGrupo).filter(EventoGrupo.nome == grupo.nome).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Já existe um grupo com o nome '{grupo.nome}'")
    
    db_grupo = EventoGrupo(**grupo.model_dump())
    db.add(db_grupo)
    db.commit()
    db.refresh(db_grupo)
    return db_grupo


@grupo_router.put("/{grupo_id}", response_model=EventoGrupoResponse)
def update_evento_grupo(
    grupo_id: int,
    grupo: EventoGrupoUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin())
):
    db_grupo = db.query(EventoGrupo).filter(EventoGrupo.id == grupo_id).first()
    if not db_grupo:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    
    update_data = grupo.model_dump(exclude_unset=True)
    old_nome = db_grupo.nome
    
    if "nome" in update_data and update_data["nome"] != old_nome:
        existing = db.query(EventoGrupo).filter(
            EventoGrupo.nome == update_data["nome"],
            EventoGrupo.id != grupo_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Já existe um grupo com o nome '{update_data['nome']}'")
        
        db.query(SkuMapping).filter(
            SkuMapping.evento_grupo == old_nome
        ).update({SkuMapping.evento_grupo: update_data["nome"]})
    
    for key, value in update_data.items():
        setattr(db_grupo, key, value)
    
    db.commit()
    db.refresh(db_grupo)
    _invalidate_all_marketing_caches()
    return db_grupo


@grupo_router.get("/available-curves")
def list_available_curves(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_sku_mappings", "pode_visualizar"))
):
    from sqlalchemy import and_
    max_ano_sub = db.query(
        CurvaHistoricaSnapshot.evento_grupo,
        func.max(CurvaHistoricaSnapshot.ano_referencia).label("max_ano")
    ).group_by(CurvaHistoricaSnapshot.evento_grupo).subquery()

    grupos_with_curves = db.query(
        CurvaHistoricaSnapshot.evento_grupo,
        max_ano_sub.c.max_ano,
        func.count(CurvaHistoricaSnapshot.id).label("pontos"),
        func.min(CurvaHistoricaSnapshot.origem).label("origem")
    ).join(
        max_ano_sub,
        and_(
            CurvaHistoricaSnapshot.evento_grupo == max_ano_sub.c.evento_grupo,
            CurvaHistoricaSnapshot.ano_referencia == max_ano_sub.c.max_ano
        )
    ).group_by(CurvaHistoricaSnapshot.evento_grupo, max_ano_sub.c.max_ano).all()

    result = []
    for row in grupos_with_curves:
        result.append({
            "grupo": row.evento_grupo,
            "anoReferencia": row.max_ano,
            "pontos": row.pontos,
            "origem": row.origem or "historico"
        })
    return sorted(result, key=lambda x: x["grupo"])


@grupo_router.put("/{grupo_id}/curva-override")
def set_curva_override(
    grupo_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin())
):
    db_grupo = db.query(EventoGrupo).filter(EventoGrupo.id == grupo_id).first()
    if not db_grupo:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")

    override_value = payload.get("curva_override")
    db_grupo.curva_override = override_value if override_value else None
    db.commit()
    db.refresh(db_grupo)
    _invalidate_all_marketing_caches()

    # Invalida o snapshot persistido do detalhe do evento e o curva_cache
    # para esse grupo, garantindo que o próximo GET (mesmo com snapshot-first
    # read) recompute a curva com o novo override em vez de servir o snapshot
    # antigo (que ainda contém a curva anterior).
    grupo_evento_id = f"grp_{db_grupo.nome}"
    try:
        from app.models.evento_detail_snapshot import EventoDetailSnapshot
        deleted = db.query(EventoDetailSnapshot).filter(
            EventoDetailSnapshot.evento_id == grupo_evento_id
        ).delete(synchronize_session=False)
        if deleted:
            db.commit()
            logger.info(
                f"[CurvaOverride] EventoDetailSnapshot invalidado para '{grupo_evento_id}' "
                f"({deleted} linha(s)) após mudança de curva_override"
            )
    except Exception as e:
        logger.warning(
            f"[CurvaOverride] Falha ao invalidar EventoDetailSnapshot de '{grupo_evento_id}': {e}"
        )
        try:
            db.rollback()
        except Exception:
            pass

    try:
        ano_atual = datetime.now().year
        _invalidate_curva_cache(db_grupo.nome, ano_atual, db=db)
    except Exception as e:
        logger.warning(
            f"[CurvaOverride] Falha ao invalidar curva_cache de '{db_grupo.nome}': {e}"
        )

    return {"message": "Override atualizado", "curva_override": db_grupo.curva_override}


@grupo_router.delete("/{grupo_id}")
def delete_evento_grupo(
    grupo_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin())
):
    db_grupo = db.query(EventoGrupo).filter(EventoGrupo.id == grupo_id).first()
    if not db_grupo:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    
    db.delete(db_grupo)
    db.commit()
    _invalidate_all_marketing_caches()
    return {"message": "Grupo excluído com sucesso"}
