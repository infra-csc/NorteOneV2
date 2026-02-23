from datetime import date, datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from app.core.database import SessionLocal, engine, Base
from app.core.security import get_password_hash
from app.models.dimensoes import DimTempo, DimCentroCusto, DimProjeto, DimCategoriaAtleta
from app.models.user import Usuario
from app.models.cadastro_evento import DistanciaOpcao

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
            perfil_acesso_id=1
        ),
        Usuario(
            email="gestor@cscdoesporte.com",
            nome="Gestor Comercial",
            senha_hash=get_password_hash("gestor123"),
            perfil_acesso_id=2,
            centro_custo_id=1
        ),
    ]
    db.add_all(usuarios)
    db.commit()

def seed_distancias(db: Session):
    if db.query(DistanciaOpcao).first():
        return
    distancias = ['3k', '5k', '10k', '13k', '15k', '21k', '42k']
    for i, nome in enumerate(distancias):
        db.add(DistanciaOpcao(nome=nome, ordem=i, ativo=True))
    db.commit()


def main():
    db = SessionLocal()
    try:
        print("Seeding tempo...")
        seed_tempo(db)
        print("Seeding centros de custo...")
        seed_centros_custo(db)
        print("Seeding categorias atletas...")
        seed_categorias_atletas(db)
        print("Seeding projetos...")
        seed_projetos(db)
        print("Seeding usuarios...")
        seed_usuarios(db)
        print("Seeding distancias...")
        seed_distancias(db)
        print("Seed completed!")
    finally:
        db.close()

if __name__ == "__main__":
    main()
