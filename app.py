"""
QuintoAndar × Prudential — Embedded Insurance (protótipo)
Flask + PostgreSQL, pronto para deploy no Render.

Rotas:
  GET  /                      -> app (home / imóvel / proposta) numa página
  GET  /api/imoveis           -> lista de imóveis (do banco)
  GET  /api/imoveis/<id>      -> um imóvel + galeria
  GET  /api/planos            -> planos de seguro Prudential
  POST /api/propostas         -> grava proposta + plano escolhido
  GET  /api/propostas         -> lista propostas (painel simples p/ a proposta comercial)
  GET  /admin                 -> painel simples com propostas + take-rate do seguro
"""
import os
import json
from datetime import datetime
from decimal import Decimal

from flask import Flask, render_template, request, jsonify, abort
from sqlalchemy import (create_engine, Column, Integer, String, Text, Numeric,
                        DateTime, ForeignKey, func)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, scoped_session

# ----------------------------------------------------------------------------
# Configuração do banco
# ----------------------------------------------------------------------------
# No Render, defina DATABASE_URL nas Environment Variables (o Postgres do Render
# fornece essa string). Localmente, cai para SQLite para facilitar testes.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///local.db")

# O Render às vezes entrega a URL como 'postgres://', mas o SQLAlchemy quer
# 'postgresql://'. Corrigimos aqui.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False))
Base = declarative_base()


# ----------------------------------------------------------------------------
# Modelos
# ----------------------------------------------------------------------------
class Imovel(Base):
    __tablename__ = "imoveis"
    id = Column(Integer, primary_key=True)
    titulo = Column(String(200), nullable=False)
    endereco = Column(String(200), nullable=False)
    bairro = Column(String(100))
    cidade = Column(String(100), default="São Paulo")
    aluguel = Column(Numeric(10, 2), nullable=False)
    condominio = Column(Numeric(10, 2), default=0)
    iptu = Column(Numeric(10, 2), default=0)
    seguro_incendio = Column(Numeric(10, 2), default=0)   # obrigatório, padrão QuintoAndar
    area = Column(Integer)          # m²
    quartos = Column(Integer)
    vagas = Column(Integer)
    mobiliado = Column(Integer, default=0)   # 0/1
    descricao = Column(Text)
    badges = Column(String(200), default="")     # csv: "Exclusivo,Anúncio novo"
    amenidades = Column(Text, default="")        # csv
    galeria = Column(Text, default="")           # csv de chaves de imagem (svg keys)

    @property
    def total(self):
        # aluguel + encargos + seguro incêndio obrigatório (padrão QuintoAndar)
        return (float(self.aluguel or 0) + float(self.condominio or 0)
                + float(self.iptu or 0) + float(self.seguro_incendio or 0))

    def to_dict(self):
        return {
            "id": self.id,
            "titulo": self.titulo,
            "endereco": self.endereco,
            "bairro": self.bairro,
            "cidade": self.cidade,
            "aluguel": float(self.aluguel or 0),
            "condominio": float(self.condominio or 0),
            "iptu": float(self.iptu or 0),
            "seguro_incendio": float(self.seguro_incendio or 0),
            "total": self.total,
            "area": self.area,
            "quartos": self.quartos,
            "vagas": self.vagas,
            "mobiliado": bool(self.mobiliado),
            "descricao": self.descricao,
            "badges": [b for b in (self.badges or "").split(",") if b],
            "amenidades": [a for a in (self.amenidades or "").split(",") if a],
            "galeria": [g for g in (self.galeria or "").split(",") if g],
        }


