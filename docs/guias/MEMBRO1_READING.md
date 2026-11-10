# Guia do Membro 1: Reading Challenge

Este guia mostra **onde cada tarefa do Reading Challenge se encaixa no projeto atual** e quais regras ele já
impõe. A base é a branch `Membro4` (a partir do commit do B-LLM, que traz o `llm.py` e o `CLAUDE.md`). Antes de começar, leia o **`CLAUDE.md`** (regras do trabalho: base protegida, pontos de encaixe,
processo por blocos) e, no `README.md`, as seções "Banco de dados e migrações", "Contas e login",
"LLM e desafios com IA" e "Formato dos erros da API". **Onde este guia e o `CLAUDE.md` divergirem, vale o
`CLAUDE.md`.** Toda a sua documentação vai no `README_MEMBRO1.md`, nunca no `README.md`.

```bash
python -m app.migrar                 # banco na versão atual
pytest                               # tudo verde antes de mexer
```

---

## 1. Modelos (ReadingChallenge, ReadingText, ReadingQuestion, ReadingAttempt)

- **Use SQLModel (`class X(SQLModel, table=True)`), e não `declarative_base()` puro.** O SQLModel é o SQLAlchemy
  com Pydantic por cima. O Alembic (`migrations/env.py`) e os testes enxergam **só** o `SQLModel.metadata`. Uma
  tabela feita com um `Base` próprio do SQLAlchemy fica invisível para as migrações e para os testes.
- Coloque os modelos em **`app/models_reading.py`** (importando `Usuario` e `agora` de `app/models.py`) e
  acrescente `import app.models_reading  # noqa: E402, F401` no **seu ponto de encaixe**, no fim de
  `app/models.py` (bloco "# Membro 1 (Reading)"). Sem isso, o Alembic e os testes não veem as tabelas.
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

- Crie `app/api/reading.py` e registre os routers no **seu ponto de encaixe** em `app/main.py`
  (`_rotas_das_features`, bloco "# Membro 1 (Reading)").
- **Prefixo `/api/reading`** (ex.: `POST /api/reading/challenges`). Toda a API do projeto fica em `/api/...`, e o
  teste de proteção só cobre esse prefixo.
- **Login obrigatório:**
  `router = APIRouter(prefix="/api/reading", tags=["reading"], dependencies=[Depends(usuario_atual)])`.
  O teste `tests/test_protecao_api.py` **falha** se uma rota `/api` responder sem login.
- **Isolamento:** um recurso de outro usuário responde **404**, igual a um que não existe. Copie o padrão
  `_deck()` de `app/api/decks.py` (busca o recurso e compara `usuario_id`).
- **Schemas** de entrada e saída em `app/schemas_reading.py` (Pydantic; `app/schemas.py` é base). Valide a resposta da LLM com Pydantic **antes**
  de usar ou gravar.
- Chamadas bloqueantes (HTTP, LLM): use rotas `def` (o FastAPI as roda numa thread, como em `api/legendas.py`) ou
  `asyncio.to_thread`.

## 5. LLM (perguntas e correção)

- **O serviço já existe: `app/services/llm.py`** (README, seção "LLM e desafios com IA"). **Não o altere**
  (`CLAUDE.md`, seção 3). Os prompts da sua feature ficam no seu serviço (ex.: `app/services/reading_llm.py`):
  ```python
  from app.services import llm
  resultado = llm.gerar_json(sistema=INSTRUCOES, usuario=texto, modelo=SeuModeloPydantic)
  ```
  Ele manda o schema do modelo, valida a resposta, tenta de novo uma vez se vier fora do formato e converte as
  falhas no erro padrão (502/503/504). A chamada é bloqueante: rota `def` ou `asyncio.to_thread`.
- **Provedor:** Gemini Flash (grátis no desenvolvimento, pago no deploy; decisão da equipe). Crie a **sua** chave em
  https://aistudio.google.com/apikey e coloque em `LLM_CHAVE` no seu `.env` (nunca no Git).
- **Cota diária (10 desafios por dia, decisão da equipe):** `Depends(exigir_cota("reading"))` (de `app/api/llm.py`)
  **só** na rota que cria o desafio.
- **Aviso de privacidade:** mostre `criarAvisoIA(aviso)` (`componentes/aviso-ia.js`, texto de `GET /api/llm/situacao`)
  na tela, **antes** do envio.
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
- Falhas da LLM já viram o erro padrão sozinhas (`llm_indisponivel`, `llm_tempo_esgotado`...).
- `codigo` novo? Use `ErroDaApi(..., codigo="...")` sem alterar `app/erros.py`, documente no `README_MEMBRO1.md`
  e teste nos seus testes.

## 7. Telas (leitura com timer e as cinco questões)

- **Página:** template em `app/templates/paginas/reading.html` e rota no **seu** `app/api/reading.py` (um router
  `paginas`, sem prefixo) com `pagina_protegida(...)`, importada de `app/api/paginas.py` (exemplo no próprio
  arquivo). Sem login, leva ao login e depois volta. Botão na navbar e CSS: pontos de encaixe do `base.html`.
- **JS:** `app/static/js/paginas/reading.js`, com `registrarPagina("reading", (raiz) => { ...; return limpeza; })`,
  importado no seu ponto de encaixe de `app/static/js/main.js`.
- **Chamadas à API:** crie `app/static/js/nucleo/api-reading.js`, importando `requisitarJSON` e `enviarJSON` de
  `api.js` (que é base: não o altere). Ele já trata a sessão
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
- **Testes em `tests/reading/`** (fixtures próprias em `tests/reading/conftest.py`; o `tests/conftest.py` é base).
- **Nunca chame a rede ou a LLM de verdade nos testes.** LLM: fixture **`llm_falsa`** (README, seção "LLM").
  Wikipedia/Gutendex: `monkeypatch.setattr(servico, "funcao", falsa)`. Veja `tests/test_tokens.py` e `tests/test_api_legendas.py`.
- Teste o isolamento (o Bruno recebe 404 nos desafios da Ana), como em `tests/test_isolamento.py`.
- Navegador (opcional, `E2E=1`): `tests/test_e2e_navegador.py` mostra como subir o servidor de teste, simular
  serviços externos e testar páginas.
- Antes de cada commit:
  ```bash
  pytest && ruff check .
  # e no Postgres: TEST_DATABASE_URL=postgresql+psycopg://...@127.0.0.1:5432/shadowing_teste pytest
  ```

## 9. Para o Membro 4 (Docker e deploy no final)

Anote no `README_MEMBRO1.md`, seção "Para o Membro 4" (ver `CLAUDE.md`, seção 10):
- bibliotecas novas, no seu bloco do `requirements.txt` (**com versão fixa**);
- variáveis novas do `.env`, se houver (só com a confirmação do usuário; a da LLM já existe);
- URLs externas usadas (Wikipedia, Gutendex, API da LLM), porque o servidor de produção precisa alcançá-las.
