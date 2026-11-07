# Guia do Membro 3: Writing Challenge (e Rewrite Challenge)

Este guia mostra **onde cada tarefa do Writing Challenge se encaixa no projeto atual**, quais regras ele já impõe e
**o que já existe para reaproveitar**. A base é a branch `Membro4` (commit `e48fa44` ou posterior). Antes de
começar, leia no `README.md` as seções "Banco de dados e migrações", "Contas e login" e "Formato dos erros da API".

```bash
python -m app.migrar                 # banco na versão atual
pytest                               # tudo verde antes de mexer
```

---

## 1. Modelos (WritingPrompt, WritingAttempt, WritingFeedback)

- **Use SQLModel (`class X(SQLModel, table=True)`), e não `declarative_base()` puro.** O Alembic e os testes
  enxergam **só** o `SQLModel.metadata`. Coloque os modelos em `app/models.py`, ou num arquivo próprio importado
  por ele.
- **Dono:** `WritingAttempt.usuario_id = Field(foreign_key="usuario.id", index=True)`. O feedback e as reescritas
  pertencem à tentativa (`attempt_id`), como o Card pertence ao Deck. Os temas (`WritingPrompt`) são compartilhados
  por todos, sem dono.
- **Estado da tentativa** numa coluna: `rascunho` → `enviada` → `avaliada` (ou `erro_avaliacao`). Com isso, o
  autosave só é aceito no rascunho, e uma avaliação que falhou pode ser refeita.
- **"Persistência da versão original":** o texto enviado **nunca é sobrescrito**. As reescritas vão para linhas
  novas (ex.: `WritingRewrite`, com `feedback_id` ou o índice do problema). O histórico original → feedback →
  rewrite sai dessas ligações.
- **Notas por categoria e trechos apontados:** coluna JSON, como `Waveform.peaks`:
  `Field(sa_column=Column(JSON, nullable=False))`. Guarde também **qual versão do prompt e qual modelo** geraram o
  feedback. Assim, dá para comparar avaliações depois que o prompt mudar (o mesmo princípio de
  `WAVEFORM_VERSAO_ALGORITMO`, no B9).
- **Datas:** `Field(default_factory=agora)` (de `app/models.py`). Dê **nome** a toda FK e UNIQUE. O autogenerate gera
  FK sem nome, e o downgrade quebra (veja a migração `0003`).

## 2. Migrações e os temas (TOEFL/IELTS)

O banco está na **0006**, e os três membros criam migrações em paralelo. **Sua faixa: `0301`, `0302`, …**

```bash
python -m alembic revision --autogenerate -m "writing challenge" --rev-id 0301
# REVISE o arquivo gerado
python -m app.migrar        # aplica. Não use "alembic upgrade" direto.
pytest tests/test_migracoes.py
```

- A primeira migração tem `down_revision = "0006"`. Na integração, o Membro 4 junta as "cabeças" com `alembic merge`.
  **Não edite as migrações 0001 a 0006.**
- **Os temas iniciais entram numa migração de dados separada** (ex.: `0302`, com `op.bulk_insert`). Esquema numa
  migração, dados em outra: fica mais fácil de revisar e de desfazer.
- **Tema aleatório:** `select(WritingPrompt).where(...).order_by(func.random()).limit(1)` (`from sqlalchemy import
  func`). Funciona igual em SQLite e Postgres.

## 3. Rotas (FastAPI)

- Crie `app/api/writing.py` com prefixo **`/api/writing`** (ex.: `POST /api/writing/challenges`,
  `PATCH /api/writing/attempts/{id}` para o autosave, `POST .../submissao`) e registre-o na tupla de `app/main.py`.
- **Login obrigatório:** `APIRouter(..., dependencies=[Depends(usuario_atual)])`. O `tests/test_protecao_api.py`
  **falha** se uma rota `/api` responder sem login.
- **Isolamento:** a tentativa de outro usuário responde **404** (padrão `_deck()` em `app/api/decks.py`).
- **Limite de tamanho do texto no schema** (ex.: `Field(max_length=10000)`). Isso protege o banco e o **custo da
  LLM**, que cobra por tamanho.
- **O timer precisa valer também no servidor:** grave o início ao criar a tentativa e confira o tempo na submissão
  (com uma pequena tolerância). O timer da tela pode ser burlado.
- **Contagem de palavras:** a do servidor é a que vale (para validação e nota). Use a **mesma regra** no JS e no
  Python, para os números da tela e do resultado baterem.

## 4. Editor, contador, timer e autosave (front)

- **Página:** template em `app/templates/paginas/`, rota com `_pagina_protegida(...)` em `app/api/paginas.py`, JS
  em `static/js/paginas/writing.js` com `registrarPagina` (importado em `main.js`).
- **Timer:** **já existe** `contagemRegressiva(segundos, aCadaSegundo, aoTerminar)` e `formatarTempo(segundos)`
  em `app/static/js/nucleo/interface.js`. Cancele a contagem na limpeza da página.