class PlanoSeguro(Base):
    """Proteção Financeira do Inquilino (Prudential).
    Cobre o pagamento do aluguel do inquilino em caso de invalidez total ou
    parcial por acidente, doenças graves/terminais e morte."""
    __tablename__ = "planos_seguro"
    id = Column(Integer, primary_key=True)
    nome = Column(String(100), nullable=False)
    preco = Column(Numeric(10, 2), nullable=False)   # mensal
    cobertura = Column(Text)
    meses_cobertos = Column(Integer, default=0)       # nº de aluguéis pagos pelo seguro
    capital = Column(Numeric(12, 2), default=0)       # indenização por morte/invalidez total
    destaque = Column(Integer, default=0)   # 0/1 -> "MAIS ESCOLHIDO"
    ordem = Column(Integer, default=0)

    def to_dict(self):
        return {
            "id": self.id,
            "nome": self.nome,
            "preco": float(self.preco or 0),
            "cobertura": self.cobertura,
            "meses_cobertos": self.meses_cobertos,
            "capital": float(self.capital or 0),
            "destaque": bool(self.destaque),
        }


class Proposta(Base):
    __tablename__ = "propostas"
    id = Column(Integer, primary_key=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    nome = Column(String(200), nullable=False)
    cpf = Column(String(20))
    email = Column(String(200))
    telefone = Column(String(40))
    inicio = Column(String(20))

    imovel_id = Column(Integer, ForeignKey("imoveis.id"))
    imovel = relationship("Imovel")

    plano_id = Column(Integer, ForeignKey("planos_seguro.id"), nullable=True)
    plano = relationship("PlanoSeguro")

    valor_aluguel = Column(Numeric(10, 2))
    valor_seguro = Column(Numeric(10, 2), default=0)
    valor_total = Column(Numeric(10, 2))

    def to_dict(self):
        return {
            "id": self.id,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
            "nome": self.nome,
            "email": self.email,
            "telefone": self.telefone,
            "imovel": self.imovel.titulo if self.imovel else None,
            "plano": self.plano.nome if self.plano else "Sem proteção",
            "valor_seguro": float(self.valor_seguro or 0),
            "valor_total": float(self.valor_total or 0),
        }


# ----------------------------------------------------------------------------
# Seed (popula o banco na primeira execução)
# ----------------------------------------------------------------------------
def seed():
    db = SessionLocal()
    try:
        if db.query(PlanoSeguro).count() == 0:
            db.add_all([
                PlanoSeguro(nome="Proteção Total", preco=Decimal("34.90"), destaque=1, ordem=1,
                            meses_cobertos=12, capital=Decimal("50000"),
                            cobertura="Paga até 12 aluguéis em caso de invalidez total/parcial "
                                      "por acidente, doenças graves ou terminais · Quitação do "
                                      "contrato + capital de R$ 50.000 em caso de morte."),
                PlanoSeguro(nome="Proteção Essencial", preco=Decimal("18.90"), destaque=0, ordem=2,
                            meses_cobertos=6, capital=Decimal("20000"),
                            cobertura="Paga até 6 aluguéis em caso de invalidez por acidente ou "
                                      "doença grave · Capital de R$ 20.000 em caso de morte."),
                PlanoSeguro(nome="Seguir sem proteção", preco=Decimal("0.00"), destaque=0, ordem=3,
                            meses_cobertos=0, capital=Decimal("0"),
                            cobertura="Você segue sem a proteção financeira da Prudential. Em caso "
                                      "de imprevisto, o aluguel continua sendo sua responsabilidade."),
            ])
        if db.query(Imovel).count() == 0:
            db.add_all([
                Imovel(titulo="Apartamento com 2 quartos, 1 suíte",
                       endereco="Rua Higienópolis, 200", bairro="Higienópolis",
                       aluguel=Decimal("6500"), condominio=Decimal("1900"), iptu=Decimal("674"), seguro_incendio=Decimal("41"),
                       area=90, quartos=2, vagas=1, mobiliado=0,
                       descricao="Apartamento amplo e reformado em Higienópolis, sala ampla, "
                                 "cozinha planejada e suíte com armários. Prédio com portaria 24h.",
                       badges="Exclusivo,Visualizado",
                       amenidades="Portaria 24h,Elevador,Aceita pet,Varanda,Salão de festas,Academia",
                       galeria="im1_4,im1_1,im1_3,im1_2"),
                Imovel(titulo="Kitnet mobiliada com 1 quarto e academia no condomínio",
                       endereco="Rua Otávio Tarquínio de Sousa", bairro="Brooklin Novo",
                       aluguel=Decimal("3200"), condominio=Decimal("520"), iptu=Decimal("173"), seguro_incendio=Decimal("22"),
                       area=30, quartos=1, vagas=1, mobiliado=1,
                       descricao="Studio mobiliado e recém-reformado no Brooklin Novo, com vista "
                                 "para a cidade e varanda integrada. Condomínio com academia, "
                                 "lavanderia e portaria 24h. A poucos passos da Av. Berrini.",
                       badges="Exclusivo,Anúncio novo",
                       amenidades="Mobiliada,Academia,Portaria 24h,Ar-condicionado,Varanda,Lavanderia,Elevador,Aceita pet",
                       galeria="im5_1,im5_2,im5_3,im5_4"),
                Imovel(titulo="Kitnet mobiliada com 1 quarto e academia no condomínio",
                       endereco="Rua Serra de Japi", bairro="Vila Azevedo",
                       aluguel=Decimal("3500"), condominio=Decimal("450"), iptu=Decimal("170"), seguro_incendio=Decimal("24"),
                       area=35, quartos=1, vagas=0, mobiliado=1,
                       descricao="Kitnet mobiliada, ideal para quem busca praticidade. "
                                 "Condomínio com academia e lavanderia compartilhada.",
                       badges="Anúncio novo",
                       amenidades="Mobiliada,Academia,Lavanderia,Elevador,Próximo ao metrô",
                       galeria="im4_1,im4_2,im4_3,im4_4"),
                Imovel(titulo="Apartamento amplo com 3 quartos e varanda gourmet",
                       endereco="Rua Vergueiro, 3000", bairro="Vila Mariana",
                       aluguel=Decimal("5400"), condominio=Decimal("1200"), iptu=Decimal("380"), seguro_incendio=Decimal("35"),
                       area=110, quartos=3, vagas=2, mobiliado=0,
                       descricao="Apartamento espaçoso na Vila Mariana com varanda gourmet, "
                                 "3 dormitórios e 2 vagas. Excelente localização perto do metrô.",
                       badges="Exclusivo",
                       amenidades="Varanda gourmet,Portaria 24h,Elevador,Aceita pet,Playground,Piscina",
                       galeria="im2_2,im2_3,im2_4,im2_1"),
                Imovel(titulo="Apartamento vazio com 1 quarto, pronto para decorar",
                       endereco="Rua Cardeal Arcoverde, 850", bairro="Pinheiros",
                       aluguel=Decimal("2400"), condominio=Decimal("480"), iptu=Decimal("140"), seguro_incendio=Decimal("18"),
                       area=42, quartos=1, vagas=0, mobiliado=0,
                       descricao="Apartamento simples e bem cuidado em Pinheiros, sem mobília, "
                                 "pronto para você decorar do seu jeito. Condomínio com playground "
                                 "e área de bicicletário.",
                       badges="Anúncio novo",
                       amenidades="Playground,Portaria 24h,Elevador,Bicicletário",
                       galeria="im3_1,im3_2,im3_4,im3_3"),
            ])
        db.commit()
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(engine)
    seed()


# ----------------------------------------------------------------------------
# App Flask
# ----------------------------------------------------------------------------
# Caminhos absolutos baseados na localização deste arquivo — garante que o Flask
# ache templates/ e static/ mesmo que o diretório de trabalho no Render seja outro.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)


@app.teardown_appcontext
def remove_session(exc=None):
    SessionLocal.remove()


@app.route("/health")
def health():
    """Diagnóstico: mostra se o banco está acessível e populado, e se acha os templates."""
    info = {"app": "ok", "database_url_scheme": DATABASE_URL.split("://")[0]}
    # diagnóstico de templates/estáticos
    tpl_dir = os.path.join(BASE_DIR, "templates")
    info["base_dir"] = BASE_DIR
    info["templates_existe"] = os.path.isdir(tpl_dir)
    info["templates_encontrados"] = (
        sorted(os.listdir(tpl_dir)) if os.path.isdir(tpl_dir) else []
    )
    try:
        db = SessionLocal()
        info["imoveis"] = db.query(Imovel).count()
        info["planos"] = db.query(PlanoSeguro).count()
        info["propostas"] = db.query(Proposta).count()
        info["db"] = "ok"
    except Exception as e:
        info["db"] = "erro"
        info["erro"] = str(e)
        return jsonify(info), 500
    return jsonify(info)


@app.route("/")
def index():
    resp = render_template("index.html")
    from flask import make_response
    resp = make_response(resp)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@app.route("/api/imoveis")
def api_imoveis():
    db = SessionLocal()
    imoveis = db.query(Imovel).all()
    return jsonify([i.to_dict() for i in imoveis])


@app.route("/api/imoveis/<int:imovel_id>")
def api_imovel(imovel_id):
    db = SessionLocal()
    imovel = db.get(Imovel, imovel_id)
    if not imovel:
        abort(404)
    return jsonify(imovel.to_dict())


@app.route("/api/planos")
def api_planos():
    db = SessionLocal()
    planos = db.query(PlanoSeguro).order_by(PlanoSeguro.ordem).all()
    return jsonify([p.to_dict() for p in planos])


@app.route("/api/propostas", methods=["POST"])
def criar_proposta():
    data = request.get_json(force=True)
    db = SessionLocal()

    imovel = db.get(Imovel, int(data.get("imovel_id")))
    if not imovel:
        return jsonify({"erro": "imóvel inválido"}), 400

    plano = None
    valor_seguro = Decimal("0")
    if data.get("plano_id"):
        plano = db.get(PlanoSeguro, int(data["plano_id"]))
        if plano:
            valor_seguro = Decimal(str(plano.preco))

    valor_aluguel = Decimal(str(imovel.total))
    valor_total = valor_aluguel + valor_seguro

    prop = Proposta(
        nome=data.get("nome", ""),
        cpf=data.get("cpf", ""),
        email=data.get("email", ""),
        telefone=data.get("telefone", ""),
        inicio=data.get("inicio", ""),
        imovel_id=imovel.id,
        plano_id=plano.id if plano else None,
        valor_aluguel=valor_aluguel,
        valor_seguro=valor_seguro,
        valor_total=valor_total,
    )
    db.add(prop)
    db.commit()
    return jsonify({"ok": True, "id": prop.id, "total": float(valor_total)})


@app.route("/api/propostas")
def listar_propostas():
    db = SessionLocal()
    props = db.query(Proposta).order_by(Proposta.criado_em.desc()).all()
    return jsonify([p.to_dict() for p in props])


@app.route("/admin")
def admin():
    """Painel simples: propostas + take-rate do seguro (métrica-chave da tese)."""
    db = SessionLocal()
    props = db.query(Proposta).order_by(Proposta.criado_em.desc()).all()
    total = len(props)
    com_seguro = sum(1 for p in props if p.plano and float(p.valor_seguro) > 0)
    take_rate = (com_seguro / total * 100) if total else 0
    receita_seguro = sum(float(p.valor_seguro or 0) for p in props)
    return render_template("admin.html", props=props, total=total,
                           com_seguro=com_seguro, take_rate=take_rate,
                           receita_seguro=receita_seguro)


# Inicializa o banco no start, com retry (o Postgres do Render pode demorar a
# aceitar conexões nos primeiros segundos). Não derruba o app se falhar — apenas
# registra o erro no log, para o 500 mostrar a causa real.
import time
import logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("startup")


def init_db_with_retry(tentativas=6, espera=3):
    for i in range(1, tentativas + 1):
        try:
            init_db()
            log.info("Banco inicializado com sucesso (tentativa %s).", i)
            return
        except Exception as e:
            log.warning("Falha ao inicializar o banco (tentativa %s/%s): %s",
                        i, tentativas, e)
            time.sleep(espera)
    log.error("Não foi possível inicializar o banco após %s tentativas.", tentativas)


with app.app_context():
    init_db_with_retry()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
