"""
Serviço de consolidação de inscrições em grão fino (Detalhamento de Eventos).

Fluxo:
1. Busca em sku_mappings os IDs de Ativo e Magento para o evento_grupo pedido.
2. Executa as duas queries em paralelo (ThreadPoolExecutor).
3. Concatena e agrega por dimensões comuns + canonical event key.
4. Recalcula ticket_medio = SUM(receita_liquida) / SUM(inscritos).
5. Mantém os result sets brutos por banco para auditoria/cross-validation.

Snapshot noturno:
- get_detalhe() lê do snapshot PostgreSQL (< 1s) se atualizado há < 26h.
- force_refresh=True ou snapshot ausente disparam query ao vivo e regravação.
- save_snapshot() persiste o payload após query ao vivo.

Chave canônica de consolidação:
- Cada linha raw é enriquecida com `canonical_grupo` = evento_grupo resolvido via
  mapa reverso sku_mappings: (fonte.upper(), id_externo) → evento_grupo.
- A consolidação sempre agrega por (canonical_grupo, DIM_KEYS), o que garante:
  * Linhas Ativo e Magento do MESMO evento canônico se fundem por dimensão.
  * Eventos distintos que coincidam em dimensões NUNCA são fundidos.
- Isso funciona tanto para query de evento único quanto para query global sem filtro.

Cache: dict em memória por chave (evento_grupo or "__all__"), TTL 15 min.
"""
from __future__ import annotations

import json
import logging
import re
import time
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

import app.core.database as db_module
from app.models.dimensoes import SkuMapping
from app.models.cadastro_evento import CadastroEvento
from app.models.projecao import ProjecaoInscritos, AreaProjecao
from app.models.kit_config import KitConfig
from app.models.kit_mapping_snapshot import KitMappingSnapshot
from app.models.detalhe_dimensao_alias import DetalheDimensaoAlias
from app.queries.detalhe_eventos import build_ativo_detalhe, build_magento_detalhe
from app.services.canal_mapping import AREA_PARA_CANAL, CANAIS_DETALHE

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 900  # 15 minutos
SNAPSHOT_MAX_AGE_HOURS = 26  # snapshot válido por 26h

_cache: Dict[str, Tuple[float, Any]] = {}
_cache_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Cache de padrões de dimensão (DetalheDimensaoAlias — todas as dimensões)
# ---------------------------------------------------------------------------
# Estrutura: {dimensao: [(compiled_pattern | None, substituicao, is_regex), ...]}
# None em compiled_pattern indica match exato (case-insensitive).
_dim_alias_cache: Dict[str, list] = {}
_dim_alias_lock = threading.Lock()
_dim_alias_loaded: bool = False


def _load_dimension_aliases(db: Session) -> Dict[str, list]:
    """Carrega DetalheDimensaoAlias do banco e devolve mapa {dimensao: [regras]}."""
    global _dim_alias_cache, _dim_alias_loaded
    rows = (
        db.query(DetalheDimensaoAlias)
        .filter(DetalheDimensaoAlias.ativo == True)
        .order_by(DetalheDimensaoAlias.dimensao, DetalheDimensaoAlias.ordem, DetalheDimensaoAlias.id)
        .all()
    )
    result: Dict[str, list] = {}
    for row in rows:
        entry: list = result.setdefault(row.dimensao, [])
        if row.is_regex:
            try:
                entry.append((re.compile(row.pattern, re.IGNORECASE), row.substituicao, True))
            except re.error:
                pass
        else:
            entry.append((None, row.substituicao, row.pattern.strip()))
    with _dim_alias_lock:
        _dim_alias_cache = result
        _dim_alias_loaded = True
    return result


def _get_dimension_aliases(db: Session) -> Dict[str, list]:
    with _dim_alias_lock:
        if _dim_alias_loaded:
            return dict(_dim_alias_cache)
    return _load_dimension_aliases(db)


def _apply_dim_alias_to_value(value: Optional[str], rules: list) -> str:
    """Aplica regras de uma dimensão a um valor bruto; devolve o alias ou o original."""
    if not value:
        return value or ""
    cleaned = re.sub(r"\s+", " ", value.strip())
    for compiled, substituicao, extra in rules:
        if compiled is None:
            # Exact match (case-insensitive)
            if cleaned.lower() == str(extra).lower():
                return re.sub(r"\s+", " ", substituicao).strip()
        else:
            result = compiled.sub(substituicao, cleaned)
            if result != cleaned:
                return re.sub(r"\s+", " ", result).strip()
    return cleaned


def _apply_dimension_aliases(rows: List[Dict], db: Session) -> None:
    """Aplica padrões de DetalheDimensaoAlias a TODAS as dimensões, in-place."""
    aliases = _get_dimension_aliases(db)
    if not aliases:
        return
    dims = ["kit", "modalidade", "pelotao", "tamanho_camiseta", "produtos"]
    for row in rows:
        for dim in dims:
            rules = aliases.get(dim)
            if rules and row.get(dim):
                row[dim] = _apply_dim_alias_to_value(row[dim], rules)


def invalidate_alias_cache() -> None:
    global _dim_alias_loaded
    with _dim_alias_lock:
        _dim_alias_cache.clear()
        _dim_alias_loaded = False


def _normalize_modalidade(val: Optional[str]) -> Optional[str]:
    """Normaliza o valor bruto de modalidade:
    1. Strip + colapsar espaços internos.
    2. Regex: padrões numérico+k/km → '<N>km' (ex: '5K', '5 km', '5Km' → '5km').
    3. Lowercase.
    """
    if not val:
        return val
    v = " ".join(val.strip().split())
    v = re.sub(r"(\d+)\s*[Kk][Mm]?", lambda m: f"{m.group(1)}km", v)
    v = v.lower()
    return v


# Single-flight guard para force_refresh ao vivo.
# Impede que dois usuários simultâneos disparem queries pesadas ao Ativo/Magento
# para o mesmo evento_grupo ao mesmo tempo. O segundo recebe HTTP 429.
_inflight: set = set()
_inflight_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Contrato de colunas
# ---------------------------------------------------------------------------

COLUMNS = [
    "banco", "id_evento", "evento", "canal", "kit", "modalidade",
    "pelotao", "produtos", "tamanho_camiseta",
    "inscritos", "receita_bruta", "receita_liquida", "ticket_medio",
]

DIM_KEYS = ["canal", "kit", "modalidade", "pelotao", "produtos", "tamanho_camiseta"]


def _row_to_dict(row) -> Dict:
    d = {}
    for i, col in enumerate(COLUMNS):
        val = row[i]
        if col == "inscritos":
            val = int(val) if val is not None else 0
        elif col in ("receita_bruta", "receita_liquida", "ticket_medio"):
            val = float(val) if val is not None else 0.0
        elif val is not None:
            val = str(val)
        d[col] = val
    return d


# ---------------------------------------------------------------------------
# Resolução de IDs via sku_mappings
# ---------------------------------------------------------------------------

def get_evento_ids(db: Session, evento_grupo: str, ano: int) -> Tuple[List[int], List[int]]:
    """
    Retorna (ativo_ids, magento_ids) para o evento_grupo na edição (ano) pedida.

    O campo SkuMapping.ano representa o ano da edição do evento. Filtrar por
    ano evita somar pedidos de edições diferentes que compartilham o mesmo
    evento_grupo (ex.: Troféu Brasil 2025 + 2026). Mapeamentos sem ano
    (nullable historicamente) são conservados via OR IS NULL — valem para
    qualquer edição.
    """
    mappings = (
        db.query(SkuMapping)
        .filter(
            SkuMapping.evento_grupo == evento_grupo,
            SkuMapping.ativo == True,
            (SkuMapping.ano == ano) | (SkuMapping.ano == None),
        )
        .all()
    )
    ativo_ids = [m.id_externo for m in mappings if m.fonte == "ATIVO" and m.id_externo]
    magento_ids = [m.id_externo for m in mappings if m.fonte == "MAGENTO" and m.id_externo]
    return ativo_ids, magento_ids


