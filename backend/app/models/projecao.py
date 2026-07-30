from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, ForeignKey, Text, UniqueConstraint, Index, text
from sqlalchemy.orm import relationship
from datetime import datetime
from zoneinfo import ZoneInfo
from ..core.database import Base


def _now_brasilia():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None)


# Kit cujo comportamento muda no Corte 2: até o Corte 1 ele é "Kit Completo -
# Sem camiseta"; depois que o Corte 1 congela, vira "Camiseta avulsa" (display)
# com teto igual ao valor congelado no Corte 1 (ver ProjecaoKitCorteSnapshot).
KIT_CAMISETA_AVULSA_ORIGEM = "Kit Completo - Sem camiseta"
KIT_CAMISETA_AVULSA_LABEL = "Camiseta avulsa"


class AreaProjecao(Base):
    __tablename__ = "area_projecao"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), unique=True, nullable=False)
    sigla = Column(String(10), nullable=True)
    ativo = Column(Boolean, default=True, index=True)
    usa_cutoff_customizado = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=_now_brasilia)
    updated_at = Column(DateTime, onupdate=_now_brasilia)

    usuarios = relationship("AreaProjecaoUsuario", back_populates="area", cascade="all, delete-orphan")
    projecoes = relationship("ProjecaoInscritos", back_populates="area_projecao")


class AreaProjecaoUsuario(Base):
    __tablename__ = "area_projecao_usuario"

    id = Column(Integer, primary_key=True, index=True)
    area_projecao_id = Column(Integer, ForeignKey("area_projecao.id", ondelete="CASCADE"), nullable=False, index=True)
    usuario_id = Column(Integer, ForeignKey("dim_usuario.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=_now_brasilia)

    area = relationship("AreaProjecao", back_populates="usuarios")
    usuario = relationship("Usuario")

    __table_args__ = (
        UniqueConstraint("area_projecao_id", "usuario_id", name="uq_area_usuario"),
    )


class ProjecaoInscritos(Base):
    __tablename__ = "projecao_inscritos"

    id = Column(Integer, primary_key=True, index=True)
    evento_id = Column(Integer, ForeignKey("cadastro_evento.id", ondelete="CASCADE"), nullable=False, index=True)
    area_projecao_id = Column(Integer, ForeignKey("area_projecao.id", ondelete="CASCADE"), nullable=False, index=True)
    quantidade = Column(Integer, nullable=False, default=0)
    created_by = Column(Integer, ForeignKey("dim_usuario.id"), nullable=False, index=True)
    updated_by = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True, index=True)
    locked_by = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=_now_brasilia)
    updated_at = Column(DateTime, onupdate=_now_brasilia)
    locked_at = Column(DateTime, nullable=True, index=True)
    deleted_at = Column(DateTime, nullable=True, index=True)
    # Resumo da ÚLTIMA escrita "fora do prazo" (Task #126): trava que estava
    # ativa ('corte_1' | 'corte_2' | 'auto_lock'), quando e por quem. Permite
    # exibir o selo na listagem sem varrer o histórico. O registro permanente
    # e completo fica em ProjecaoInscritosHistorico (fora_prazo/trava_ativa).
    fora_prazo_trava = Column(String(20), nullable=True)
    fora_prazo_em = Column(DateTime, nullable=True)
    fora_prazo_por = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True)

    evento = relationship("CadastroEvento")
    area_projecao = relationship("AreaProjecao", back_populates="projecoes")
    criador = relationship("Usuario", foreign_keys=[created_by])
    editor = relationship("Usuario", foreign_keys=[updated_by])
    travador = relationship("Usuario", foreign_keys=[locked_by])
    fora_prazo_usuario = relationship("Usuario", foreign_keys=[fora_prazo_por])
    historico = relationship("ProjecaoInscritosHistorico", back_populates="projecao")
    clientes = relationship("ProjecaoInscritosCliente", back_populates="projecao", cascade="all, delete-orphan")
    kits = relationship("ProjecaoInscritosKit", back_populates="projecao", cascade="all, delete-orphan")


