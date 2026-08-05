"""Testes do fallback por banco (Ativo/Magento) em detalhe_eventos_service.get_detalhe.

Bug (task #252): quando UM banco (Ativo ou Magento) falha na busca ao vivo mas o
outro funciona, o Painel do Evento tratava a contribuição do banco falho como
zero em vez de reaproveitar o último snapshot bom conhecido — subestimando os
totais e, pior, deixando esse resultado parcial sobrescrever um snapshot
persistido completo.

Cenários cobertos (mesma redação do "Done looks like" da tarefa):
1. Um banco funciona ao vivo, o outro falha mas tem snapshot -> total inclui
   as duas contribuições e a resposta indica banco+timestamp do fallback.
2. Os dois bancos falham -> comportamento atual preservado: nada é
   preenchido, nada é persistido (snapshot existente não é tocado).
3. Um banco falha e não há snapshot anterior para aquela edição ->
   comportamento atual preservado: resultado parcial + erro cru, e o
   resultado incompleto não é persistido como se fosse o snapshot completo.
"""
import os
import sys

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — registra todos os mappers antes de usar os models
from app.core.database import Base
from app.models.dimensoes import SkuMapping
from app.models.vendas_snapshot import DetalheEventosSnapshot
import app.services.detalhe_eventos_service as svc

ANO = datetime.now().year