def resolve_cadastro_evento_ids(db: Session, evento_grupo: str, ano: int) -> List[int]:
    """
    Resolve os CadastroEvento.id correspondentes a um (evento_grupo, ano) do
    Detalhamento de Eventos, para poder buscar a "Projeção de Inscritos"
    (indexada por CadastroEvento.id, não por evento_grupo/ano).

    Dois caminhos, combinados (um evento pode ter cadastro achável por
    qualquer um dos dois, e não são mutuamente exclusivos):
    - MAGENTO: SkuMapping.id_externo -> CadastroEvento.id_evento_magento
      (cache materializado, sincronizado em sku_mappings.py ao salvar o
      mapeamento — ver `_sync_id_evento_magento_from_mapping`).
    - ATIVO: SkuMapping.id_externo -> CadastroEvento.projeto_id (convenção:
      o ID externo do Ativo é o mesmo id de DimProjeto/CadastroEvento.projeto_id).

    Retorna lista vazia quando não há CadastroEvento cadastrado para o evento
    (evento existe em sku_mappings mas nunca foi cadastrado manualmente) — a
    projeção simplesmente não está disponível nesse caso, sem erro.
    """
    ativo_ids, magento_ids = get_evento_ids(db, evento_grupo, ano)
    cadastro_ids: set = set()

    if magento_ids:
        rows = (
            db.query(CadastroEvento.id)
            .filter(
                CadastroEvento.id_evento_magento.in_(magento_ids),
                CadastroEvento.deleted_at.is_(None),
            )
            .all()
        )
        cadastro_ids.update(r[0] for r in rows)

    if ativo_ids:
        rows = (
            db.query(CadastroEvento.id)
            .filter(
                CadastroEvento.projeto_id.in_(ativo_ids),
                CadastroEvento.deleted_at.is_(None),
            )
            .all()
        )
        cadastro_ids.update(r[0] for r in rows)

    return list(cadastro_ids)


def get_projetado_por_canal(db: Session, evento_grupo: str, ano: int) -> Dict[str, int]:
    """
    Agrega a projeção de inscritos AO VIVO (reflete Corte 2 quando existir)
    por canal, usando o mapeamento área->canal (AREA_PARA_CANAL). Retorna
    {canal: quantidade}, com todos os CANAIS_DETALHE presentes (0 quando sem
    projeção). Áreas ativas fora do mapeamento são ignoradas na soma e
    logadas como aviso — nunca "adivinhamos" um canal para elas.
    """
    resultado: Dict[str, int] = {canal: 0 for canal in CANAIS_DETALHE}

    cadastro_ids = resolve_cadastro_evento_ids(db, evento_grupo, ano)
    if not cadastro_ids:
        return resultado

    rows = (
        db.query(AreaProjecao.nome, ProjecaoInscritos.quantidade)
        .join(ProjecaoInscritos, ProjecaoInscritos.area_projecao_id == AreaProjecao.id)
        .filter(
            ProjecaoInscritos.evento_id.in_(cadastro_ids),
            ProjecaoInscritos.deleted_at.is_(None),
        )
        .all()
    )

    areas_sem_mapeamento = set()
    for area_nome, quantidade in rows:
        canal = AREA_PARA_CANAL.get(area_nome)
        if canal is None:
            areas_sem_mapeamento.add(area_nome)
            continue
        resultado[canal] = resultado.get(canal, 0) + (quantidade or 0)

    if areas_sem_mapeamento:
        logger.warning(
            f"[ProjetadoPorCanal] evento_grupo={evento_grupo!r} ano={ano} tem projeção em "
            f"área(s) sem mapeamento de canal (ignorada na soma): {sorted(areas_sem_mapeamento)} "
            f"— atualizar AREA_PARA_CANAL em app/services/canal_mapping.py"
        )

    return resultado


def get_anos_evento(db: Session, evento_grupo: str) -> List[int]:
    """Retorna todos os anos (edições) cadastrados para o evento_grupo, desc."""
    rows = (
        db.query(SkuMapping.ano)
        .filter(
            SkuMapping.evento_grupo == evento_grupo,
            SkuMapping.ativo == True,
            SkuMapping.ano != None,
        )
        .distinct()
        .all()
    )
    return sorted({r[0] for r in rows}, reverse=True)


def resolve_ano_padrao(anos: List[int]) -> Optional[int]:
    """
    Resolve o ano padrão a exibir para um evento_grupo, mesmo critério usado
    no Dashboard (ano_atual): ano corrente se disponível, senão o mais recente.
    """
    if not anos:
        return None
    from datetime import date as _date
    current_year = _date.today().year
    return current_year if current_year in anos else anos[0]


def _anos_cobertos_pela_query_ao_vivo() -> Tuple[int, int]:
    """
    Espelha a janela de datas fixa usada em build_ativo_detalhe/build_magento_detalhe
    (b.dt_evento BETWEEN MAKEDATE(YEAR(CURDATE()),1) AND MAKEDATE(YEAR(CURDATE())+2,1)-1).
    Só edições com ano dentro dessa janela têm cobertura real na query ao vivo.
    """
    from datetime import date as _date
    current_year = _date.today().year
    return current_year, current_year + 1


def _ano_fora_da_janela_ao_vivo(ano: Optional[int]) -> bool:
    """
    True quando `ano` é uma edição que a query ao vivo NUNCA vai enxergar
    (fora da janela fixa current_year..current_year+1 do SQL). Uma edição
    assim só pode ser servida por um snapshot já existente (capturado quando
    aquele ano ainda estava dentro da janela) — nunca por uma query nova, que
    retornaria 0 mesmo com inscrições reais e corromperia o snapshot se salva.
    """
    if ano is None:
        return False
    ano_min, ano_max = _anos_cobertos_pela_query_ao_vivo()
    return not (ano_min <= ano <= ano_max)


def list_eventos_disponiveis(db: Session) -> List[Dict]:
    """
    Lista todos os evento_grupos com pelo menos um mapeamento ativo.

    Retorna nome canônico, evento_grupo (chave SKU), todos os anos cadastrados
    e, para cada ano, os IDs por banco daquela edição especifica (`edicoes`) —
    necessário porque cada edição pode ter IDs Ativo/Magento diferentes.
    """
    mappings = (
        db.query(SkuMapping)
        .filter(SkuMapping.ativo == True, SkuMapping.evento_grupo != None)
        .order_by(SkuMapping.evento_grupo, SkuMapping.ano.desc())
        .all()
    )

    grupos: Dict[str, Dict] = {}
    for m in mappings:
        eg = m.evento_grupo
        if not eg:
            continue
        if eg not in grupos:
            grupos[eg] = {
                "evento_grupo": eg,
                "nome_evento": m.nome_evento or eg,
                "skus": [],
                "anos": set(),
                "_edicoes": {},  # ano -> {ativo_ids: [...], magento_ids: [...]}
            }
        g = grupos[eg]
        if m.nome_evento and len(m.nome_evento) > len(g["nome_evento"]):
            g["nome_evento"] = m.nome_evento
        if m.sku and m.sku not in g["skus"]:
            g["skus"].append(m.sku)

        # Mapeamentos sem ano valem para TODAS as edições já conhecidas deste
        # grupo (mesma semântica OR ano IS NULL do get_evento_ids). Como a
        # ordenação é por ano DESC, quando chegamos numa linha ano=None todas
        # as edições concretas do grupo já foram vistas.
        anos_alvo = [m.ano] if m.ano is not None else list(g["anos"])
        if m.ano is not None:
            g["anos"].add(m.ano)
        for ano_alvo in anos_alvo:
            edicao = g["_edicoes"].setdefault(ano_alvo, {"ativo_ids": [], "magento_ids": []})
            if m.fonte == "ATIVO" and m.id_externo and m.id_externo not in edicao["ativo_ids"]:
                edicao["ativo_ids"].append(m.id_externo)
            elif m.fonte == "MAGENTO" and m.id_externo and m.id_externo not in edicao["magento_ids"]:
                edicao["magento_ids"].append(m.id_externo)

    result = []
    for g in grupos.values():
        anos_sorted = sorted(g["anos"], reverse=True)
        g["anos"] = anos_sorted
        g["edicoes"] = [
            {
                "ano": ano,
                "ativo_ids": g["_edicoes"].get(ano, {}).get("ativo_ids", []),
                "magento_ids": g["_edicoes"].get(ano, {}).get("magento_ids", []),
            }
            for ano in anos_sorted
        ]
        del g["_edicoes"]
        result.append(g)
    result.sort(key=lambda x: x["nome_evento"] or "")
    return result


