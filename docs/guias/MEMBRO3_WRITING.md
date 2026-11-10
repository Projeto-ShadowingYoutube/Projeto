# Guia do Membro 3: Writing Challenge (e Rewrite Challenge)

Este guia mostra **onde cada tarefa do Writing Challenge se encaixa no projeto atual**, quais regras ele já impõe e
**o que já existe para reaproveitar**. A base é a branch `Membro4` (a partir do commit do B-LLM, que traz o `llm.py` e o `CLAUDE.md`). Antes de começar, leia o **`CLAUDE.md`** (regras do trabalho: base protegida, pontos de encaixe,
processo por blocos) e, no `README.md`, as seções "Banco de dados e migrações", "Contas e login",
"LLM e desafios com IA" e "Formato dos erros da API". **Onde este guia e o `CLAUDE.md` divergirem, vale o
`CLAUDE.md`.** Toda a sua documentação vai no `README_MEMBRO3.md`, nunca no `README.md`.

```bash
python -m app.migrar                 # banco na versão atual
pytest                               # tudo verde antes de mexer
```

---

## 1. Modelos (WritingPrompt, WritingAttempt, WritingFeedback)

- **Use SQLModel (`class X(SQLModel, table=True)`), e não `declarative_base()` puro.** O Alembic e os testes
  enxergam **só** o `SQLModel.metadata`. Coloque os modelos em **`app/models_writing.py`** e importe-o no **seu ponto de encaixe**, no fim de
  `app/models.py` (`import app.models_writing  # noqa: E402, F401`).
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
  `PATCH /api/writing/attempts/{id}` para o autosave, `POST .../submissao`) e registre os routers no **seu ponto de encaixe** em `app/main.py` (`_rotas_das_features`).
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

- **Página:** template em `app/templates/paginas/writing.html`, rota no **seu** `app/api/writing.py` (router
  `paginas`) com `pagina_protegida(...)` de `app/api/paginas.py`, JS em `static/js/paginas/writing.js` com
  `registrarPagina` (importado no seu ponto de encaixe de `main.js`). Botão e CSS: encaixes do `base.html`.
- **Timer:** **já existe** `contagemRegressiva(segundos, aCadaSegundo, aoTerminar)` e `formatarTempo(segundos)`
  em `app/static/js/nucleo/interface.js`. Cancele a contagem na limpeza da página.
- **Autosave:** **já existe o padrão** em `app/static/js/nucleo/configuracoes.js`, que salva com atraso (*debounce*)
  e tem um `salvarPendentes()` chamado ao sair da página. Copie a ideia: salvar alguns segundos depois de parar de
  digitar, mais uma vez a cada N segundos, e ao sair. Mostre "Salvo às 14:32" para dar confiança.
- **Chamadas à API:** crie `app/static/js/nucleo/api-writing.js`, com `requisitarJSON`/`enviarJSON` de `api.js`
  (que é base: não o altere), que já trata a sessão vencida (vai
  ao login) e o formato de erro (`erro.codigo`). Uma redação nunca deve se perder por causa de uma sessão vencida:
  o autosave já guardou o texto no servidor.

## 5. Correção por IA

- **O serviço já existe: `app/services/llm.py`** (README, seção "LLM e desafios com IA"). **Não o altere**
  (`CLAUDE.md`, seção 3). Os prompts da sua feature ficam no seu serviço (ex.: `app/services/writing_llm.py`):
  ```python
  from app.services import llm
  resultado = llm.gerar_json(sistema=INSTRUCOES, usuario=texto, modelo=SeuModeloPydantic)
  ```
  Ele manda o schema do modelo, valida a resposta, tenta de novo uma vez se vier fora do formato e converte as
  falhas no erro padrão (502/503/504). A chamada é bloqueante: rota `def` ou `asyncio.to_thread`.
- **Provedor:** Gemini Flash (grátis no desenvolvimento, pago no deploy; decisão da equipe). Crie a **sua** chave em
  https://aistudio.google.com/apikey e coloque em `LLM_CHAVE` no seu `.env` (nunca no Git).
- **Cota diária (10 desafios por dia, decisão da equipe):** `Depends(exigir_cota("writing"))` (de `app/api/llm.py`)
  **só** na rota que cria o desafio.