class ProjecaoInscritosHistorico(Base):
    __tablename__ = "projecao_inscritos_historico"

    id = Column(Integer, primary_key=True, index=True)
    projecao_id = Column(Integer, ForeignKey("projecao_inscritos.id", ondelete="CASCADE"), nullable=False, index=True)
    acao = Column(String(20), nullable=False)
    campo_alterado = Column(String(50), nullable=True)
    valor_anterior = Column(Text, nullable=True)
    valor_novo = Column(Text, nullable=True)
    usuario_id = Column(Integer, ForeignKey("dim_usuario.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=_now_brasilia, index=True)
    # Auditoria "fora do prazo" (Task #126): True quando a operação foi feita
    # com Corte 1/2 congelado ou trava automática D-N ativa. trava_ativa guarda
    # qual trava estava vigente ('corte_1' | 'corte_2' | 'auto_lock').
    fora_prazo = Column(Boolean, default=False, nullable=False)
    trava_ativa = Column(String(20), nullable=True)

    projecao = relationship("ProjecaoInscritos", back_populates="historico")
    usuario = relationship("Usuario")


class ProjecaoInscritosCliente(Base):
    __tablename__ = "projecao_inscritos_cliente"

    id = Column(Integer, primary_key=True, index=True)
    projecao_id = Column(Integer, ForeignKey("projecao_inscritos.id", ondelete="CASCADE"), nullable=False, index=True)
    nome_cliente = Column(String(200), nullable=False)
    quantidade = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=_now_brasilia)

    projecao = relationship("ProjecaoInscritos", back_populates="clientes")


class ProjecaoInscritosKit(Base):
    __tablename__ = "projecao_inscritos_kit"

    id = Column(Integer, primary_key=True, index=True)
    projecao_id = Column(Integer, ForeignKey("projecao_inscritos.id", ondelete="CASCADE"), nullable=False, index=True)
    nome_kit = Column(String(200), nullable=False)
    quantidade = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=_now_brasilia)

    projecao = relationship("ProjecaoInscritos", back_populates="kits")


class ProjecaoCutoffRule(Base):
    __tablename__ = "projecao_cutoff_rule"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)
    dias_antes_evento = Column(Integer, nullable=False, index=True)
    ativo = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime, default=_now_brasilia)
    updated_at = Column(DateTime, onupdate=_now_brasilia)

    __table_args__ = (
        UniqueConstraint("dias_antes_evento", name="uq_cutoff_dias"),
    )


class ProjecaoCutoffEventoArea(Base):
    __tablename__ = "projecao_cutoff_evento_area"

    id = Column(Integer, primary_key=True, index=True)
    evento_id = Column(Integer, ForeignKey("cadastro_evento.id", ondelete="CASCADE"), nullable=False, index=True)
    area_projecao_id = Column(Integer, ForeignKey("area_projecao.id", ondelete="CASCADE"), nullable=False, index=True)
    data_corte_1 = Column(Date, nullable=True)
    data_corte_2 = Column(Date, nullable=True)
    data_saida_caminhao = Column(Date, nullable=True)
    observacao_corte_1 = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True, index=True)
    updated_by = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=_now_brasilia)
    updated_at = Column(DateTime, onupdate=_now_brasilia)

    evento = relationship("CadastroEvento")
    area = relationship("AreaProjecao")
    editor = relationship("Usuario", foreign_keys=[updated_by])
    criador = relationship("Usuario", foreign_keys=[created_by])

    __table_args__ = (
        UniqueConstraint("evento_id", "area_projecao_id", name="uq_cutoff_evento_area"),
    )


class ProjecaoAutoLockConfig(Base):
    __tablename__ = "projecao_auto_lock_config"

    id = Column(Integer, primary_key=True, index=True)
    dias_antes_evento = Column(Integer, nullable=False, default=7)
    # Horário (BRT, formato "HH:MM") em que a trava passa a valer no dia D-N.
    # "00:00" (default) preserva o comportamento legado: trava o dia D-N inteiro.
    hora_trava = Column(String(5), nullable=False, default="00:00")
    ativo = Column(Boolean, default=True, nullable=False)
    updated_by = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True)
    updated_at = Column(DateTime, default=_now_brasilia, onupdate=_now_brasilia)

    editor = relationship("Usuario", foreign_keys=[updated_by])


