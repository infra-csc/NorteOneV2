from datetime import date, datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from app.core.database import SessionLocal, engine, Base
from app.core.security import get_password_hash
from app.models.dimensoes import DimTempo, DimCentroCusto, DimConta, DimProjeto, DimCategoriaAtleta
from app.models.user import Usuario
from app.models.fatos import FatoOrcamento, FatoProjecao, FatoRealizado, FatoAtletasMetricas, FatoAtletasCanais, FatoAtletasKits, FatoAtletasCustos

Base.metadata.create_all(bind=engine)

def seed_tempo(db: Session):
    if db.query(DimTempo).first():
        return
    
    meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 
             'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
    dias_semana = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
    
    for ano in [2024, 2025]:
        for mes in range(1, 13):
            for dia in range(1, 29):
                try:
                    d = date(ano, mes, dia)
                    trimestre = (mes - 1) // 3 + 1
                    semestre = 1 if mes <= 6 else 2
                    tempo = DimTempo(
                        data=d,
                        dia=dia,
                        mes=mes,
                        trimestre=trimestre,
                        semestre=semestre,
                        ano=ano,
                        dia_semana=dias_semana[d.weekday()],
                        nome_mes=meses[mes-1],
                        is_feriado=False
                    )
                    db.add(tempo)
                except:
                    pass
    db.commit()

def seed_centros_custo(db: Session):
    if db.query(DimCentroCusto).first():
        return
    
    centros = [
        DimCentroCusto(codigo="CC001", nome="Comercial", area="Vendas", gestor_responsavel="João Silva"),
        DimCentroCusto(codigo="CC002", nome="Produção", area="Operações", gestor_responsavel="Maria Santos"),
        DimCentroCusto(codigo="CC003", nome="Administrativo", area="Backoffice", gestor_responsavel="Pedro Costa"),
        DimCentroCusto(codigo="CC004", nome="Marketing", area="Comunicação", gestor_responsavel="Ana Oliveira"),
        DimCentroCusto(codigo="CC005", nome="Cenografia", area="Operações", gestor_responsavel="Carlos Lima"),
    ]
    db.add_all(centros)
    db.commit()

def seed_contas(db: Session):
    if db.query(DimConta).first():
        return
    
    contas = [
        DimConta(codigo="R001", nome="Inscrições", tipo="RECEITA", grupo="Receitas Operacionais", subgrupo="Eventos"),
        DimConta(codigo="R002", nome="Patrocínios", tipo="RECEITA", grupo="Receitas Operacionais", subgrupo="Parcerias"),
        DimConta(codigo="R003", nome="Venda de Produtos", tipo="RECEITA", grupo="Receitas Operacionais", subgrupo="Produtos"),
        DimConta(codigo="R004", nome="Taxas", tipo="RECEITA", grupo="Receitas Operacionais", subgrupo="Serviços"),
        DimConta(codigo="R005", nome="Outras Receitas", tipo="RECEITA", grupo="Receitas Diversas", subgrupo="Outros"),
        DimConta(codigo="D001", nome="Kits Atletas", tipo="DESPESA", grupo="Custos Diretos", subgrupo="Material"),
        DimConta(codigo="D002", nome="Produção", tipo="DESPESA", grupo="Custos Diretos", subgrupo="Operacional"),
        DimConta(codigo="D003", nome="Logística", tipo="DESPESA", grupo="Custos Diretos", subgrupo="Transporte"),
        DimConta(codigo="D004", nome="Premiação", tipo="DESPESA", grupo="Custos Diretos", subgrupo="Atletas"),
        DimConta(codigo="D005", nome="Infraestrutura", tipo="DESPESA", grupo="Custos Diretos", subgrupo="Estrutura"),
    ]
    db.add_all(contas)
    db.commit()