- **Aviso de privacidade:** mostre `criarAvisoIA(aviso)` (`componentes/aviso-ia.js`, texto de `GET /api/llm/situacao`)
  na tela, **antes** do envio.
- **Grave `llm.modelo_em_uso()`** junto do feedback (item 1).
- **Contrato JSON:** um schema Pydantic com as 5 categorias (gramática, vocabulário, coerência, organização,
  atendimento à tarefa), cada uma com nota e comentário, mais a lista de trechos problemáticos. Valide **antes** de
  gravar. Resposta inválida → uma nova tentativa → erro claro (item 6).
- **Trechos problemáticos:** peça à LLM a **citação exata** do trecho, e não a posição. LLMs erram contagem de
  caracteres. O servidor acha a posição com `texto.find(citacao)` e **descarta** citações que não existem no texto.
  Assim, o destaque nunca fica no lugar errado.
- **Destaque na tela, sem XSS:** o texto da redação foi digitado pelo usuário. **Nunca** o insira com `innerHTML`.
  Monte os pedaços com `textContent` e `<span>` criados com `document.createElement`, como todo o front do projeto
  já faz (veja `static/js/paginas/decks.js`).
- **Custo por chamada:** limite o tamanho da redação no schema (item 3); a cota diária já está acima.

## 6. Timeout e resposta inválida da LLM

As falhas da LLM já viram o erro padrão sozinhas (`app/services/llm.py`: 502 `llm_indisponivel`, 504
`llm_tempo_esgotado`, 502 `llm_resposta_invalida`). Para marcar a tentativa e dar uma mensagem própria, capture e
relance:

```python
from app.services import llm
try:
    feedback = llm.gerar_json(sistema=INSTRUCOES, usuario=texto, modelo=Feedback)
except llm.ErroLLM as erro:
    tentativa.estado = "erro_avaliacao"; session.add(tentativa); session.commit()
    if isinstance(erro, llm.LLMTempoEsgotado):
        raise llm.LLMTempoEsgotado("A correção demorou demais. A sua redação foi salva; tente avaliar de novo.") from erro
    raise
```

- **A redação já está salva antes de chamar a LLM.** Uma falha na correção deixa a tentativa em `erro_avaliacao`,
  com um botão "Avaliar de novo". A pessoa nunca perde o texto.
- O timeout já é explícito no `llm.py` (`LLM_TIMEOUT_SEGUNDOS`, 60 s por padrão).
- `codigo` novo? Use `ErroDaApi(..., codigo="...")` sem alterar `app/erros.py`, documente no `README_MEMBRO3.md`
  e teste nos seus testes.
- Não capture `Exception` genérica só para devolver 500. O app já faz isso, com a stack no log.

## 7. Rewrite Challenge

- **Seleção dos problemas:** a partir dos trechos do feedback (ex.: os N mais graves, ou um por categoria). Isso
  pode ser uma função pura, testável sem LLM.
- **Comparação original × reescrita:** para a parte visual, use `difflib` (biblioteca padrão do Python, sem
  dependência nova), que mostra o que mudou palavra a palavra. A LLM julga se **melhorou**, com o mesmo contrato
  Pydantic.
- Cada reescrita é uma linha nova ligada ao problema original. **Nada é sobrescrito.**

## 8. Testes

- **Testes em `tests/writing/`** (fixtures próprias em `tests/writing/conftest.py`; o `tests/conftest.py` é base).
- **Nunca chame a LLM de verdade nos testes.** Use a fixture **`llm_falsa`**: `llm_falsa.responder({...})`,
  `llm_falsa.responder("não é JSON")`, `llm_falsa.falhar(llm.LLMTempoEsgotado())`.
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

Anote no `README_MEMBRO3.md`, seção "Para o Membro 4" (ver `CLAUDE.md`, seção 10):
- bibliotecas novas, no seu bloco do `requirements.txt` (**com versão fixa**). Provavelmente nenhuma: o `llm.py`
  usa o `requests` e o `difflib` já vem com o Python;
- variáveis novas do `.env`, se houver (só com a confirmação do usuário; as da LLM já existem);
- o tempo médio de uma correção, para configurar os timeouts do servidor e do proxy em produção.