class ProjecaoCorteConfig(Base):
    """Config global (single-row) dos dois cortes de congelamento por evento.

    dias_corte_1 → Projeção envio (D-N do corte 1)
    dias_corte_2 → Projeção convicta (D-N do corte 2)
    Quando o evento atinge cada D-, o job noturno congela o total de projeção.
    """
    __tablename__ = "projecao_corte_config"

    id = Column(Integer, primary_key=True, index=True)
    dias_corte_1 = Column(Integer, nullable=False, default=30)
    dias_corte_2 = Column(Integer, nullable=False, default=7)
    # D-N do alerta "Ponto de corte" — contado em cima da Data de corte Envio do
    # evento. Valor único (0 = alerta desligado). Independente do congelamento.
    dias_alerta_envio = Column(Integer, nullable=False, default=30)
    # Resumo diário por e-mail das pendências (independente do alerta in-app).
    notif_email_ativo = Column(Boolean, default=False, nullable=False)
    notif_email_hora = Column(Integer, default=8, nullable=False)  # hora BRT (0-23)
    notif_email_last_sent = Column(Date, nullable=True)  # guarda contra envio duplicado/dia
    # Canal de envio: 'email' | 'teams' | 'ambos'
    notif_canal = Column(String(20), default='email', nullable=False)
    ativo = Column(Boolean, default=False, nullable=False)
    # Área global responsável por aprovar reduções do total de projeção durante
    # o Corte de Ajuste (Task #212). None = nenhuma área configurada ainda —
    # nesse caso só administradores enxergam/agem na fila de chamados
    # pendentes (rede de segurança contra deadlock).
    area_aprovadora_reducao_id = Column(Integer, ForeignKey("area_projecao.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True)
    updated_at = Column(DateTime, default=_now_brasilia, onupdate=_now_brasilia)

    editor = relationship("Usuario", foreign_keys=[updated_by])
    area_aprovadora_reducao = relationship("AreaProjecao", foreign_keys=[area_aprovadora_reducao_id])


class ProjecaoCorteSnapshot(Base):
    """Valores congelados (por evento) de cada corte. Uma linha por evento."""
    __tablename__ = "projecao_corte_snapshot"

    id = Column(Integer, primary_key=True, index=True)
    evento_id = Column(Integer, ForeignKey("cadastro_evento.id", ondelete="CASCADE"), nullable=False, index=True)
    valor_corte_1 = Column(Integer, nullable=True)
    congelado_corte_1_em = Column(DateTime, nullable=True)
    valor_corte_2 = Column(Integer, nullable=True)
    congelado_corte_2_em = Column(DateTime, nullable=True)
    # Reabertura manual (admin): quando True, o congelamento AO VIVO/noturno NÃO
    # recongela este corte automaticamente — só volta a congelar quando o admin
    # clica em "Congelar agora" (recongelar). Limpo no recongelamento manual.
    reaberto_manual_corte_1 = Column(Boolean, default=False, nullable=False)
    reaberto_manual_corte_2 = Column(Boolean, default=False, nullable=False)
    # Congelamento manual (admin clicou "Congelar agora"): quando True, o
    # auto-descongelamento NÃO reverte este corte mesmo que a janela D-N ainda
    # não tenha sido atingida. Limpo na reabertura manual.
    congelado_manual_corte_1 = Column(Boolean, default=False, nullable=False)
    congelado_manual_corte_2 = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime, default=_now_brasilia, onupdate=_now_brasilia)

    evento = relationship("CadastroEvento")

    __table_args__ = (
        UniqueConstraint("evento_id", name="uq_corte_snapshot_evento"),
    )


class ProjecaoKitCorteSnapshot(Base):
    """Valor congelado por (evento, área, kit) no momento do Corte 1.

    Hoje só é populado para o kit "Kit Completo - Sem camiseta": guarda quanto
    havia desse kit quando o Corte 1 congelou, servindo de TETO da "Camiseta
    avulsa" no Corte 2 (o usuário só pode diminuir a partir desse valor).
    """
    __tablename__ = "projecao_kit_corte_snapshot"

    id = Column(Integer, primary_key=True, index=True)
    evento_id = Column(Integer, ForeignKey("cadastro_evento.id", ondelete="CASCADE"), nullable=False, index=True)
    area_projecao_id = Column(Integer, ForeignKey("area_projecao.id", ondelete="CASCADE"), nullable=False, index=True)
    nome_kit = Column(String(200), nullable=False)
    valor_corte_1 = Column(Integer, nullable=False, default=0)
    congelado_em = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=_now_brasilia, onupdate=_now_brasilia)

    evento = relationship("CadastroEvento")
    area = relationship("AreaProjecao")

    __table_args__ = (
        UniqueConstraint("evento_id", "area_projecao_id", "nome_kit", name="uq_kit_corte_snapshot_evento_area_kit"),
    )


