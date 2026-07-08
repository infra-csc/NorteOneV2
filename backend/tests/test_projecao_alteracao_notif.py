"""Testes de regressão do aviso de alteração de projeção (Task #120/#121).

Regras travadas por estes testes:

1. CRIAÇÃO de projeção NÃO dispara o aviso de alteração.
2. EDIÇÃO só de quantidade dispara (com old/new corretos).
3. EDIÇÃO só de kits (quantidade igual) dispara com o diff de kits.
4. Save sem mudança alguma NÃO dispara; e mudança líquida nula dentro da
   janela de debounce (ex.: 10→15→10) é suprimida no flush (nenhum e-mail).
5. Área com aviso INATIVO (ou sem config) não envia e-mail nenhum.
6. GET/PUT /projecao/alteracao-notif-config exigem admin → 403 para não-admin.
"""

import json
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException

# Importa o pacote de models inteiro para registrar todos os mappers.
import app.models  # noqa: F401
from app.core.database import Base
from app.models.user import Usuario
from app.models.perfil_acesso import PerfilAcesso
from app.models.cadastro_evento import CadastroEvento
from app.models.projecao import (
    AreaProjecao,
    AreaProjecaoUsuario,
    ProjecaoInscritos,
    ProjecaoInscritosHistorico,
    ProjecaoInscritosCliente,
    ProjecaoInscritosKit,
    ProjecaoCorteSnapshot,
    ProjecaoKitCorteSnapshot,
    ProjecaoAutoLockConfig,
    ProjecaoAlteracaoNotifConfig,
    ProjecaoAlteracaoNotifPending,
)
from app.schemas.projecao import (
    ProjecaoInscritosCreate,
    ProjecaoInscritosUpdate,
    KitProjecaoItem,
    AlteracaoNotifAreaUpsert,
)

from app.api.routes import projecao as projecao_routes
from app.services import projecao_alteracao_notif_service as notif_service


TABLES = [
    PerfilAcesso.__table__,
    Usuario.__table__,
    CadastroEvento.__table__,
    AreaProjecao.__table__,
    AreaProjecaoUsuario.__table__,
    ProjecaoInscritos.__table__,
    ProjecaoInscritosHistorico.__table__,
    ProjecaoInscritosCliente.__table__,
    ProjecaoInscritosKit.__table__,
    ProjecaoCorteSnapshot.__table__,
    ProjecaoKitCorteSnapshot.__table__,
    ProjecaoAutoLockConfig.__table__,
    ProjecaoAlteracaoNotifConfig.__table__,
    ProjecaoAlteracaoNotifPending.__table__,
]


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng, tables=TABLES)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def db(engine):
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