@pytest.fixture()
def db():
    """Sessão isolada por teste: engine SQLite em memória, fresco a cada teste."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_mappings(db, grupo, ativo_id=101, magento_id=202):
    db.add(SkuMapping(
        fonte="ATIVO", id_externo=ativo_id, sku=f"{grupo}-ATIVO",
        evento_grupo=grupo, ano=ANO, nome_evento=grupo, ativo=True,
    ))
    db.add(SkuMapping(
        fonte="MAGENTO", id_externo=magento_id, sku=f"{grupo}-MAGENTO",
        evento_grupo=grupo, ano=ANO, nome_evento=grupo, ativo=True,
    ))
    db.commit()


def _row(banco, id_evento, inscritos, receita, evento):
    return {
        "banco": banco, "id_evento": id_evento, "evento": evento,
        "canal": "Site", "kit": "Kit Único", "modalidade": "5km",
        "pelotao": None, "produtos": None, "tamanho_camiseta": None,
        "inscritos": inscritos, "receita_bruta": receita, "receita_liquida": receita,
        "ticket_medio": (receita / inscritos) if inscritos else 0.0,
    }


def _seed_snapshot(db, grupo, ativo_rows, magento_rows):
    payload = {
        "evento_grupo": grupo, "ano": ANO, "nome_evento": grupo, "skus": [],
        "consolidado": [], "por_banco": {"Ativo": ativo_rows, "Magento": magento_rows},
        "divergencias": [], "erros": {}, "fallback_bancos": {}, "totais": {},
    }
    ts = datetime.now(timezone.utc)
    db.add(DetalheEventosSnapshot(
        evento_grupo=grupo, ano=ANO, payload=json.dumps(payload, default=str),
        created_at=ts, updated_at=ts,
    ))
    db.commit()


def _get_snapshot_row(db, grupo):
    return (
        db.query(DetalheEventosSnapshot)
        .filter(DetalheEventosSnapshot.evento_grupo == grupo, DetalheEventosSnapshot.ano == ANO)
        .first()
    )


# ---------------------------------------------------------------------------
# Cenário 1: um banco ao vivo + um banco via fallback de snapshot
# ---------------------------------------------------------------------------

class TestFallbackUmBanco:
    GRUPO = "Corrida Teste Fallback Um Banco"

    def test_totais_incluem_contribuicao_do_banco_via_fallback(self, db):
        _seed_mappings(db, self.GRUPO)
        _seed_snapshot(
            db, self.GRUPO,
            ativo_rows=[_row("Ativo", 101, 100, 10000.0, self.GRUPO)],
            magento_rows=[_row("Magento", 202, 50, 6000.0, self.GRUPO)],
        )

        def fake_ativo(ids, ano_historico=None):
            return [_row("Ativo", 101, 100, 10000.0, self.GRUPO)], None

        def fake_magento(ids, profile="request", ano_historico=None):
            return None, "Fila Magento cheia (1 concorrentes ocupados)"

        with patch.object(svc, "_fetch_ativo", side_effect=fake_ativo), \
             patch.object(svc, "_fetch_magento", side_effect=fake_magento):
            payload = svc.get_detalhe(db, self.GRUPO, ANO, force_refresh=True)

        # Total deve somar Ativo (ao vivo) + Magento (fallback do snapshot) = 150,
        # não só os 100 do Ativo (o que aconteceria tratando Magento como zero).
        assert payload["totais"]["inscritos"] == 150

        # erros mantém o problema técnico original (transparência/debug)...
        assert "Magento" in payload["erros"]
        # ...mas fallback_bancos indica que a lacuna foi coberta e a partir de quando.
        assert "Magento" in payload["fallback_bancos"]
        assert "Ativo" not in payload["fallback_bancos"]
        # timestamp deve ser um ISO válido.
        datetime.fromisoformat(payload["fallback_bancos"]["Magento"])

    def test_snapshot_persistido_fica_completo_sem_erro_residual(self, db):
        _seed_mappings(db, self.GRUPO)
        _seed_snapshot(
            db, self.GRUPO,
            ativo_rows=[_row("Ativo", 101, 100, 10000.0, self.GRUPO)],
            magento_rows=[_row("Magento", 202, 50, 6000.0, self.GRUPO)],
        )

        def fake_ativo(ids, ano_historico=None):
            return [_row("Ativo", 101, 100, 10000.0, self.GRUPO)], None

        def fake_magento(ids, profile="request", ano_historico=None):
            return None, "Fila Magento cheia (1 concorrentes ocupados)"

        with patch.object(svc, "_fetch_ativo", side_effect=fake_ativo), \
             patch.object(svc, "_fetch_magento", side_effect=fake_magento):
            svc.get_detalhe(db, self.GRUPO, ANO, force_refresh=True)

        saved = _get_snapshot_row(db, self.GRUPO)
        assert saved is not None
        saved_payload = json.loads(saved.payload)

        # O snapshot recém salvo não pode carregar o alarme já resolvido —
        # senão toda leitura futura (cache/SWR) voltaria a mostrar o erro.
        assert saved_payload["erros"] == {}
        assert saved_payload.get("fallback_bancos", {}) == {}
        assert saved_payload["totais"]["inscritos"] == 150
        assert len(saved_payload["por_banco"]["Magento"]) == 1


# ---------------------------------------------------------------------------
# Cenário 2: os dois bancos falham -> comportamento atual preservado
# ---------------------------------------------------------------------------

class TestAmbosBancosFalham:
    GRUPO = "Corrida Teste Ambos Falham"

    def test_snapshot_existente_nao_e_sobrescrito(self, db):
        _seed_mappings(db, self.GRUPO)
        _seed_snapshot(
            db, self.GRUPO,
            ativo_rows=[_row("Ativo", 101, 100, 10000.0, self.GRUPO)],
            magento_rows=[_row("Magento", 202, 50, 6000.0, self.GRUPO)],
        )
        original_payload_json = _get_snapshot_row(db, self.GRUPO).payload

        def fake_ativo(ids, ano_historico=None):
            return None, "SSH tunnel não configurado"

        def fake_magento(ids, profile="request", ano_historico=None):
            return None, "Fila Magento cheia (1 concorrentes ocupados)"

        with patch.object(svc, "_fetch_ativo", side_effect=fake_ativo), \
             patch.object(svc, "_fetch_magento", side_effect=fake_magento):
            payload = svc.get_detalhe(db, self.GRUPO, ANO, force_refresh=True)

        # Leitura ao vivo continua mostrando o problema cru dos dois bancos.
        assert payload["totais"]["inscritos"] == 0
        assert set(payload["erros"].keys()) == {"Ativo", "Magento"}
        assert payload["fallback_bancos"] == {}

        # Snapshot bom persistido não pode ser tocado quando os dois falham.
        db.expire_all()
        after = _get_snapshot_row(db, self.GRUPO)
        assert after.payload == original_payload_json


# ---------------------------------------------------------------------------
# Cenário 3: um banco falha e não existe snapshot anterior para fallback
# ---------------------------------------------------------------------------

class TestSemSnapshotDisponivel:
    GRUPO = "Corrida Teste Sem Snapshot"

    def test_resultado_parcial_preservado_e_nao_persistido(self, db):
        _seed_mappings(db, self.GRUPO)
        # Nenhum snapshot pré-existente para este evento_grupo/ano.

        def fake_ativo(ids, ano_historico=None):
            return [_row("Ativo", 101, 100, 10000.0, self.GRUPO)], None

        def fake_magento(ids, profile="request", ano_historico=None):
            return None, "Fila Magento cheia (1 concorrentes ocupados)"

        with patch.object(svc, "_fetch_ativo", side_effect=fake_ativo), \
             patch.object(svc, "_fetch_magento", side_effect=fake_magento):
            payload = svc.get_detalhe(db, self.GRUPO, ANO, force_refresh=True)

        # Sem fallback disponível, comportamento de hoje é preservado: só o
        # banco que respondeu entra no total, erro cru é reportado.
        assert payload["totais"]["inscritos"] == 100
        assert payload["erros"] == {"Magento": "Fila Magento cheia (1 concorrentes ocupados)"}
        assert payload["fallback_bancos"] == {}

        # Resultado incompleto não deve virar o snapshot persistido (evita
        # propagar a lacuna para a próxima leitura servida pelo snapshot).
        assert _get_snapshot_row(db, self.GRUPO) is None