class ProjecaoCorteDistSnapshot(Base):
    """Foto COMPLETA da distribuição (quantidade + kits + clientes) por (evento,
    área) no momento em que o Corte 1 congela.

    Diferente de ProjecaoKitCorteSnapshot (que só guarda o teto da Camiseta
    avulsa), esta tabela guarda o retrato inteiro do Corte 1 para que a tela de
    Corte 2 possa exibir o que foi preenchido no Corte 1 (leitura) ao lado dos
    campos aditivos do Corte 2. kits/clientes são JSON-serializados em Text:
    [{"nome_kit"|"nome_cliente": str, "quantidade": int}, ...].

    Capturada nos DOIS caminhos de congelamento do Corte 1 (job/consolidado via
    `congelar_cortes_para_eventos` e o recongelamento manual do admin).
    """
    __tablename__ = "projecao_corte_dist_snapshot"

    id = Column(Integer, primary_key=True, index=True)
    evento_id = Column(Integer, ForeignKey("cadastro_evento.id", ondelete="CASCADE"), nullable=False, index=True)
    area_projecao_id = Column(Integer, ForeignKey("area_projecao.id", ondelete="CASCADE"), nullable=False, index=True)
    quantidade = Column(Integer, nullable=False, default=0)
    kits_json = Column(Text, nullable=True)
    clientes_json = Column(Text, nullable=True)
    congelado_em = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=_now_brasilia, onupdate=_now_brasilia)

    evento = relationship("CadastroEvento")
    area = relationship("AreaProjecao")

    __table_args__ = (
        UniqueConstraint("evento_id", "area_projecao_id", name="uq_corte_dist_snapshot_evento_area"),
    )


class ProjecaoReducaoSolicitacao(Base):
    """Chamado de aprovação para reduzir o total de uma projeção durante o
    Corte de Ajuste (Corte 2). Task #212: enquanto o evento está nessa fase,
    uma edição que DIMINUI o total já salvo não é aplicada direto — vira um
    chamado pendente que a área aprovadora (config global, ver
    `ProjecaoCorteConfig.area_aprovadora_reducao_id`) precisa decidir. Fora do
    Corte de Ajuste (ou aumentos/redistribuições que preservam o total), a
    edição continua indo direto — este fluxo não se aplica.

    Um novo chamado para o mesmo (evento, área) enquanto já existe um pendente
    substitui o anterior (cancela o velho, cria o novo) — reforçado pelo
    índice único parcial abaixo, não só pela lógica de aplicação, então uma
    corrida entre duas requisições concorrentes nunca deixa dois pendentes.
    """
    __tablename__ = "projecao_reducao_solicitacao"

    id = Column(Integer, primary_key=True, index=True)
    projecao_id = Column(Integer, ForeignKey("projecao_inscritos.id", ondelete="CASCADE"), nullable=False, index=True)
    evento_id = Column(Integer, ForeignKey("cadastro_evento.id", ondelete="CASCADE"), nullable=False, index=True)
    area_projecao_id = Column(Integer, ForeignKey("area_projecao.id", ondelete="CASCADE"), nullable=False, index=True)
    quantidade_atual = Column(Integer, nullable=False)
    quantidade_proposta = Column(Integer, nullable=False)
    kits_propostos_json = Column(Text, nullable=True)
    clientes_propostos_json = Column(Text, nullable=True)
    motivo = Column(Text, nullable=True)
    # 'pendente' | 'aprovado' | 'rejeitado' | 'cancelado'
    status = Column(String(20), nullable=False, default="pendente", index=True)
    solicitado_por = Column(Integer, ForeignKey("dim_usuario.id"), nullable=False, index=True)
    solicitado_em = Column(DateTime, default=_now_brasilia, nullable=False)
    decidido_por = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True)
    decidido_em = Column(DateTime, nullable=True)
    motivo_rejeicao = Column(Text, nullable=True)

    projecao = relationship("ProjecaoInscritos")
    evento = relationship("CadastroEvento")
    area_projecao = relationship("AreaProjecao", foreign_keys=[area_projecao_id])
    solicitante = relationship("Usuario", foreign_keys=[solicitado_por])
    decisor = relationship("Usuario", foreign_keys=[decidido_por])

    __table_args__ = (
        Index(
            "uq_reducao_pendente_evento_area",
            "evento_id", "area_projecao_id",
            unique=True,
            postgresql_where=text("status = 'pendente'"),
        ),
    )