# ---------------------------------------------------------------------------
# Fetch individual por banco (usa bind params via SQLAlchemy text())
# ---------------------------------------------------------------------------

def _fetch_ativo(
    ids: Optional[List[int]],
    ano_historico: Optional[int] = None,
) -> Tuple[Optional[List[Dict]], Optional[str]]:
    """
    ids=None  → query sem filtro (modo global sem evento_grupo selecionado)
    ids=[]    → evento selecionado mas sem IDs Ativo → retorna vazio, NÃO executa query
    ids=[...] → filtra pelos IDs fornecidos

    ano_historico: quando informado, usa janela de datas fixa para o ano
      histórico em vez da janela móvel ao vivo. Ver build_ativo_detalhe.
    """
    if isinstance(ids, list) and len(ids) == 0:
        logger.info("[DetalheEventos] Ativo: nenhum ID para este evento_grupo, retornando vazio")
        return [], None
    if db_module.engine_ssh is None:
        return None, "SSH tunnel não configurado"
    try:
        sql, params = build_ativo_detalhe(ids, ano_historico=ano_historico)
        logger.info(f"[DetalheEventos] Ativo query ids={ids} ano_historico={ano_historico}")
        with db_module.engine_ssh.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        logger.info(f"[DetalheEventos] Ativo: {len(rows)} linhas")
        return [_row_to_dict(r) for r in rows], None
    except Exception as e:
        logger.error(f"[DetalheEventos] Ativo error: {e}")
        return None, str(e)


def _fetch_magento(
    ids: Optional[List[int]],
    profile: str = "request",
    ano_historico: Optional[int] = None,
) -> Tuple[Optional[List[Dict]], Optional[str]]:
    """
    ids=None  → query sem filtro (modo global sem evento_grupo selecionado)
    ids=[]    → evento selecionado mas sem IDs Magento → retorna vazio, NÃO executa query
    ids=[...] → filtra pelos IDs fornecidos

    profile: "request" (padrão, para clicks de usuário — 2 tentativas, backoff curto)
             "background" (para batch noturno — 3 tentativas, backoff maior)

    ano_historico: quando informado, usa janela de datas fixa para o ano
      histórico em vez da janela móvel ao vivo. Ver build_magento_detalhe.
    """
    if isinstance(ids, list) and len(ids) == 0:
        logger.info("[DetalheEventos] Magento: nenhum ID para este evento_grupo, retornando vazio")
        return [], None
    if db_module.engine_magento is None:
        return None, "Magento não configurado"
    try:
        from app.core.db_retry import magento_run
        sql, params = build_magento_detalhe(ids, ano_historico=ano_historico)
        logger.info(f"[DetalheEventos] Magento query ids={ids} profile={profile} ano_historico={ano_historico}")

        t0 = time.time()

        def _work(conn):
            return conn.execute(text(sql), params).fetchall()

        rows = magento_run(_work, label="detalhe-eventos:fetch-magento", profile=profile)
        elapsed_ms = int((time.time() - t0) * 1000)
        dicts = [_row_to_dict(r) for r in rows]
        logger.info(
            f"[DetalheEventos] Magento: {len(dicts)} linhas em {elapsed_ms}ms "
            f"(limit=90000ms ids={ids})"
        )
        # Validation helper: log presence of shirt/produto columns in first row
        if dicts:
            first = dicts[0]
            shirt_val = first.get("tamanho_camiseta")
            prod_val = first.get("produtos")
            logger.info(
                f"[DetalheEventos] Magento colunas spot-check — "
                f"tamanho_camiseta={'presente' if shirt_val is not None else 'null/ausente'} "
                f"produtos={'presente' if prod_val is not None else 'null/ausente'}"
            )
        return dicts, None
    except Exception as e:
        logger.error(f"[DetalheEventos] Magento error: {e}")
        return None, str(e)


# ---------------------------------------------------------------------------
# Consolidação
# ---------------------------------------------------------------------------

def _build_canonical_map(db: Session) -> Dict[Tuple[str, int], str]:
    """
    Constrói mapa reverso (fonte.upper(), id_externo) → evento_grupo
    a partir de sku_mappings ativos.

    Utilizado para resolver a identidade canônica de cada linha raw
    retornada pelo Ativo/Magento antes de consolidar — garantindo que
    linhas de bancos diferentes que representam o MESMO evento se fundam
    pela chave canônica, não pelo id_externo individual.
    """
    mappings = (
        db.query(SkuMapping)
        .filter(SkuMapping.ativo == True, SkuMapping.evento_grupo != None)
        .all()
    )
    result: Dict[Tuple[str, int], str] = {}
    for m in mappings:
        if m.id_externo and m.fonte and m.evento_grupo:
            key = (m.fonte.upper(), int(m.id_externo))
            result[key] = m.evento_grupo
    return result


def _tag_canonical_grupo(
    rows: List[Dict],
    canonical_map: Dict[Tuple[str, int], str],
    default_grupo: Optional[str],
) -> None:
    """
    Enriquece cada linha in-place com `canonical_grupo` resolvido a partir do
    mapa reverso de sku_mappings. Quando não encontrado, usa `default_grupo`
    (evento_grupo da query, se for query de evento único) ou fallback
    para 'banco:id_evento' garantindo isolamento mínimo.
    """
    for row in rows:
        banco = (row.get("banco") or "").upper()
        id_ev = row.get("id_evento")
        try:
            id_ev_int = int(id_ev) if id_ev is not None else None
        except (ValueError, TypeError):
            id_ev_int = None

        resolved: Optional[str] = None
        if id_ev_int is not None:
            resolved = canonical_map.get((banco, id_ev_int))
        if resolved is None:
            resolved = default_grupo
        if resolved is None:
            # Último fallback: isolamento por banco+id evita cross-event merge
            resolved = f"__raw__{banco}_{id_ev}"
        row["canonical_grupo"] = resolved


