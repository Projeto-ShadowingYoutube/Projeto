import json
import os

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlmodel import Session, SQLModel, create_engine

from app import config, db, migrar
from app.main import app
from app.services import llm

# Com TEST_DATABASE_URL definida (só no terminal, nunca no .env), os testes usam esse banco (ex.: o Postgres do
# docker-compose). Sem ela, cada teste usa um SQLite temporário.
URL_BANCO_TESTE = os.environ.get("TEST_DATABASE_URL")


def _conferir_banco_de_teste(url: str) -> None:
    """Os testes apagam tabelas: recusa qualquer banco que não seja claramente de teste."""
    nome = make_url(url).database or ""
    if not nome.endswith("_teste") or url == config.DATABASE_URL:
        pytest.exit(f"TEST_DATABASE_URL precisa apontar para um banco *_teste (recebido: {nome!r}).", returncode=2)


if URL_BANCO_TESTE:
    _conferir_banco_de_teste(URL_BANCO_TESTE)


def limpar_banco(engine) -> None:
    """Apaga as tabelas dos modelos e a de versão do Alembic, deixando o banco de teste vazio."""
    SQLModel.metadata.drop_all(engine)
    with engine.begin() as conexao:
        conexao.execute(text("DROP TABLE IF EXISTS alembic_version"))


@pytest.fixture(autouse=True)
def dados_isolados(tmp_path, monkeypatch):
    """Nenhum teste encosta na pasta dados/ de verdade (vídeos, cache, modelo de fala)."""
    monkeypatch.setattr(config, "PASTA_MIDIA", tmp_path / "midia")
    monkeypatch.setattr(config, "PASTA_MODELOS", tmp_path / "modelos")
    monkeypatch.setattr(config, "ARQUIVO_CACHE_LEGENDAS", tmp_path / "ultimo_video.json")


@pytest.fixture(autouse=True)
def llm_desligada(monkeypatch):
    """Nenhum teste chama a LLM de verdade, mesmo com LLM_CHAVE no .env de quem roda. Para simular respostas, use
    a fixture llm_falsa."""
    monkeypatch.setattr(config, "LLM_CHAVE", "")

    def sem_rede(*args, **kwargs):
        raise AssertionError("teste tentou chamar a LLM de verdade: use a fixture llm_falsa")

    monkeypatch.setattr(llm._sessao, "post", sem_rede)


class LLMFalsa:
    """Substituto da LLM nos testes (fixture llm_falsa). Passa pela validação real de llm.gerar_json.

        llm_falsa.responder(Correcao(nota=8, comentario="ok"))   # objeto Pydantic, dict ou texto cru (JSON inválido)
        llm_falsa.falhar(llm.LLMTempoEsgotado())                  # a próxima chamada levanta este erro
        llm_falsa.chamadas                                        # mensagens enviadas em cada chamada

    As respostas são consumidas em ordem, uma por chamada; uma chamada a mais que o previsto reprova o teste.
    """

    def __init__(self):
        self.fila = []
        self.chamadas = []

    def responder(self, resposta):
        if isinstance(resposta, BaseModel):
            resposta = resposta.model_dump_json()
        elif not isinstance(resposta, str):
            resposta = json.dumps(resposta, ensure_ascii=False)
        self.fila.append(resposta)
        return self

    def falhar(self, erro: Exception):
        self.fila.append(erro)
        return self

    def _chamar(self, mensagens, temperatura, max_tokens):
        self.chamadas.append([dict(m) for m in mensagens])
        if not self.fila:
            raise AssertionError("a LLM foi chamada mais vezes do que o teste previu (use llm_falsa.responder)")
        proxima = self.fila.pop(0)
        if isinstance(proxima, Exception):
            raise proxima
        return proxima


@pytest.fixture()
def llm_falsa(monkeypatch):
    """LLM configurada e simulada: nada sai para a rede. Veja LLMFalsa acima."""
    falsa = LLMFalsa()
    monkeypatch.setattr(config, "LLM_CHAVE", "chave-de-teste")
    monkeypatch.setattr(llm, "_chamar", falsa._chamar)
    return falsa


@pytest.fixture()
def url_banco_externo_teste():
    """URL do banco de TEST_DATABASE_URL, vazio no início e no fim do teste. Sem a variável, o teste é pulado."""
    if not URL_BANCO_TESTE:
        pytest.skip("defina TEST_DATABASE_URL para rodar os testes no Postgres")
    engine = create_engine(URL_BANCO_TESTE)
    limpar_banco(engine)
    yield URL_BANCO_TESTE
    limpar_banco(engine)
    engine.dispose()


@pytest.fixture()
def engine_teste(tmp_path):
    """Banco isolado e vazio para cada teste (o mesmo que o client usa; serve para conferir o que foi gravado)."""
    url = URL_BANCO_TESTE or f"sqlite:///{tmp_path / 'test_estudos.db'}"
    engine = create_engine(url, connect_args=db.opcoes_de_conexao(url))
    if URL_BANCO_TESTE:
        limpar_banco(engine)  # sobras de um teste interrompido
    # create_all deixa os testes rápidos; tests/test_migracoes.py garante que as migrações
    # produzem exatamente este mesmo esquema.
    SQLModel.metadata.create_all(engine)
    yield engine
    if URL_BANCO_TESTE:
        limpar_banco(engine)
    engine.dispose()


@pytest.fixture()
def app_de_teste(engine_teste, monkeypatch):
    """O app apontando para o banco de engine_teste."""
    # O lifespan confere a versão do banco real; no teste, ele não deve encostar nele.
    monkeypatch.setattr(migrar, "verificar_banco", lambda: None)

    def get_session_teste():
        with Session(engine_teste) as session:
            yield session

    app.dependency_overrides[db.get_session] = get_session_teste
    yield app
    app.dependency_overrides.clear()


@pytest.fixture()
def client(app_de_teste):
    """Cliente HTTP de teste, sem login (um navegador que acabou de abrir o site)."""
    with TestClient(app_de_teste) as c:
        yield c


@pytest.fixture()
def entrar_como(app_de_teste):
    """Fábrica de navegadores já logados: entrar_como("ana@exemplo.com") cria a conta e devolve o cliente dela.
    Cada cliente tem os próprios cookies, então dá para simular dois usuários ao mesmo tempo."""
    clientes = []

    def fabricar(email: str, senha: str = "senha-forte-123") -> TestClient:
        cliente = TestClient(app_de_teste)
        clientes.append(cliente)
        resposta = cliente.post("/api/auth/cadastro", json={"email": email, "senha": senha})
        assert resposta.status_code == 201, resposta.text
        return cliente

    yield fabricar
    for cliente in clientes:
        cliente.close()