class ProjecaoNotifLog(Base):
    """
    Registro histórico de cada disparo de notificação (agendado ou manual).
    Permite consultar os últimos N envios no painel de configuração.
    """
    __tablename__ = "projecao_notif_log"

    id = Column(Integer, primary_key=True, index=True)
    disparado_em = Column(DateTime, nullable=False, default=_now_brasilia, index=True)
    canal = Column(String(20), nullable=False)
    enviados_email = Column(Integer, nullable=False, default=0)
    enviados_teams = Column(Integer, nullable=False, default=0)
    falhas = Column(Integer, nullable=False, default=0)
    total_eventos = Column(Integer, nullable=False, default=0)
    destinatarios_json = Column(Text, nullable=True)
    erros_json = Column(Text, nullable=True)
    foi_teste = Column(Boolean, nullable=False, default=False)
    usuario_teste_id = Column(Integer, ForeignKey("dim_usuario.id", ondelete="SET NULL"), nullable=True)

    usuario_teste = relationship("Usuario", foreign_keys=[usuario_teste_id])


class ProjecaoAlteracaoNotifConfig(Base):
    """
    Config por ÁREA do aviso imediato de ALTERAÇÃO de projeção (Task: notificar
    edições de quantidade por e-mail). Lista de destinatários própria — separada
    do vínculo área↔usuário usado pelas pendências (`area_projecao_usuario`).

    emails_json: lista JSON de e-mails ["a@x.com", ...].
    ativo: liga/desliga o aviso para a área (default False).
    """
    __tablename__ = "projecao_alteracao_notif_config"

    id = Column(Integer, primary_key=True, index=True)
    area_projecao_id = Column(Integer, ForeignKey("area_projecao.id", ondelete="CASCADE"), nullable=False, index=True)
    ativo = Column(Boolean, default=False, nullable=False)
    emails_json = Column(Text, nullable=True)
    updated_by = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True)
    updated_at = Column(DateTime, default=_now_brasilia, onupdate=_now_brasilia)

    area = relationship("AreaProjecao")
    editor = relationship("Usuario", foreign_keys=[updated_by])

    __table_args__ = (
        UniqueConstraint("area_projecao_id", name="uq_alteracao_notif_area"),
    )


class ProjecaoAlteracaoNotifPending(Base):
    """
    Debounce PERSISTIDO do aviso de alteração de projeção (multi-worker safe).

    Cada save de edição faz UPSERT aqui: mantém o baseline (estado ANTES da
    1ª alteração da janela), atualiza o estado final e empurra `flush_after`.
    Um timer local em cada worker tenta o flush após a janela; o envio só
    acontece para quem conseguir o claim atômico (DELETE ... WHERE flush_after
    <= now RETURNING), então mesmo com múltiplos workers/instâncias sai UM
    e-mail por janela. Linhas órfãs (worker morreu antes do timer) são
    varridas oportunisticamente no próximo save de qualquer usuário.
    """
    __tablename__ = "projecao_alteracao_notif_pending"

    id = Column(Integer, primary_key=True, index=True)
    evento_id = Column(Integer, nullable=False)
    area_projecao_id = Column(Integer, nullable=False)
    usuario_id = Column(Integer, nullable=False)
    baseline_qtd = Column(Integer, nullable=False)
    baseline_kits_json = Column(Text, nullable=True)
    nova_qtd = Column(Integer, nullable=False)
    novos_kits_json = Column(Text, nullable=True)
    meta_json = Column(Text, nullable=True)
    ultima_em = Column(DateTime, nullable=False, default=_now_brasilia)
    flush_after = Column(DateTime, nullable=False, index=True)
    # Sticky: se QUALQUER save da janela de debounce foi fora do prazo, o e-mail
    # agrupado sinaliza (COALESCE no UPSERT preserva o primeiro valor não-nulo).
    fora_prazo_trava = Column(String(20), nullable=True)

    __table_args__ = (
        UniqueConstraint("evento_id", "area_projecao_id", "usuario_id",
                         name="uq_alteracao_notif_pending_chave"),
    )


class SimuladorProjetadoFaixas(Base):
    __tablename__ = "simulador_projetado_faixas"

    id = Column(Integer, primary_key=True, index=True)
    evento_id = Column(String(100), nullable=False, index=True)
    usuario_id = Column(Integer, ForeignKey("dim_usuario.id", ondelete="CASCADE"), nullable=False, index=True)
    faixas = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, default=_now_brasilia)
    updated_at = Column(DateTime, default=_now_brasilia, onupdate=_now_brasilia)

    usuario = relationship("Usuario")

    __table_args__ = (
        UniqueConstraint("evento_id", "usuario_id", name="uq_simulador_faixas_evento_usuario"),
    )