def _consolidar(
    rows_ativo: List[Dict],
    rows_magento: List[Dict],
) -> List[Dict]:
    """
    Agrega todas as linhas por (canonical_grupo, DIM_KEYS).

    canonical_grupo é resolvido previamente via _tag_canonical_grupo() usando
    o mapa reverso de sku_mappings. Isso garante:
    - Linhas Ativo e Magento do MESMO evento canônico se fundem por dimensão.
    - Eventos distintos que coincidam em dimensões nunca são fundidos,
      independentemente de a query ser de evento único ou global sem filtro.
    """
    agg: Dict[tuple, Dict] = {}

    for row in (rows_ativo or []) + (rows_magento or []):
        canonical = row.get("canonical_grupo") or "__unknown__"
        dim_key = tuple(row.get(k) for k in DIM_KEYS)
        key = (canonical,) + dim_key

        if key not in agg:
            agg[key] = {k: row.get(k) for k in DIM_KEYS}
            agg[key]["canonical_grupo"] = canonical
            agg[key]["evento"] = row.get("evento")
            agg[key]["inscritos"] = 0
            agg[key]["receita_bruta"] = 0.0
            agg[key]["receita_liquida"] = 0.0
            agg[key]["bancos"] = []

        agg[key]["inscritos"] += row.get("inscritos") or 0
        agg[key]["receita_bruta"] += row.get("receita_bruta") or 0.0
        agg[key]["receita_liquida"] += row.get("receita_liquida") or 0.0

        banco = row.get("banco")
        if banco and banco not in agg[key]["bancos"]:
            agg[key]["bancos"].append(banco)

    consolidated = []
    for rec in agg.values():
        ins = rec["inscritos"]
        rec_liq = rec["receita_liquida"]
        rec["ticket_medio"] = round(rec_liq / ins, 2) if ins else 0.0
        rec["receita_bruta"] = round(rec["receita_bruta"], 2)
        rec["receita_liquida"] = round(rec_liq, 2)
        consolidated.append(rec)

    consolidated.sort(key=lambda r: (
        r.get("canal") or "",
        r.get("kit") or "",
        r.get("modalidade") or "",
        -(r.get("inscritos") or 0),
    ))
    return consolidated


