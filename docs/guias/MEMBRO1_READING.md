# Guia do Membro 1: Reading Challenge

Este guia mostra **onde cada tarefa do Reading Challenge se encaixa no projeto atual** e quais regras ele já
impõe. A base é a branch `Membro4` (commit `e48fa44` ou posterior). Antes de começar, leia no `README.md` as seções
"Banco de dados e migrações", "Contas e login" e "Formato dos erros da API".

```bash
python -m app.migrar                 # banco na versão atual
pytest                               # tudo verde antes de mexer
```

---

## 1. Modelos (ReadingChallenge, ReadingText, ReadingQuestion, ReadingAttempt)

- **Use SQLModel (`class X(SQLModel, table=True)`), e não `declarative_base()` puro.** O SQLModel é o SQLAlchemy
  com Pydantic por cima. O Alembic (`migrations/env.py`) e os testes enxergam **só** o `SQLModel.metadata`. Uma
  tabela feita com um `Base` próprio do SQLAlchemy fica invisível para as migrações e para os testes.
- Coloque os modelos em `app/models.py`, que é o arquivo que `migrations/env.py` importa. Se preferir um arquivo
  próprio (ex.: `app/models_reading.py`), importe-o em `app/models.py`. Sem isso, o Alembic não vê as tabelas.
- **Dono:** o que é do usuário leva `usuario_id: int = Field(foreign_key="usuario.id", index=True)`. É o caso de
  `ReadingChallenge` e `ReadingAttempt`. Um texto (`ReadingText`) pode ser compartilhado entre usuários, como a
  tabela `waveform`.
- **Datas:** `Field(default_factory=agora)`, com `agora()` de `app/models.py` (horário de Brasília, sem fuso,
  como o resto do banco).
- **Listas e objetos** (alternativas, justificativas): coluna JSON, como em `Waveform.peaks`:
  `alternativas: list[str] = Field(sa_column=Column(JSON, nullable=False))`.
- Dê **nome** a toda FK e UNIQUE (`name="fk_..."`, `name="uq_..."`). O autogenerate gera FK sem nome, e o
  downgrade quebra. Foi um problema real no B5 (veja `migrations/versions/0003_posse_dos_decks.py`).

## 2. Migrações (Alembic)

O banco está na **0006**. Os três membros vão criar migrações **em paralelo**, e isso conflita. **Combinado:**

| Membro | Faixa de `--rev-id` |
|---|---|
| Membro 1 (Reading) | `0101`, `0102`, … |
| Membro 2 (Speaking) | `0201`, … |
| Membro 3 (Writing) | `0301`, … |

```bash
python -m alembic revision --autogenerate -m "reading challenge" --rev-id 0101
# REVISE o arquivo gerado (nomes de FK/UNIQUE, tipos JSON)
python -m app.migrar        # aplica (com backup no SQLite). Não use "alembic upgrade" direto.
pytest tests/test_migracoes.py   # falha se um modelo não tiver migração correspondente
```

A sua primeira migração tem `down_revision = "0006"`. Os outros membros também vão partir da 0006. Na integração,
o Membro 4 junta as "cabeças" com `alembic merge`. **Não edite as migrações 0001 a 0006.**

## 3. Busca dos textos (MediaWiki/Wikipedia e domínio público)

- A regra de negócio fica em `app/services/` (ex.: `app/services/reading_textos.py`), **sem FastAPI**. A rota só
  valida a entrada e chama o serviço.
- **Siga o padrão de `app/services/dicionario.py`**, que já consulta a Wikimedia (Wiktionary):
  - uma `requests.Session()` reaproveitada;
  - **User-Agent identificado** (a Wikimedia exige; copie o de `dicionario.py`);
  - **`timeout=` em toda chamada**;
  - uma exceção própria para "fonte indisponível" (ex.: `DicionarioIndisponivel`).
- A Wikipedia entrega o texto já sem HTML com
  `action=query&prop=extracts&explaintext=1&format=json` (e `list=random&rnnamespace=0` para artigos
  aleatórios). Isso reduz bastante o trabalho de limpeza.
- Para obras em domínio público, faça um **adaptador com a mesma interface** do serviço da Wikipedia. Exemplo de
  fonte: Project Gutenberg, via a API Gutendex. Assim, trocar ou somar fontes não muda a rota.
- **Limpeza e seleção** (referências `[1]`, seções vazias, listas, conteúdo inadequado) em funções **puras**
  (`str → str`), fáceis de testar sem rede.
- Contagem de palavras e tempo limite: funções puras (ex.: `limite_segundos = palavras / ppm * 60`).

## 4. Rotas (FastAPI)

- Crie `app/api/reading.py` e registre-o na tupla de `app/main.py` (`for modulo in (...)`).
- **Prefixo `/api/reading`** (ex.: `POST /api/reading/challenges`). Toda a API do projeto fica em `/api/...`, e o
  teste de proteção só cobre esse prefixo.