def seed_categorias_atletas(db: Session):
    if db.query(DimCategoriaAtleta).first():
        return
    
    categorias = [
        DimCategoriaAtleta(codigo="C5KM", nome="Corrida 5K - Masculino Adulto", faixa_etaria="Adulto", genero="MASCULINO", modalidade="CORRIDA", valor_inscricao_padrao=Decimal("120.00"), custo_kit_padrao=Decimal("45.00")),
        DimCategoriaAtleta(codigo="C5KF", nome="Corrida 5K - Feminino Adulto", faixa_etaria="Adulto", genero="FEMININO", modalidade="CORRIDA", valor_inscricao_padrao=Decimal("120.00"), custo_kit_padrao=Decimal("45.00")),
        DimCategoriaAtleta(codigo="C10KM", nome="Corrida 10K - Masculino Adulto", faixa_etaria="Adulto", genero="MASCULINO", modalidade="CORRIDA", valor_inscricao_padrao=Decimal("150.00"), custo_kit_padrao=Decimal("50.00")),
        DimCategoriaAtleta(codigo="C10KF", nome="Corrida 10K - Feminino Adulto", faixa_etaria="Adulto", genero="FEMININO", modalidade="CORRIDA", valor_inscricao_padrao=Decimal("150.00"), custo_kit_padrao=Decimal("50.00")),
        DimCategoriaAtleta(codigo="C21KM", nome="Corrida 21K - Masculino Adulto", faixa_etaria="Adulto", genero="MASCULINO", modalidade="CORRIDA", valor_inscricao_padrao=Decimal("200.00"), custo_kit_padrao=Decimal("60.00")),
        DimCategoriaAtleta(codigo="C21KF", nome="Corrida 21K - Feminino Adulto", faixa_etaria="Adulto", genero="FEMININO", modalidade="CORRIDA", valor_inscricao_padrao=Decimal("200.00"), custo_kit_padrao=Decimal("60.00")),
        DimCategoriaAtleta(codigo="KIDS", nome="Kids Run - Misto Infantil", faixa_etaria="Infantil", genero="MISTO", modalidade="CORRIDA", valor_inscricao_padrao=Decimal("50.00"), custo_kit_padrao=Decimal("30.00")),
        DimCategoriaAtleta(codigo="PCD", nome="Corrida PCD - Misto Adulto", faixa_etaria="Adulto", genero="MISTO", modalidade="CORRIDA", is_pcd=True, valor_inscricao_padrao=Decimal("80.00"), custo_kit_padrao=Decimal("50.00")),
        DimCategoriaAtleta(codigo="CICM", nome="Ciclismo 50K - Masculino", faixa_etaria="Adulto", genero="MASCULINO", modalidade="CICLISMO", valor_inscricao_padrao=Decimal("180.00"), custo_kit_padrao=Decimal("55.00")),
        DimCategoriaAtleta(codigo="CICF", nome="Ciclismo 50K - Feminino", faixa_etaria="Adulto", genero="FEMININO", modalidade="CICLISMO", valor_inscricao_padrao=Decimal("180.00"), custo_kit_padrao=Decimal("55.00")),
    ]
    db.add_all(categorias)
    db.commit()

def seed_projetos(db: Session):
    if db.query(DimProjeto).first():
        return
    
    projetos = [
        DimProjeto(
            codigo="MSP2025", produto="Maratona SP", modalidade="CORRIDA", tipo_evento="PROPRIO",
            evento="Maratona de São Paulo 2025", lei="ROUANET", cliente="Prefeitura SP",
            status="EM_ANDAMENTO", data_evento=date(2025, 1, 15), local_evento="Parque Ibirapuera",
            cidade="São Paulo", estado="SP", capacidade_maxima=15000, etapa=1
        ),
        DimProjeto(
            codigo="DCS2025", produto="Desafio Ciclístico", modalidade="CICLISMO", tipo_evento="PROPRIO",
            evento="Desafio Ciclístico Sudeste", lei="PIE", cliente="Secretaria Esportes",
            status="EM_ANDAMENTO", data_evento=date(2025, 3, 20), local_evento="Estrada Velha",
            cidade="Rio de Janeiro", estado="RJ", capacidade_maxima=3000, etapa=1
        ),
        DimProjeto(
            codigo="CNR2025", produto="Corrida Noturna", modalidade="CORRIDA", tipo_evento="PROPRIO",
            evento="Corrida Noturna RJ", lei="ISS RJ", cliente="Prefeitura RJ",
            status="EM_ANDAMENTO", data_evento=date(2025, 5, 10), local_evento="Orla Copacabana",
            cidade="Rio de Janeiro", estado="RJ", capacidade_maxima=8000, etapa=1
        ),
    ]
    db.add_all(projetos)
    db.commit()