# ---------------------------------------------------------------------------
# Canonicalização de nomes de kit via KitConfig.tipo_kit
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Regras de normalização de nomes brutos de kit (aplicadas como fallback
# quando o kit NÃO tem tipo_kit configurado no kit_config).
#
# Formato: lista de tuplas (regex_pattern, substituição).
# - A primeira regra que casar é aplicada; as demais são ignoradas.
# - Use grupos de captura (\1, \2…) na substituição quando precisar
#   preservar parte do nome original.
# - Para adicionar um novo padrão: inclua uma nova tupla ANTES do
#   comentário "# ── fim das regras ──" abaixo.
# ---------------------------------------------------------------------------
_KIT_NAME_PATTERNS: list = [
    # "DESCONTO PARA GRUPOS - 159,99" / "- 169.99" etc. → "Desconto Grupo"
    (r"(?i)^desconto\s+para\s+grupos?\s*[-–]\s*[\d.,]+\s*$", "Desconto Grupo"),
    # "DESCONTO PARA GRUPOS - CORTESIA" → "Desconto Grupo - Cortesia"
    (r"(?i)^desconto\s+para\s+grupos?\s*[-–]\s*cortesia\s*$", "Desconto Grupo - Cortesia"),
    # "DESCONTO PARA GRUPOS - PARTICIPAÇÃO" / "- PARTICIPACAO" → "Desconto Grupo - Participação"
    (r"(?i)^desconto\s+para\s+grupos?\s*[-–]\s*participa[cç][aã]o\s*$", "Desconto Grupo - Participação"),
    # "DESCONTO PARA GRUPOS - <outro sufixo>" → "Desconto Grupo - <sufixo capitalizado>"
    (r"(?i)^desconto\s+para\s+grupos?\s*[-–]\s*(.+)$", r"Desconto Grupo - \1"),
    # ── fim das regras ──
]
# Pré-compila os padrões uma única vez no import do módulo.
_KIT_NAME_PATTERNS_COMPILED: list = [
    (re.compile(pat), repl) for pat, repl in _KIT_NAME_PATTERNS
]


def _normalize_kit_raw(name: Optional[str]) -> str:
    """Trim + colapso de espaços internos com padrões de normalização.

    Aplicado como fallback para kits sem tipo_kit em kit_config.
    Os padrões em _KIT_NAME_PATTERNS são testados em ordem; o primeiro
    que casar substitui o nome inteiro. Se nenhum casar, devolve o nome
    com apenas trim + colapso de espaços.
    """
    if not name:
        return ""
    cleaned = re.sub(r"\s+", " ", name.strip())
    for pattern, repl in _KIT_NAME_PATTERNS_COMPILED:
        result = pattern.sub(repl, cleaned)
        if result != cleaned:
            return re.sub(r"\s+", " ", result).strip()
    return cleaned


def _build_kit_canonical_maps(
    db: Session,
    magento_event_ids: List[int],
) -> Tuple[Dict[Tuple, str], Dict[str, str]]:
    """
    Retorna dois dicionários de resolução canônica a partir de KitConfig:

    magento_map: {(id_evento_magento: int, kit_nome_raw: str) → tipo_kit}
        Chave baseia-se em KitConfig.id_evento (== Magento event ID) e
        KitConfig.kit_nome (== soi_parent.name nas linhas Magento).

    ativo_map: {ativo_categoria_raw: str → tipo_kit}
        Global (sem escopo de evento) porque linhas Ativo usam IDs do Ativo
        que não coincidem com KitConfig.id_evento (Magento).
        ativo_categoria pode conter múltiplas categorias separadas por vírgula.

    Entradas com tipo_kit NULL ou vazio são ignoradas.
    """
    magento_map: Dict[Tuple, str] = {}
    ativo_map: Dict[str, str] = {}

    # Join KitMappingSnapshot to resolve nome_kit (raw Magento bundle name)
    # when KitConfig.kit_nome is null (common — UI never sends it).
    query = (
        db.query(KitConfig, KitMappingSnapshot.nome_kit)
        .outerjoin(
            KitMappingSnapshot,
            KitMappingSnapshot.bundle_entity_id == KitConfig.bundle_entity_id,
        )
        .filter(
            KitConfig.tipo_kit.isnot(None),
            KitConfig.tipo_kit != "",
        )
    )
    if magento_event_ids:
        query = query.filter(KitConfig.id_evento.in_(magento_event_ids))

    for cfg, snap_nome_kit in query.all():
        tipo = cfg.tipo_kit.strip()
        if not tipo:
            continue
        # Mapa Magento: prefer KitConfig.kit_nome; fall back to KitMappingSnapshot.nome_kit
        bundle_name = (cfg.kit_nome or snap_nome_kit or "").strip()
        if cfg.id_evento is not None and bundle_name:
            magento_map[(int(cfg.id_evento), bundle_name)] = tipo
        # Mapa Ativo: ativo_categoria → tipo_kit (pode ter múltiplos separados por vírgula)
        if cfg.ativo_categoria:
            for cat in cfg.ativo_categoria.replace("\n", ",").split(","):
                cat = cat.strip()
                if cat and cat not in ativo_map:
                    ativo_map[cat] = tipo

    return magento_map, ativo_map


def _apply_canonical_kit(
    rows: List[Dict],
    magento_map: Dict[Tuple, str],
    ativo_map: Dict[str, str],
) -> None:
    """
    Resolve o nome canônico de kit para cada linha, *in-place*.

    Linhas Magento: lookup via (id_evento, kit.strip()) no magento_map.
    Linhas Ativo:   lookup via kit.strip() no ativo_map.
    Fallback: _normalize_kit_raw (trim + colapso de espaços).
    """
    for row in rows:
        raw = row.get("kit") or ""
        banco = row.get("banco") or ""
        canonical: Optional[str] = None

        if banco == "Magento" and magento_map:
            try:
                ev_id = int(row.get("id_evento") or 0)
            except (ValueError, TypeError):
                ev_id = 0
            canonical = magento_map.get((ev_id, raw.strip()))
        elif banco == "Ativo" and ativo_map:
            canonical = ativo_map.get(raw.strip())

        row["kit"] = canonical if canonical else _normalize_kit_raw(raw)


def _check_divergencias(
    consolidado: List[Dict],
    rows_ativo: List[Dict],
    rows_magento: List[Dict],
) -> List[Dict]:
    """
    Para cada combinação (canonical_grupo + DIM_KEYS), verifica se a soma
    das linhas brutas por banco coincide com o total consolidado.

    Agrega por (canonical_grupo, DIM_KEYS, banco) via SUM para evitar
    false-divergence quando múltiplos IDs do mesmo banco compartilham
    as mesmas dimensões (ex: dois IDs Ativo no mesmo evento).
    """
    # Acumula totais por (canonical_grupo, *DIM_KEYS, banco)
    bank_sums: Dict[tuple, Dict[str, float]] = defaultdict(lambda: {"inscritos": 0.0, "receita_liquida": 0.0})

    for row in (rows_ativo or []) + (rows_magento or []):
        canonical = row.get("canonical_grupo") or "__unknown__"
        agg_key = (canonical,) + tuple(row.get(k) for k in DIM_KEYS)
        banco = row.get("banco", "?")
        slot_key = agg_key + (banco,)
        bank_sums[slot_key]["inscritos"] += row.get("inscritos") or 0
        bank_sums[slot_key]["receita_liquida"] += row.get("receita_liquida") or 0.0

    # Para cada linha consolidada, soma todos os bancos sob a mesma chave canônica
    divergencias = []
    for rec in consolidado:
        canonical = rec.get("canonical_grupo") or "__unknown__"
        agg_key = (canonical,) + tuple(rec.get(k) for k in DIM_KEYS)

        soma_ins = 0.0
        soma_liq = 0.0
        for slot_key, totals in bank_sums.items():
            # slot_key = (canonical, *DIM_KEYS, banco) — prefix must match agg_key
            if slot_key[:len(agg_key)] == agg_key:
                soma_ins += totals["inscritos"]
                soma_liq += totals["receita_liquida"]

        diff_ins = abs(soma_ins - (rec.get("inscritos") or 0))
        diff_liq = abs(soma_liq - (rec.get("receita_liquida") or 0.0))

        if diff_ins > 0.5 or diff_liq > 0.01:
            divergencias.append({
                "dimensoes": {k: rec.get(k) for k in DIM_KEYS},
                "consolidado_inscritos": rec.get("inscritos"),
                "soma_bancos_inscritos": int(soma_ins),
                "diff_inscritos": int(diff_ins),
                "consolidado_receita_liquida": rec.get("receita_liquida"),
                "soma_bancos_receita_liquida": round(soma_liq, 2),
                "diff_receita_liquida": round(diff_liq, 2),
            })
    return divergencias


# ---------------------------------------------------------------------------
# Snapshot PostgreSQL (leitura / escrita)
# ---------------------------------------------------------------------------

def _read_snapshot_raw(db: Session, evento_grupo: str, ano: int) -> Optional[Tuple[Dict, datetime, float]]:
    """
    Lê o snapshot do PostgreSQL independente da idade.
    Retorna (payload_dict, updated_at, age_hours) se existir, None se não existir.
    O chamador decide se o snapshot é fresco ou stale.
    """
    try:
        from app.models.vendas_snapshot import DetalheEventosSnapshot
        row = (
            db.query(DetalheEventosSnapshot)
            .filter(
                DetalheEventosSnapshot.evento_grupo == evento_grupo,
                DetalheEventosSnapshot.ano == ano,
            )
            .first()
        )
        if row is None:
            return None
        now_utc = datetime.now(timezone.utc)
        updated = row.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age_h = (now_utc - updated).total_seconds() / 3600
        payload_dict = json.loads(row.payload)
        return payload_dict, updated, age_h
    except Exception as e:
        logger.warning(f"[DetalheSnap] Erro ao ler snapshot de '{evento_grupo}'/{ano}: {e}")
        return None


def _read_snapshot(db: Session, evento_grupo: str, ano: int) -> Optional[Tuple[Dict, datetime]]:
    """
    Lê o snapshot do PostgreSQL para o evento_grupo/ano.
    Retorna (payload_dict, updated_at) se válido (< SNAPSHOT_MAX_AGE_HOURS), None caso contrário.
    """
    result = _read_snapshot_raw(db, evento_grupo, ano)
    if result is None:
        return None
    payload_dict, updated, age_h = result
    if age_h > SNAPSHOT_MAX_AGE_HOURS:
        logger.debug(f"[DetalheSnap] snapshot de '{evento_grupo}'/{ano} tem {age_h:.1f}h — ignorando (>{SNAPSHOT_MAX_AGE_HOURS}h)")
        return None
    return payload_dict, updated


def _fallback_rows_from_snapshot(
    db: Session, evento_grupo: str, ano: int, banco: str
) -> Tuple[Optional[List[Dict]], Optional[datetime]]:
    """
    Busca as linhas de UM banco (Ativo ou Magento) no snapshot mais recente
    salvo para (evento_grupo, ano), independente da idade.

    Usado para preencher a lacuna quando a busca AO VIVO desse banco falha
    mas a do outro banco funciona — em vez de tratar a contribuição do banco
    falho como zero, reaproveita o último dado bom conhecido daquele banco.

    Retorna (rows, snapshot_updated_at). Ambos None se não existir nenhum
    snapshot para essa edição (nada disponível para usar como fallback).
    """
    snap_raw = _read_snapshot_raw(db, evento_grupo, ano)
    if snap_raw is None:
        return None, None
    payload_dict, updated_at, _age_h = snap_raw
    rows = (payload_dict.get("por_banco") or {}).get(banco) or []
    return rows, updated_at


def _trigger_background_refresh(evento_grupo: str, ano: int) -> None:
    """
    Dispara um refresh ao vivo para evento_grupo/ano em background (thread daemon).
    Não faz nada se já houver um refresh em andamento para a mesma edição.
    Não dispara para edições fora da janela ao vivo (anos históricos): nesses
    casos o snapshot é frozen — só um force_refresh explícito do usuário o atualiza.
    Cria sua própria sessão de banco — não bloqueia o request atual.
    """
    if _ano_fora_da_janela_ao_vivo(ano):
        logger.debug(
            f"[DetalheSnap SWR] Refresh background ignorado para '{evento_grupo}'/{ano} "
            "— ano histórico (fora da janela ao vivo); snapshot é frozen"
        )
        return
    cache_key = (evento_grupo, ano)
    with _inflight_lock:
        if cache_key in _inflight:
            logger.debug(
                f"[DetalheSnap SWR] Refresh background ignorado para '{evento_grupo}'/{ano} "
                "— outro já está em andamento"
            )
            return

    def _bg() -> None:
        from app.core.database import SessionLocal
        db_bg = SessionLocal()
        try:
            logger.info(f"[DetalheSnap SWR] Iniciando refresh background para '{evento_grupo}'/{ano}")
            get_detalhe(db_bg, evento_grupo, ano, force_refresh=True)
            logger.info(f"[DetalheSnap SWR] Refresh background concluído para '{evento_grupo}'/{ano}")
        except Exception as _e:
            logger.warning(
                f"[DetalheSnap SWR] Refresh background falhou para '{evento_grupo}'/{ano}: {_e}"
            )
        finally:
            try:
                db_bg.close()
            except Exception:
                pass

    t = threading.Thread(
        target=_bg,
        name=f"detalhe-swr-{evento_grupo}-{ano}",
        daemon=True,
    )
    t.start()


# Versão da estrutura da query. Quando alterada, o startup descarta todos os
# snapshots calculados com a versão anterior, garantindo que contagens obsoletas
# não sejam servidas após deploys que mudam a lógica de contagem.
DETALHE_QUERY_VERSION = "v4"  # v4: snapshot agora é por (evento_grupo, ano) em vez de só evento_grupo


def maybe_flush_snapshots_on_version_change(db: Session) -> None:
    """Descarta todos os snapshots de detalhe se a versão da query mudou.

    Usa uma linha sentinela (evento_grupo='__version__') na própria tabela para
    rastrear a última versão computada sem precisar de tabela extra.

    Comportamento por reinicialização:
    - Versão bate     → nenhuma operação (caminho rápido).
    - Versão diverge  → DELETE de todos os snapshots reais + UPSERT da sentinela.
    Snapshots são recriados lazily no primeiro acesso (SWR) ou pelo job noturno.
    """
    from app.models.vendas_snapshot import DetalheEventosSnapshot
    try:
        marker = (
            db.query(DetalheEventosSnapshot)
            .filter(DetalheEventosSnapshot.evento_grupo == "__version__")
            .first()
        )
        stored_version: Optional[str] = None
        if marker:
            try:
                stored_version = json.loads(marker.payload).get("version")
            except Exception:
                pass

        if stored_version == DETALHE_QUERY_VERSION:
            logger.info(
                f"[DetalheSnap] Version check OK ({DETALHE_QUERY_VERSION}) — snapshots válidos"
            )
            return

        # Versão diferente: descarta todos os snapshots reais
        deleted = (
            db.query(DetalheEventosSnapshot)
            .filter(DetalheEventosSnapshot.evento_grupo != "__version__")
            .delete(synchronize_session=False)
        )

        now_utc = datetime.now(timezone.utc)
        version_payload = json.dumps({"version": DETALHE_QUERY_VERSION})
        if marker:
            marker.payload = version_payload
            marker.updated_at = now_utc
        else:
            db.add(DetalheEventosSnapshot(
                evento_grupo="__version__",
                ano=0,
                payload=version_payload,
                created_at=now_utc,
                updated_at=now_utc,
            ))

        db.commit()

        # Limpa também o cache em memória para que não sirva dados da versão antiga
        with _cache_lock:
            _cache.clear()

        logger.info(
            f"[DetalheSnap] {deleted} snapshot(s) descartado(s) "
            f"(mudança de versão: {stored_version!r} → {DETALHE_QUERY_VERSION!r}). "
            "Snapshots serão recriados no próximo acesso."
        )
    except Exception as e:
        logger.error(f"[DetalheSnap] maybe_flush_snapshots_on_version_change falhou: {e}")
        try:
            db.rollback()
        except Exception:
            pass


def save_snapshot(db: Session, evento_grupo: str, ano: int, payload: Dict) -> bool:
    """
    Persiste o payload no snapshot PostgreSQL via UPSERT, escopado por (evento_grupo, ano).
    Retorna True em sucesso, False em falha (não lança).
    """
    try:
        from app.models.vendas_snapshot import DetalheEventosSnapshot
        payload_json = json.dumps(payload, ensure_ascii=False, default=str)
        now_utc = datetime.now(timezone.utc)

        existing = (
            db.query(DetalheEventosSnapshot)
            .filter(
                DetalheEventosSnapshot.evento_grupo == evento_grupo,
                DetalheEventosSnapshot.ano == ano,
            )
            .first()
        )
        if existing:
            existing.payload = payload_json
            existing.updated_at = now_utc
        else:
            db.add(DetalheEventosSnapshot(
                evento_grupo=evento_grupo,
                ano=ano,
                payload=payload_json,
                created_at=now_utc,
                updated_at=now_utc,
            ))
        db.commit()
        logger.info(f"[DetalheSnap] Snapshot salvo para '{evento_grupo}'/{ano}")
        return True
    except Exception as e:
        logger.error(f"[DetalheSnap] Erro ao salvar snapshot de '{evento_grupo}'/{ano}: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# API pública do serviço
# ---------------------------------------------------------------------------

def get_detalhe(
    db: Session,
    evento_grupo: Optional[str],
    ano: Optional[int] = None,
    force_refresh: bool = False,
) -> Dict:
    """
    Retorna o payload completo de detalhamento para a edição (evento_grupo, ano).

    `ano` é obrigatório sempre que `evento_grupo` é informado — cada edição do
    evento (ex.: 2026 e 2027) tem seu próprio cache, snapshot e dados. Quando
    evento_grupo é None ("modo global"), ano é ignorado.

    Ordem de leitura (padrão SWR — stale-while-revalidate):
    1. Cache em memória (TTL 15min) — bypass se force_refresh.
    2. Snapshot PostgreSQL (qualquer idade):
       - Fresco (< SNAPSHOT_MAX_AGE_HOURS): retorna imediatamente.
       - Stale (>= SNAPSHOT_MAX_AGE_HOURS): retorna imediatamente com
         snapshot_stale=True e dispara refresh em background (sem bloquear
         o usuário). O cache em memória é populado com o dado stale por 15min;
         após esse tempo, a próxima leitura pega o snapshot já atualizado.
       - Ausente: cai na query ao vivo.
       - Bypass completo se force_refresh=True.
    3. Query ao vivo (Ativo + Magento) — salva no snapshot e no cache.
       Single-flight guard via _inflight: segundo force_refresh simultâneo
       para o mesmo evento recebe HTTP 429.

    Campos adicionais no retorno:
    - source: "cache" | "snapshot" | "live"
    - snapshot_updated_at: ISO string com data/hora do snapshot
    - snapshot_stale: True se o snapshot estava expirado ao ser servido
    """
    if evento_grupo and ano is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="ano é obrigatório quando evento_grupo é informado.")

    ano_fora_da_janela = bool(evento_grupo) and _ano_fora_da_janela_ao_vivo(ano)
    # force_refresh É honrado para anos históricos — a query histórica usa
    # janela fixada em 'ano' (não CURDATE()) e retorna dados reais do período.
    # O único guard automático é _trigger_background_refresh, que ignora anos
    # históricos (snapshot frozen — só force_refresh explícito do usuário atualiza).

    cache_key = (evento_grupo or "__all__", ano)

    if not force_refresh:
        # 1. Cache em memória
        with _cache_lock:
            entry = _cache.get(cache_key)
        if entry:
            ts, data = entry
            if time.time() - ts < CACHE_TTL_SECONDS:
                logger.debug(f"[DetalheEventos] cache HIT key={cache_key}")
                return data

        # 2. Snapshot PostgreSQL com padrão SWR (stale-while-revalidate).
        #    Apenas para evento único — "__all__" não tem snapshot por chave.
        if evento_grupo:
            snap_raw = _read_snapshot_raw(db, evento_grupo, ano)
            if snap_raw is not None:
                payload_dict, updated_at, age_h = snap_raw

                # Re-apply canonical kit names so alias changes in KitConfig
                # are reflected immediately without waiting for the next live refresh.
                try:
                    por_banco = payload_dict.get("por_banco") or {}
                    rows_ativo_snap = por_banco.get("Ativo") or []
                    rows_magento_snap = por_banco.get("Magento") or []
                    magento_ids_snap = list({
                        int(r["id_evento"])
                        for r in rows_magento_snap
                        if r.get("id_evento")
                    })
                    km_snap, ka_snap = _build_kit_canonical_maps(db, magento_ids_snap)
                    _apply_canonical_kit(rows_ativo_snap, km_snap, ka_snap)
                    _apply_canonical_kit(rows_magento_snap, km_snap, ka_snap)
                    _apply_dimension_aliases(rows_ativo_snap, db)
                    _apply_dimension_aliases(rows_magento_snap, db)
                    payload_dict["consolidado"] = _consolidar(rows_ativo_snap, rows_magento_snap)
                    payload_dict["totais"] = _calc_totais(payload_dict["consolidado"])
                except Exception as _kit_err:
                    logger.warning(f"[DetalheSnap] Erro ao re-aplicar kit names no snapshot: {_kit_err}")

                payload_dict["source"] = "snapshot"
                payload_dict["snapshot_updated_at"] = updated_at.isoformat()

                # Projeção é sempre recalculada ao vivo, independente da idade do
                # snapshot de inscrições: os dois conjuntos de dados evoluem em
                # ritmos diferentes (projeção muda por edição manual, não por
                # sincronização noturna) e a query é leve (poucas linhas, por PK).
                try:
                    payload_dict["projetado_por_canal"] = get_projetado_por_canal(db, evento_grupo, ano)
                except Exception as _proj_err:
                    logger.warning(f"[DetalheSnap] Erro ao calcular projetado_por_canal: {_proj_err}")
                    payload_dict["projetado_por_canal"] = {}

                if age_h <= SNAPSHOT_MAX_AGE_HOURS:
                    # Snapshot fresco: retorna imediatamente
                    payload_dict["snapshot_stale"] = False
                    with _cache_lock:
                        _cache[cache_key] = (time.time(), payload_dict)
                    logger.info(
                        f"[DetalheSnap] Fresh snapshot para '{evento_grupo}' "
                        f"({age_h:.1f}h, atualizado {updated_at.isoformat()})"
                    )
                    return payload_dict
                elif _ano_fora_da_janela_ao_vivo(ano):
                    # Snapshot histórico frozen: o job noturno não o recomputa.
                    # Snapshots de anos passados não mudam de forma significativa;
                    # o admin pode forçar um recalculo via force_refresh=True, que
                    # usará a query com janela fixada em 'ano' (ano_historico).
                    # Auto-refresh em background NUNCA é disparado para anos históricos
                    # (ver _trigger_background_refresh).
                    payload_dict["snapshot_stale"] = False
                    payload_dict["fora_da_janela_ao_vivo"] = True
                    with _cache_lock:
                        _cache[cache_key] = (time.time(), payload_dict)
                    logger.info(
                        f"[DetalheSnap] Snapshot histórico frozen para "
                        f"'{evento_grupo}'/{ano} ({age_h:.1f}h) — servindo sem "
                        "acionar refresh automático"
                    )
                    return payload_dict
                else:
                    # Snapshot stale: retorna imediatamente + dispara refresh em background.
                    # O usuário vê o dado anterior sem esperar; o refresh atualiza o cache.
                    payload_dict["snapshot_stale"] = True
                    with _cache_lock:
                        _cache[cache_key] = (time.time(), payload_dict)
                    logger.info(
                        f"[DetalheSnap SWR] Stale snapshot para '{evento_grupo}'/{ano} "
                        f"({age_h:.1f}h > {SNAPSHOT_MAX_AGE_HOURS}h) — "
                        "servindo dado anterior + refresh em background"
                    )
                    _trigger_background_refresh(evento_grupo, ano)
                    return payload_dict

    # 3. Query ao vivo (ou histórica) — single-flight guard.
    # Para anos dentro da janela: query ao vivo usando CURDATE() como âncora.
    # Para anos fora da janela (históricos): query com janela fixada em 'ano'
    #   via ano_historico, retornando os dados reais da edição histórica.
    # Em ambos os casos o resultado é salvo no snapshot PostgreSQL.
    # Quando force_refresh=True e outro request já está executando as queries
    # pesadas para o mesmo evento_grupo, serve o dado em cache/snapshot com
    # refresh_in_progress=True (sem levantar 429), para que o frontend possa
    # mostrar dados e re-poll automático quando o refresh terminar.
    if force_refresh and evento_grupo:
        with _inflight_lock:
            if cache_key in _inflight:
                logger.info(
                    f"[DetalheEventos] force_refresh bloqueado para '{evento_grupo}'/{ano} — "
                    "já há uma consulta ao vivo em andamento; servindo dado em cache (single-flight)"
                )
                # Tenta cache em memória primeiro
                with _cache_lock:
                    entry = _cache.get(cache_key)
                if entry:
                    _, cached_data = entry
                    return {**cached_data, "refresh_in_progress": True}
                # Tenta snapshot PostgreSQL usando sessão independente —
                # a `db` do request pode estar em estado inválido quando há
                # stress no pool, e uma sessão limpa garante que o snapshot
                # seja encontrado mesmo nesse cenário.
                from app.core.database import SessionLocal
                db_snap = SessionLocal()
                try:
                    snap_raw = _read_snapshot_raw(db_snap, evento_grupo, ano)
                finally:
                    db_snap.close()
                if snap_raw is not None:
                    payload_dict, updated_at, age_h = snap_raw
                    payload_dict["source"] = "snapshot"
                    payload_dict["snapshot_updated_at"] = updated_at.isoformat()
                    payload_dict["snapshot_stale"] = True
                    payload_dict["refresh_in_progress"] = True
                    return payload_dict
                # Último recurso: sem dado nenhum disponível — retorna 202
                # para que o frontend faça re-poll automático.
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=202,
                    detail=(
                        "Atualização em andamento — aguarde alguns instantes."
                    ),
                )
            _inflight.add(cache_key)

    try:
        ativo_ids: Optional[List[int]] = None
        magento_ids: Optional[List[int]] = None
        evento_nome: Optional[str] = None
        skus: List[str] = []

        if evento_grupo:
            ativo_ids_list, magento_ids_list = get_evento_ids(db, evento_grupo, ano)

            # IMPORTANT: keep empty list as [] — do NOT convert to None.
            # _fetch_ativo/magento(ids=[]) → returns empty rows immediately.
            # _fetch_ativo/magento(ids=None) → unfiltered full-year query (global mode only).
            # Converting [] to None would silently run full-year queries for an event
            # that simply has no IDs registered for one bank.
            ativo_ids = ativo_ids_list      # [] or [id, ...]
            magento_ids = magento_ids_list  # [] or [id, ...]

            # Reject unknown evento_grupo: if BOTH banks have zero IDs, the group
            # doesn't exist (or has no active mappings). Raise explicitly.
            if len(ativo_ids) == 0 and len(magento_ids) == 0:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=404,
                    detail=f"evento_grupo '{evento_grupo}' não encontrado ou sem mapeamentos ativos em sku_mappings.",
                )

            mapping = (
                db.query(SkuMapping)
                .filter(SkuMapping.evento_grupo == evento_grupo, SkuMapping.ativo == True)
                .first()
            )
            if mapping:
                evento_nome = mapping.nome_evento
                skus_q = (
                    db.query(SkuMapping.sku)
                    .filter(SkuMapping.evento_grupo == evento_grupo, SkuMapping.ativo == True)
                    .all()
                )
                skus = [s[0] for s in skus_q if s[0]]

        rows_ativo: Optional[List[Dict]] = None
        rows_magento: Optional[List[Dict]] = None
        error_ativo: Optional[str] = None
        error_magento: Optional[str] = None

        # Build canonical map BEFORE fetching (lightweight PG query)
        canonical_map = _build_canonical_map(db)

        # Para anos históricos, fixa a janela de datas em 'ano' em vez de
        # usar CURDATE() (que jamais enxergaria uma edição passada).
        _ano_hist = ano if ano_fora_da_janela else None

        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_ativo = executor.submit(_fetch_ativo, ativo_ids, _ano_hist)
            fut_magento = executor.submit(
                _fetch_magento, magento_ids, "request", _ano_hist
            )

            rows_ativo, error_ativo = fut_ativo.result()
            rows_magento, error_magento = fut_magento.result()

        # Fallback por banco: quando só UM dos dois bancos falha ao vivo,
        # preenche a lacuna com o snapshot mais recente salvo para esta
        # edição, em vez de tratar a contribuição do banco falho como zero.
        # Quando os DOIS falham, mantém o comportamento atual — não há
        # nenhum lado "bom" ao vivo para validar contra o fallback, e o
        # payload inteiro já não será persistido (ver guard de save abaixo).
        fallback_bancos: Dict[str, str] = {}
        if evento_grupo and (error_ativo or error_magento) and not (error_ativo and error_magento):
            if error_ativo and rows_ativo is None:
                fb_rows, fb_updated = _fallback_rows_from_snapshot(db, evento_grupo, ano, "Ativo")
                if fb_rows is not None and fb_updated is not None:
                    rows_ativo = fb_rows
                    fallback_bancos["Ativo"] = fb_updated.isoformat()
                    logger.info(
                        f"[DetalheEventos] Ativo falhou ao vivo ('{error_ativo}') para "
                        f"'{evento_grupo}'/{ano} — completando com snapshot de "
                        f"{fb_updated.isoformat()} ({len(fb_rows)} linhas)"
                    )
            if error_magento and rows_magento is None:
                fb_rows, fb_updated = _fallback_rows_from_snapshot(db, evento_grupo, ano, "Magento")
                if fb_rows is not None and fb_updated is not None:
                    rows_magento = fb_rows
                    fallback_bancos["Magento"] = fb_updated.isoformat()
                    logger.info(
                        f"[DetalheEventos] Magento falhou ao vivo ('{error_magento}') para "
                        f"'{evento_grupo}'/{ano} — completando com snapshot de "
                        f"{fb_updated.isoformat()} ({len(fb_rows)} linhas)"
                    )

        # Tag each row with its canonical_grupo before consolidating
        _tag_canonical_grupo(rows_ativo or [], canonical_map, evento_grupo)
        _tag_canonical_grupo(rows_magento or [], canonical_map, evento_grupo)

        # Normaliza modalidade em todas as rows (regex de km + lowercase)
        for row in (rows_ativo or []):
            if row.get("modalidade"):
                row["modalidade"] = _normalize_modalidade(row["modalidade"])
        for row in (rows_magento or []):
            if row.get("modalidade"):
                row["modalidade"] = _normalize_modalidade(row["modalidade"])

        # Resolve canonical kit names via KitConfig.tipo_kit (lightweight PG query).
        # Magento rows look up by (id_evento, kit_nome); Ativo rows by ativo_categoria.
        # Falls back to normalized raw name when tipo_kit is not configured.
        kit_mapa_magento, kit_mapa_ativo = _build_kit_canonical_maps(db, magento_ids)
        _apply_canonical_kit(rows_ativo or [], kit_mapa_magento, kit_mapa_ativo)
        _apply_canonical_kit(rows_magento or [], kit_mapa_magento, kit_mapa_ativo)
        _apply_dimension_aliases(rows_ativo or [], db)
        _apply_dimension_aliases(rows_magento or [], db)

        consolidado = _consolidar(rows_ativo or [], rows_magento or [])
        divergencias = _check_divergencias(consolidado, rows_ativo or [], rows_magento or [])

        payload = {
            "evento_grupo": evento_grupo,
            "ano": ano,
            "nome_evento": evento_nome,
            "skus": skus,
            "consolidado": consolidado,
            "por_banco": {
                "Ativo": rows_ativo or [],
                "Magento": rows_magento or [],
            },
            "divergencias": divergencias,
            "erros": {
                k: v for k, v in [("Ativo", error_ativo), ("Magento", error_magento)] if v
            },
            "fallback_bancos": fallback_bancos,
            "totais": _calc_totais(consolidado),
            "projetado_por_canal": (
                get_projetado_por_canal(db, evento_grupo, ano) if evento_grupo and ano else {}
            ),
            "source": "live",
            "snapshot_updated_at": None,
        }

        # Salva no snapshot PostgreSQL (apenas evento único). NUNCA persiste uma
        # versão em que um banco falhou sem fallback disponível — isso
        # sobrescreveria um snapshot bom com dados incompletos. Quando o
        # fallback (acima) preencheu a lacuna, salva a versão já complementada,
        # mas sem os campos de erro/fallback transitórios: eles valem só para
        # esta resposta ao vivo, não devem "grudar" indefinidamente no registro
        # persistido já que os dados em si ficaram completos.
        ativo_sem_dado = bool(error_ativo) and "Ativo" not in fallback_bancos
        magento_sem_dado = bool(error_magento) and "Magento" not in fallback_bancos

        snap_saved = False
        if evento_grupo and not ativo_sem_dado and not magento_sem_dado:
            if fallback_bancos:
                snapshot_payload = dict(payload)
                snapshot_payload["erros"] = {}
                snapshot_payload["fallback_bancos"] = {}
                snap_saved = save_snapshot(db, evento_grupo, ano, snapshot_payload)
            else:
                snap_saved = save_snapshot(db, evento_grupo, ano, payload)
            if snap_saved:
                payload["snapshot_updated_at"] = datetime.now(timezone.utc).isoformat()

        # Validation summary log — searchable in production to confirm all criteria:
        # • rows from Magento (confirms query ran and returned data)
        # • elapsed visible in the per-bank log above (< 90000ms)
        # • snapshot created (confirms badge will show "Snapshot" on next load)
        magento_rows = len(rows_magento) if rows_magento else 0
        logger.info(
            f"[DetalheEventos] live query concluída — evento_grupo={evento_grupo!r} "
            f"consolidado={len(consolidado)} linhas "
            f"magento_rows={magento_rows} "
            f"erros={list(payload['erros'].keys()) or 'nenhum'} "
            f"fallback={list(fallback_bancos.keys()) or 'nenhum'} "
            f"snapshot={'salvo' if snap_saved else 'não salvo'}"
        )

        with _cache_lock:
            _cache[cache_key] = (time.time(), payload)

        return payload

    finally:
        # Libera o slot de single-flight (se foi adquirido) independente de sucesso ou erro.
        if force_refresh and evento_grupo:
            with _inflight_lock:
                _inflight.discard(cache_key)