- **Login obrigatório:**
  `router = APIRouter(prefix="/api/reading", tags=["reading"], dependencies=[Depends(usuario_atual)])`.
  O teste `tests/test_protecao_api.py` **falha** se uma rota `/api` responder sem login.
- **Isolamento:** um recurso de outro usuário responde **404**, igual a um que não existe. Copie o padrão
  `_deck()` de `app/api/decks.py` (busca o recurso e compara `usuario_id`).
- **Schemas** de entrada e saída em `app/schemas.py` (Pydantic). Valide a resposta da LLM com Pydantic **antes**
  de usar ou gravar.
- Chamadas bloqueantes (HTTP, LLM): use rotas `def` (o FastAPI as roda numa thread, como em `api/legendas.py`) ou
  `asyncio.to_thread`.

## 5. LLM (perguntas e correção)

- Isole a LLM num serviço próprio (ex.: `app/services/llm.py`), com funções que **devolvem objetos Pydantic já
  validados**. As rotas e os testes não conhecem o SDK.
- **Chave da API:** campo novo em `Configuracoes` (`app/config.py`), lido do `.env`, e documentado no
  `.env.example` **sem o valor real**. O app precisa **subir sem a chave** (testes e dev); só a geração falha, com
  um erro claro.
- **Custo:** cada chamada custa dinheiro. Limite por conta com o mesmo limitador dos tokens de legenda
  (`app/api/legendas.py`, chave `usuario:<id>`), mas com outro espaço (ex.: `"reading"`).
- **"Exatamente cinco perguntas":** valide com Pydantic (`Field(min_length=5, max_length=5)`). Se vier inválido,
  tente de novo uma vez e então use o **fallback**.

## 6. Erros (falha da API externa ou da LLM)

O formato já é padronizado (`app/erros.py`):

```python
from app.erros import ErroDaApi
raise ErroDaApi(502, "Não foi possível gerar as perguntas agora. Tente de novo.", codigo="llm_indisponivel")
```

- Fonte de texto ou LLM fora do ar: **502**. O `codigo` padrão é `servico_externo_indisponivel`, ou use um próprio.
- **Não capture `Exception` genérica só para devolver 500.** O app já transforma qualquer erro inesperado em 500
  padrão, com a stack no log.
- `codigo` novo? Inclua em `CODIGOS` (`app/erros.py`), na tabela do README e num teste em `tests/test_erros.py`.

## 7. Telas (leitura com timer e as cinco questões)

- **Página:** template em `app/templates/paginas/` e rota em `app/api/paginas.py` com `_pagina_protegida(...)`
  (sem login, leva ao login e depois volta).
- **JS:** `app/static/js/paginas/reading.js`, com `registrarPagina("reading", (raiz) => { ...; return limpeza; })`,
  importado em `app/static/js/main.js`.
- **Chamadas à API:** acrescente em `app/static/js/nucleo/api.js` e use `requisitarJSON`. Ele já trata a sessão
  vencida (vai ao login) e o formato de erro (`erro.message`, `erro.codigo`).
- **Timer:** **já existe** `contagemRegressiva(segundos, aCadaSegundo, aoTerminar)` e `formatarTempo(segundos)` em
  `app/static/js/nucleo/interface.js` (usados na tela de tokens). Cancele a contagem na limpeza da página.
- **"Bloqueio quando o tempo acabar" precisa valer também no servidor:** o timer da tela pode ser burlado. Grave
  o horário de início no banco ao criar o desafio e confira o tempo na submissão (com uma pequena tolerância).
- **Telas vazias** (ex.: "você ainda não fez nenhum desafio"): `app/static/js/componentes/estado-vazio.js`.

## 8. Testes

- Fixtures prontas em `tests/conftest.py`:
  - `entrar_como("ana@exemplo.com")` → navegador logado (use dois para testar isolamento);
  - `engine_teste` → para conferir o que foi gravado.
- **Nunca chame a rede ou a LLM de verdade nos testes.** Substitua com `monkeypatch.setattr(servico, "funcao",
  falsa)`. Veja `tests/test_tokens.py` e `tests/test_api_legendas.py`.
- Teste o isolamento (o Bruno recebe 404 nos desafios da Ana), como em `tests/test_isolamento.py`.
- Navegador (opcional, `E2E=1`): `tests/test_e2e_navegador.py` mostra como subir o servidor de teste, simular
  serviços externos e testar páginas.
- Antes de cada commit:
  ```bash
  pytest && ruff check .
  # e no Postgres: TEST_DATABASE_URL=postgresql+psycopg://...@127.0.0.1:5432/shadowing_teste pytest
  ```

## 9. Para o Membro 4 (Docker e deploy no final)

Anote no seu README ou PR:
- bibliotecas novas no `requirements.txt` (**com versão fixa**, como as outras);
- variáveis novas do `.env` (ex.: chave da LLM) e se o app funciona sem elas;
- URLs externas usadas (Wikipedia, Gutendex, API da LLM), porque o servidor de produção precisa alcançá-las.