def seed_usuarios(db: Session):
    if db.query(Usuario).first():
        return
    
    usuarios = [
        Usuario(
            email="admin@cscdoesporte.com",
            nome="Administrador",
            senha_hash=get_password_hash("admin123"),
            perfil="ADMIN"
        ),
        Usuario(
            email="gestor@cscdoesporte.com",
            nome="Gestor Comercial",
            senha_hash=get_password_hash("gestor123"),
            perfil="GESTOR",
            centro_custo_id=1
        ),
    ]
    db.add_all(usuarios)
    db.commit()

def seed_dados_financeiros(db: Session):
    if db.query(FatoOrcamento).first():
        return
    
    tempos = db.query(DimTempo).filter(DimTempo.ano == 2025, DimTempo.dia == 1).all()
    tempo_dict = {t.mes: t.id for t in tempos}
    
    centros = db.query(DimCentroCusto).all()
    contas = db.query(DimConta).all()
    projetos = db.query(DimProjeto).all()
    
    receita_ids = [c.id for c in contas if c.tipo == 'RECEITA']
    despesa_ids = [c.id for c in contas if c.tipo == 'DESPESA']
    
    import random
    for mes in range(1, 7):
        tempo_id = tempo_dict.get(mes)
        if not tempo_id:
            continue
        
        for projeto in projetos:
            for conta_id in receita_ids[:2]:
                valor_base = random.randint(50000, 200000)
                db.add(FatoOrcamento(
                    tempo_id=tempo_id, centro_custo_id=centros[0].id, conta_id=conta_id,
                    projeto_id=projeto.id, valor_orcado=Decimal(valor_base),
                    versao_orcamento="V1", ano_referencia=2025, created_by=1
                ))
                
                variacao_proj = random.uniform(0.9, 1.1)
                db.add(FatoProjecao(
                    tempo_id=tempo_id, centro_custo_id=centros[0].id, conta_id=conta_id,
                    projeto_id=projeto.id, valor_projetado=Decimal(int(valor_base * variacao_proj)),
                    versao=1, status="APROVADO", created_by=1
                ))
                
                variacao_real = random.uniform(0.85, 1.15)
                db.add(FatoRealizado(
                    tempo_id=tempo_id, centro_custo_id=centros[0].id, conta_id=conta_id,
                    projeto_id=projeto.id, valor_realizado=Decimal(int(valor_base * variacao_real))
                ))
            
            for conta_id in despesa_ids[:2]:
                valor_base = random.randint(20000, 80000)
                db.add(FatoOrcamento(
                    tempo_id=tempo_id, centro_custo_id=centros[1].id, conta_id=conta_id,
                    projeto_id=projeto.id, valor_orcado=Decimal(valor_base),
                    versao_orcamento="V1", ano_referencia=2025, created_by=1
                ))
                
                variacao_real = random.uniform(0.9, 1.2)
                db.add(FatoRealizado(
                    tempo_id=tempo_id, centro_custo_id=centros[1].id, conta_id=conta_id,
                    projeto_id=projeto.id, valor_realizado=Decimal(int(valor_base * variacao_real))
                ))
    
    db.commit()


def seed_atletas_metricas(db: Session):
    if db.query(FatoAtletasMetricas).first():
        return
    
    projetos = db.query(DimProjeto).all()
    categorias = db.query(DimCategoriaAtleta).all()
    tempos = db.query(DimTempo).filter(DimTempo.ano == 2025, DimTempo.dia == 1).all()
    tempo_dict = {t.mes: t.id for t in tempos}
    
    cenarios = ['ORCADO', 'PROJETADO', 'REALIZADO']
    
    import random
    for projeto in projetos:
        for categoria in categorias[:5]:
            tempo_id = tempo_dict.get(1)
            for cenario in cenarios:
                qtd = random.randint(100, 500)
                qtd_pago = int(qtd * random.uniform(0.7, 0.9))
                qtd_cortesia = qtd - qtd_pago
                tkt = categoria.valor_inscricao_padrao or Decimal(str(random.randint(80, 200)))
                inscr = Decimal(str(qtd_pago)) * tkt
                custo_kit = categoria.custo_kit_padrao or Decimal(str(random.randint(30, 60)))
                
                db.add(FatoAtletasMetricas(
                    projeto_id=projeto.id,
                    categoria_atleta_id=categoria.id,
                    tempo_id=tempo_id,
                    cenario=cenario,
                    qtd_atletas=qtd,
                    qtd_atletas_pago=qtd_pago,
                    qtd_atletas_cortesia=qtd_cortesia,
                    tkt_medio=tkt,
                    inscricao=inscr,
                    custo_kit_unitario=custo_kit,
                    versao_projecao=1,
                    created_by=1
                ))
    db.commit()