def _calc_totais(consolidado: List[Dict]) -> Dict:
    total_ins = sum(r.get("inscritos") or 0 for r in consolidado)
    total_bruta = sum(r.get("receita_bruta") or 0.0 for r in consolidado)
    total_liq = sum(r.get("receita_liquida") or 0.0 for r in consolidado)
    ticket = round(total_liq / total_ins, 2) if total_ins else 0.0

    por_canal: Dict[str, Dict] = {}
    for r in consolidado:
        canal = r.get("canal") or "—"
        if canal not in por_canal:
            por_canal[canal] = {"inscritos": 0, "receita_liquida": 0.0}
        por_canal[canal]["inscritos"] += r.get("inscritos") or 0
        por_canal[canal]["receita_liquida"] += r.get("receita_liquida") or 0.0

    return {
        "inscritos": total_ins,
        "receita_bruta": round(total_bruta, 2),
        "receita_liquida": round(total_liq, 2),
        "ticket_medio": ticket,
        "por_canal": por_canal,
    }


def invalidate_cache(evento_grupo: Optional[str] = None, ano: Optional[int] = None) -> None:
    """
    Limpa o cache em memória.
    - evento_grupo + ano: remove só aquela edição.
    - só evento_grupo: remove TODAS as edições (anos) conhecidas daquele grupo
      (usado por invalidações amplas, ex.: mudança de KitConfig, que afeta todas
      as edições do evento).
    - nenhum: limpa tudo.
    """
    with _cache_lock:
        if evento_grupo and ano is not None:
            _cache.pop((evento_grupo, ano), None)
        elif evento_grupo:
            for key in [k for k in _cache if k[0] == evento_grupo]:
                _cache.pop(key, None)
        else:
            _cache.clear()