- **Autosave:** **já existe o padrão** em `app/static/js/nucleo/configuracoes.js`, que salva com atraso (*debounce*)
  e tem um `salvarPendentes()` chamado ao sair da página. Copie a ideia: salvar alguns segundos depois de parar de
  digitar, mais uma vez a cada N segundos, e ao sair. Mostre "Salvo às 14:32" para dar confiança.
- **Chamadas à API:** em `app/static/js/nucleo/api.js`, com `requisitarJSON`, que já trata a sessão vencida (vai
  ao login) e o formato de erro (`erro.codigo`). Uma redação nunca deve se perder por causa de uma sessão vencida:
  o autosave já guardou o texto no servidor.

## 5. Correção por IA

- **Um único serviço de LLM compartilhado com os Membros 1 e 2** (ex.: `app/services/llm.py`), com funções que
  devolvem **objetos Pydantic já validados**. Combinem quem cria e a interface.
- **Contrato JSON:** um schema Pydantic com as 5 categorias (gramática, vocabulário, coerência, organização,
  atendimento à tarefa), cada uma com nota e comentário, mais a lista de trechos problemáticos. Valide **antes** de
  gravar. Resposta inválida → uma nova tentativa → erro claro (item 6).
- **Trechos problemáticos:** peça à LLM a **citação exata** do trecho, e não a posição. LLMs erram contagem de
  caracteres. O servidor acha a posição com `texto.find(citacao)` e **descarta** citações que não existem no texto.
  Assim, o destaque nunca fica no lugar errado.
- **Destaque na tela, sem XSS:** o texto da redação foi digitado pelo usuário. **Nunca** o insira com `innerHTML`.
  Monte os pedaços com `textContent` e `<span>` criados com `document.createElement`, como todo o front do projeto
  já faz (veja `static/js/paginas/decks.js`).
- **Chave da API** em `Configuracoes` (`app/config.py`) e no `.env.example`, **sem o valor real**. O app precisa
  subir sem a chave.
- **Custo:** limite por conta com o mesmo limitador dos tokens de legenda (`app/api/legendas.py`, chave
  `usuario:<id>`), noutro espaço (ex.: `"writing"`).

## 6. Timeout e resposta inválida da LLM

O formato de erro já é padronizado (`app/erros.py`):

```python
from app.erros import ErroDaApi
raise ErroDaApi(504, "A correção demorou demais. A sua redação foi salva; tente avaliar de novo.",
                codigo="llm_tempo_esgotado")
```

- **A redação já está salva antes de chamar a LLM.** Uma falha na correção deixa a tentativa em `erro_avaliacao`,
  com um botão "Avaliar de novo". A pessoa nunca perde o texto.
- Defina um **timeout explícito** na chamada da LLM. Sem isso, a requisição pode ficar pendurada.
- `codigo` novo (ex.: `llm_tempo_esgotado`, `llm_resposta_invalida`)? Inclua em `CODIGOS` (`app/erros.py`), na
  tabela do README e num teste em `tests/test_erros.py`.
- Não capture `Exception` genérica só para devolver 500. O app já faz isso, com a stack no log.

## 7. Rewrite Challenge

- **Seleção dos problemas:** a partir dos trechos do feedback (ex.: os N mais graves, ou um por categoria). Isso
  pode ser uma função pura, testável sem LLM.
- **Comparação original × reescrita:** para a parte visual, use `difflib` (biblioteca padrão do Python, sem
  dependência nova), que mostra o que mudou palavra a palavra. A LLM julga se **melhorou**, com o mesmo contrato
  Pydantic.
- Cada reescrita é uma linha nova ligada ao problema original. **Nada é sobrescrito.**

## 8. Testes

- **Nunca chame a LLM de verdade nos testes.** Substitua com `monkeypatch.setattr(servico, "avaliar", falsa)`.
  Teste também a LLM que devolve **JSON inválido**, **citação que não existe no texto** e **timeout**. É aí que
  ficam os bugs.
- **Tamanhos e tipos de redação:** vazia, uma frase, no limite de tamanho, acima do limite (422), com
  caracteres especiais e acentos.
- **Isolamento:** o Bruno recebe 404 na redação da Ana (veja `tests/test_isolamento.py`).
- Fixtures em `tests/conftest.py`: `entrar_como("ana@exemplo.com")` e `engine_teste` (para conferir que a versão
  original continua intacta depois do rewrite).
- Navegador (opcional, `E2E=1`): `tests/test_e2e_navegador.py`. Um bom teste é digitar, esperar o autosave,
  recarregar a página e ver o texto voltar.
- Antes de cada commit: `pytest && ruff check .` (e também no Postgres, com `TEST_DATABASE_URL`).

## 9. Para o Membro 4 (Docker e deploy no final)

Anote no seu README ou PR:
- bibliotecas novas no `requirements.txt` (**com versão fixa**). Provavelmente só o SDK da LLM: `difflib` já vem
  com o Python;
- variáveis novas do `.env` (chave da LLM, timeout, modelo) e se o app funciona sem elas;
- o tempo médio de uma correção, para configurar os timeouts do servidor e do proxy em produção.