def seed_atletas_satelite(db: Session):
    if db.query(FatoAtletasCanais).first():
        return
    
    projetos = db.query(DimProjeto).all()
    categorias = db.query(DimCategoriaAtleta).all()
    tempos = db.query(DimTempo).filter(DimTempo.ano == 2025, DimTempo.dia == 1).all()
    tempo_dict = {t.mes: t.id for t in tempos}
    
    import random
    canais = ['SITE', 'GRUPOS', 'APPAI']
    tipos_kit = ['VIP', 'PLUS', 'SUPER', 'PRODUTO']
    tipos_custo = ['AGUA', 'ISOTONICO', 'HIDRATACAO', 'NUMERO_PEITO', 'CHIP', 'ALFINETE', 'IDENTIFICACAO']
    cenarios = ['ORCADO', 'PROJETADO', 'REALIZADO']
    
    for projeto in projetos:
        for categoria in categorias[:5]:
            tempo_id = tempo_dict.get(1)
            
            for canal in canais:
                for cenario in cenarios:
                    qtd = random.randint(50, 300)
                    tkt = Decimal(str(random.randint(80, 200)))
                    inscr = Decimal(str(qtd)) * tkt
                    db.add(FatoAtletasCanais(
                        projeto_id=projeto.id,
                        categoria_atleta_id=categoria.id,
                        tempo_id=tempo_id,
                        canal=canal,
                        cenario=cenario,
                        qtd_atletas=qtd,
                        tkt_medio=tkt,
                        inscricao=inscr,
                        versao_projecao=1,
                        created_by=1
                    ))
            
            for tipo_kit in tipos_kit:
                for cenario in cenarios:
                    qtd = random.randint(20, 150)
                    tkt = Decimal(str(random.randint(100, 250)))
                    inscr = Decimal(str(qtd)) * tkt
                    custo = Decimal(str(random.randint(30, 80)))
                    db.add(FatoAtletasKits(
                        projeto_id=projeto.id,
                        categoria_atleta_id=categoria.id,
                        tempo_id=tempo_id,
                        tipo_kit=tipo_kit,
                        cenario=cenario,
                        qtd_kit=qtd,
                        tkt_medio=tkt,
                        inscricao=inscr,
                        custo_unitario=custo,
                        versao_projecao=1,
                        created_by=1
                    ))
            
            for tipo_custo in tipos_custo:
                for cenario in cenarios:
                    custo_unit = Decimal(str(random.uniform(0.5, 15))).quantize(Decimal('0.01'))
                    qtd_atleta = Decimal(str(random.uniform(0.5, 3))).quantize(Decimal('0.01'))
                    custo_total = custo_unit * qtd_atleta * Decimal('100')
                    db.add(FatoAtletasCustos(
                        projeto_id=projeto.id,
                        categoria_atleta_id=categoria.id,
                        tempo_id=tempo_id,
                        tipo_custo=tipo_custo,
                        cenario=cenario,
                        custo_unitario=custo_unit,
                        qtd_por_atleta=qtd_atleta,
                        custo_total=custo_total,
                        versao_projecao=1,
                        created_by=1
                    ))
    
    db.commit()


def main():
    db = SessionLocal()
    try:
        print("Seeding tempo...")
        seed_tempo(db)
        print("Seeding centros de custo...")
        seed_centros_custo(db)
        print("Seeding contas...")
        seed_contas(db)
        print("Seeding categorias atletas...")
        seed_categorias_atletas(db)
        print("Seeding projetos...")
        seed_projetos(db)
        print("Seeding usuarios...")
        seed_usuarios(db)
        print("Seeding dados financeiros...")
        seed_dados_financeiros(db)
        print("Seeding atletas metricas...")
        seed_atletas_metricas(db)
        print("Seeding atletas satelite (canais, kits, custos)...")
        seed_atletas_satelite(db)
        print("Seed completed!")
    finally:
        db.close()

if __name__ == "__main__":
    main()