def _cancel_timers():
    with notif_service._lock:
        for timer in notif_service._timers.values():
            try:
                timer.cancel()
            except Exception:
                pass
        notif_service._timers.clear()


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Isola efeitos colaterais pesados e limpa o estado de debounce local."""
    monkeypatch.setattr(projecao_routes, "invalidate_consolidado_cache", lambda: None)
    _cancel_timers()
    yield
    _cancel_timers()


@pytest.fixture
def notif_calls(monkeypatch):
    """Captura as chamadas ao gatilho do aviso feitas pelas rotas."""
    calls = []

    def _capture(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(notif_service, "notificar_alteracao_projecao", _capture)
    return calls


def _make_user(db, *, admin: bool, email: str) -> Usuario:
    perfil = PerfilAcesso(nome=f"perfil-{email}", is_admin=admin)
    db.add(perfil)
    db.flush()
    user = Usuario(
        email=email,
        nome=f"User {email}",
        senha_hash="x",
        perfil_acesso_id=perfil.id,
        ativo=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_base(db):
    admin = _make_user(db, admin=True, email="admin@empresa.com")
    evento = CadastroEvento(nome="Eco Run Teste 2026", data_evento=date(2026, 12, 1))
    area = AreaProjecao(nome="Comercial", ativo=True)
    db.add_all([evento, area])
    db.commit()
    db.refresh(evento)
    db.refresh(area)
    return admin, evento, area


def _seed_projecao(db, admin, evento, area, *, quantidade=10, kits=None):
    proj = ProjecaoInscritos(
        evento_id=evento.id,
        area_projecao_id=area.id,
        quantidade=quantidade,
        created_by=admin.id,
    )
    db.add(proj)
    db.flush()
    for nome, qtd in (kits or {}).items():
        db.add(ProjecaoInscritosKit(projecao_id=proj.id, nome_kit=nome, quantidade=qtd))
    db.commit()
    db.refresh(proj)
    return proj


# ---------------------------------------------------------------------------
# (1) Criação NÃO dispara o aviso
# ---------------------------------------------------------------------------


def test_create_nao_dispara_aviso(db, notif_calls):
    admin, evento, area = _seed_base(db)
    resp = projecao_routes.create_projecao(
        data=ProjecaoInscritosCreate(
            evento_id=evento.id,
            area_projecao_id=area.id,
            quantidade=25,
            kits=[KitProjecaoItem(nome_kit="Kit Completo", quantidade=25)],
        ),
        db=db,
        current_user=admin,
    )
    assert resp.quantidade == 25
    assert notif_calls == [], "Criação de projeção não deve disparar aviso de alteração"


# ---------------------------------------------------------------------------
# (2) Edição só de quantidade dispara
# ---------------------------------------------------------------------------


def test_update_quantidade_dispara(db, notif_calls):
    admin, evento, area = _seed_base(db)
    proj = _seed_projecao(db, admin, evento, area, quantidade=10)

    projecao_routes.update_projecao(
        projecao_id=proj.id,
        data=ProjecaoInscritosUpdate(quantidade=15),
        db=db,
        current_user=admin,
    )
    assert len(notif_calls) == 1
    call = notif_calls[0]
    assert call["evento_id"] == evento.id
    assert call["area_projecao_id"] == area.id
    assert call["old_qtd"] == 10
    assert call["new_qtd"] == 15
    assert call["old_kits"] == call["new_kits"] == {}


# ---------------------------------------------------------------------------
# (3) Edição só de kits (quantidade igual) dispara com o diff
# ---------------------------------------------------------------------------


def test_update_somente_kits_dispara(db, notif_calls):
    admin, evento, area = _seed_base(db)
    proj = _seed_projecao(
        db, admin, evento, area, quantidade=10,
        kits={"Kit A": 6, "Kit B": 4},
    )

    projecao_routes.update_projecao(
        projecao_id=proj.id,
        data=ProjecaoInscritosUpdate(
            quantidade=10,
            kits=[
                KitProjecaoItem(nome_kit="Kit A", quantidade=7),
                KitProjecaoItem(nome_kit="Kit B", quantidade=3),
            ],
        ),
        db=db,
        current_user=admin,
    )
    assert len(notif_calls) == 1
    call = notif_calls[0]
    assert call["old_qtd"] == call["new_qtd"] == 10
    assert call["old_kits"] == {"Kit A": 6, "Kit B": 4}
    assert call["new_kits"] == {"Kit A": 7, "Kit B": 3}


# ---------------------------------------------------------------------------
# (4a) Save sem mudança alguma NÃO dispara
# ---------------------------------------------------------------------------


def test_update_sem_mudanca_nao_dispara(db, notif_calls):
    admin, evento, area = _seed_base(db)
    proj = _seed_projecao(
        db, admin, evento, area, quantidade=10, kits={"Kit A": 10},
    )

    # Mesma quantidade e mesmos kits reenviados.
    projecao_routes.update_projecao(
        projecao_id=proj.id,
        data=ProjecaoInscritosUpdate(
            quantidade=10,
            kits=[KitProjecaoItem(nome_kit="Kit A", quantidade=10)],
        ),
        db=db,
        current_user=admin,
    )
    # E também com kits omitidos (None = não mexeu na distribuição).
    projecao_routes.update_projecao(
        projecao_id=proj.id,
        data=ProjecaoInscritosUpdate(quantidade=10),
        db=db,
        current_user=admin,
    )
    assert notif_calls == []


# ---------------------------------------------------------------------------
# (4b) Mudança líquida nula na janela de debounce → e-mail suprimido no flush
# ---------------------------------------------------------------------------


def _bind_session_local(monkeypatch, engine):
    import app.core.database as core_db
    monkeypatch.setattr(
        core_db, "SessionLocal",
        sessionmaker(bind=engine, autocommit=False, autoflush=False),
    )


def _vencer_flush_after(db, key):
    """Coloca flush_after no passado para o claim do flush vencer no teste."""
    from datetime import timedelta
    row = db.query(ProjecaoAlteracaoNotifPending).filter_by(
        evento_id=key[0], area_projecao_id=key[1], usuario_id=key[2],
    ).first()
    assert row is not None
    row.flush_after = notif_service._now_naive_brt() - timedelta(seconds=1)
    db.commit()


def test_net_zero_na_janela_suprime_email(db, engine, monkeypatch):
    sent = []
    monkeypatch.setattr(notif_service, "send_email", lambda *a, **kw: sent.append((a, kw)))
    # Se o flush tentar buscar destinatários, o teste deve falhar: a supressão
    # net-zero acontece ANTES de qualquer consulta de destinatários.
    monkeypatch.setattr(
        notif_service, "get_destinatarios_area",
        lambda *a, **kw: pytest.fail("net-zero não deve consultar destinatários"),
    )
    monkeypatch.setenv("PROJECAO_ALTERACAO_NOTIF_DEBOUNCE_SEGUNDOS", "600")
    _bind_session_local(monkeypatch, engine)

    common = dict(
        evento_id=1, area_projecao_id=2, usuario_id=3,
        evento_nome="Eco Run", area_nome="Comercial", usuario_nome="Ana",
    )
    notif_service.notificar_alteracao_projecao(
        **common, old_qtd=10, new_qtd=15, old_kits={}, new_kits={},
    )
    notif_service.notificar_alteracao_projecao(
        **common, old_qtd=15, new_qtd=10, old_kits={}, new_kits={},
    )
    _cancel_timers()

    key = (1, 2, 3)
    # Estado persistido: UMA linha só, baseline preservada da 1ª alteração,
    # estado final agrupado.
    rows = db.query(ProjecaoAlteracaoNotifPending).all()
    assert len(rows) == 1
    assert rows[0].baseline_qtd == 10
    assert rows[0].nova_qtd == 10

    _vencer_flush_after(db, key)
    notif_service._flush(key)
    assert sent == [], "Mudança líquida nula deve suprimir o e-mail"
    db.expire_all()
    assert db.query(ProjecaoAlteracaoNotifPending).count() == 0


def test_flush_claim_atomico_apenas_um_envio(db, engine, monkeypatch):
    """Simula timers de múltiplos workers: só um vence o claim e envia."""
    enviados = []
    monkeypatch.setattr(
        notif_service, "_send_entry",
        lambda key, entry: enviados.append((key, entry["baseline_qtd"], entry["nova_qtd"])),
    )
    monkeypatch.setenv("PROJECAO_ALTERACAO_NOTIF_DEBOUNCE_SEGUNDOS", "600")
    _bind_session_local(monkeypatch, engine)

    common = dict(
        evento_id=7, area_projecao_id=8, usuario_id=9,
        evento_nome="Eco Run", area_nome="Comercial", usuario_nome="Ana",
    )
    notif_service.notificar_alteracao_projecao(
        **common, old_qtd=100, new_qtd=110, old_kits={}, new_kits={},
    )
    notif_service.notificar_alteracao_projecao(
        **common, old_qtd=110, new_qtd=130, old_kits={}, new_kits={"A": 5},
    )
    _cancel_timers()

    key = (7, 8, 9)

    # Antes da janela vencer, nenhum flush envia (claim exige flush_after <= now).
    notif_service._flush(key)
    assert enviados == []

    _vencer_flush_after(db, key)
    # "Dois workers" disparam o flush: apenas um vence o claim.
    notif_service._flush(key)
    notif_service._flush(key)
    assert enviados == [(key, 100, 130)]
    db.expire_all()
    assert db.query(ProjecaoAlteracaoNotifPending).count() == 0


def test_sweep_envia_orfas(db, engine, monkeypatch):
    """Linha órfã (flush_after vencido além da folga) é enviada pela varredura."""
    from datetime import timedelta
    enviados = []
    monkeypatch.setattr(
        notif_service, "_send_entry",
        lambda key, entry: enviados.append((key, entry["baseline_qtd"], entry["nova_qtd"])),
    )
    _bind_session_local(monkeypatch, engine)

    agora = notif_service._now_naive_brt()
    db.add(ProjecaoAlteracaoNotifPending(
        evento_id=1, area_projecao_id=2, usuario_id=3,
        baseline_qtd=10, nova_qtd=20,
        meta_json=json.dumps({"evento_nome": "X", "area_nome": "Y", "usuario_nome": "Z"}),
        ultima_em=agora - timedelta(minutes=10),
        flush_after=agora - timedelta(minutes=9),
    ))
    db.commit()

    notif_service._sweep_orfas()
    assert enviados == [((1, 2, 3), 10, 20)]
    db.expire_all()
    assert db.query(ProjecaoAlteracaoNotifPending).count() == 0


# ---------------------------------------------------------------------------
# (5) Área com aviso inativo (ou sem config) não envia e-mail
# ---------------------------------------------------------------------------


def _entry_exemplo(old_qtd=10, new_qtd=20):
    from datetime import datetime
    return {
        "baseline_qtd": old_qtd,
        "baseline_kits": {},
        "nova_qtd": new_qtd,
        "novos_kits": {},
        "ultima_em": datetime(2026, 7, 8, 10, 0),
        "meta": {"evento_nome": "Eco Run", "area_nome": "Comercial", "usuario_nome": "Ana"},
    }


def test_area_inativa_nao_envia(db, engine, monkeypatch):
    _, _, area = _seed_base(db)
    db.add(ProjecaoAlteracaoNotifConfig(
        area_projecao_id=area.id,
        ativo=False,
        emails_json=json.dumps(["gestor@empresa.com"]),
    ))
    db.commit()

    assert notif_service.get_destinatarios_area(db, area.id) == []

    sent = []
    monkeypatch.setattr(notif_service, "send_email", lambda *a, **kw: sent.append((a, kw)))
    import app.core.database as core_db
    monkeypatch.setattr(
        core_db, "SessionLocal",
        sessionmaker(bind=engine, autocommit=False, autoflush=False),
    )
    notif_service._send_entry((1, area.id, 3), _entry_exemplo())
    assert sent == [], "Área com aviso inativo não deve receber e-mail"

    # Área sem NENHUMA config também não envia.
    notif_service._send_entry((1, area.id + 999, 3), _entry_exemplo())
    assert sent == []


def test_area_ativa_envia_para_todos(db, engine, monkeypatch):
    _, _, area = _seed_base(db)
    db.add(ProjecaoAlteracaoNotifConfig(
        area_projecao_id=area.id,
        ativo=True,
        emails_json=json.dumps(["a@empresa.com", "b@empresa.com"]),
    ))
    db.commit()

    assert notif_service.get_destinatarios_area(db, area.id) == [
        "a@empresa.com", "b@empresa.com",
    ]

    sent = []
    monkeypatch.setattr(
        notif_service, "send_email",
        lambda email, subject, html=None, text=None: sent.append(email),
    )
    import app.core.database as core_db
    monkeypatch.setattr(
        core_db, "SessionLocal",
        sessionmaker(bind=engine, autocommit=False, autoflush=False),
    )
    notif_service._send_entry((1, area.id, 3), _entry_exemplo())
    assert sent == ["a@empresa.com", "b@empresa.com"]


# ---------------------------------------------------------------------------
# (6) Config do aviso é admin-only: 403 para não-admin (GET e PUT)
# ---------------------------------------------------------------------------


def test_get_config_nao_admin_403(db):
    _seed_base(db)
    comum = _make_user(db, admin=False, email="comum@empresa.com")
    with pytest.raises(HTTPException) as exc:
        projecao_routes.list_alteracao_notif_config(db=db, current_user=comum)
    assert exc.value.status_code == 403


def test_put_config_nao_admin_403(db):
    _, _, area = _seed_base(db)
    comum = _make_user(db, admin=False, email="comum2@empresa.com")
    with pytest.raises(HTTPException) as exc:
        projecao_routes.upsert_alteracao_notif_config(
            data=AlteracaoNotifAreaUpsert(
                area_projecao_id=area.id, ativo=True, emails=["x@empresa.com"],
            ),
            db=db,
            current_user=comum,
        )
    assert exc.value.status_code == 403


def test_put_config_admin_ok(db):
    admin, _, area = _seed_base(db)
    resp = projecao_routes.upsert_alteracao_notif_config(
        data=AlteracaoNotifAreaUpsert(
            area_projecao_id=area.id, ativo=True,
            emails=["Gestor@Empresa.com", "gestor@empresa.com"],
        ),
        db=db,
        current_user=admin,
    )
    assert resp.ativo is True
    # Normaliza (lower) e deduplica.
    assert resp.emails == ["gestor@empresa.com"]
