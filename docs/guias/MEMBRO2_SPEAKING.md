# Guia do Membro 2: Speaking Challenge (e One Minute Talk)

Este guia mostra **onde cada tarefa do Speaking Challenge se encaixa no projeto atual**, quais regras ele já impõe
e **o que já existe para reaproveitar**. O projeto já grava a voz do usuário, envia o áudio por multipart e o
processa no servidor (a avaliação da fala do estudo). A base é a branch `Membro4` (a partir do commit do B-LLM, que traz o `llm.py` e o `CLAUDE.md`). Antes de começar, leia o **`CLAUDE.md`** (regras do trabalho: base protegida, pontos de encaixe,
processo por blocos) e, no `README.md`, as seções "Banco de dados e migrações", "Contas e login",
"LLM e desafios com IA" e "Formato dos erros da API". **Onde este guia e o `CLAUDE.md` divergirem, vale o
`CLAUDE.md`.** Toda a sua documentação vai no `README_MEMBRO2.md`, nunca no `README.md`.

```bash
python -m app.migrar                 # banco na versão atual
pytest                               # tudo verde antes de mexer
```

---

## 1. Modelos (SpeakingSession, SpeakingQuestion, SpeakingAnswer)

- **Use SQLModel (`class X(SQLModel, table=True)`), e não `declarative_base()` puro.** O Alembic e os testes
  enxergam **só** o `SQLModel.metadata`. Coloque os modelos em **`app/models_speaking.py`** e importe-o no **seu ponto de encaixe**, no fim de
  `app/models.py` (`import app.models_speaking  # noqa: E402, F401`).
- **Dono:** `SpeakingSession.usuario_id = Field(foreign_key="usuario.id", index=True)`. As respostas pertencem à
  sessão (`session_id`), como o Card pertence ao Deck. O dono de uma resposta é o dono da sessão dela.
- **Estado da bateria** numa coluna: `em_andamento` → `processando` → `concluida` / `erro`. É isso que permite
  "processar só depois do término" e mostrar "processando…" na tela.
- **Datas:** `Field(default_factory=agora)` (de `app/models.py`). **Métricas e feedback** (pausas, notas por
  critério): coluna JSON, como `Waveform.peaks`.
- **O áudio não vai para o banco.** Grave a transcrição e as métricas. Se precisar guardar o arquivo, use uma
  pasta dentro de `dados/` (fora do Git) e defina quando ele é apagado.
- Dê **nome** a toda FK e UNIQUE. O autogenerate gera FK sem nome, e o downgrade quebra (veja a migração `0003`).
- **Quantidade de perguntas por bateria:** guarde na própria sessão (ex.: `SpeakingSession.quantidade_perguntas`)
  e valide a faixa no schema Pydantic (ex.: `Field(ge=1, le=10)`). **Não** acrescente coluna em
  `ConfiguracaoEstudo`: é tabela da base. Se quiser que a escolha fique salva como preferência, use uma tabela sua
  (1:1 com o usuário, como `ConfiguracaoEstudo`) ou peça confirmação ao usuário (`CLAUDE.md`, seção 3).

## 2. Migrações (Alembic)

O banco está na **0006**, e os três membros criam migrações em paralelo. **Sua faixa: `0201`, `0202`, …**

```bash
python -m alembic revision --autogenerate -m "speaking challenge" --rev-id 0201
# REVISE o arquivo gerado (nomes de FK/UNIQUE, tipos JSON)
python -m app.migrar        # aplica. Não use "alembic upgrade" direto.
pytest tests/test_migracoes.py
```

A primeira migração tem `down_revision = "0006"`. Na integração, o Membro 4 junta as "cabeças" com `alembic merge`.
**Não edite as migrações 0001 a 0006.**

## 3. Rotas (FastAPI)

- Crie `app/api/speaking.py` com prefixo **`/api/speaking`** (ex.: `POST /api/speaking/sessions`) e registre os routers no **seu ponto de encaixe** em `app/main.py` (`_rotas_das_features`).
- **Login obrigatório:** `APIRouter(..., dependencies=[Depends(usuario_atual)])`. O `tests/test_protecao_api.py`
  **falha** se uma rota `/api` responder sem login.
- **Isolamento:** a sessão de outro usuário responde **404** (padrão `_deck()` em `app/api/decks.py`).
- **Upload do áudio:** copie `app/api/avaliacoes.py`, que já recebe a gravação do navegador:
  - `gravacao: UploadFile = File(...)` e os demais campos com `Form(...)`;
  - **limite de tamanho** lido com `await gravacao.read(LIMITE + 1)` → **413** se passar (60 s de Opus ≈ 0,5 MB);
  - **confira a duração no servidor** (no máximo 60 s mais uma pequena tolerância): o timer da tela pode ser burlado.

## 4. Gravação no navegador (timers de 15 s e 60 s)

- **Reaproveite** `app/static/js/componentes/gravador.js`, que já tem `getUserMedia`, `MediaRecorder`, a montagem
  do `Blob` e a mensagem "Permita o uso do microfone no navegador".
- **Permissão do microfone antes do timer.** O navegador só abre o pedido de permissão a partir de um clique.
  Peça o microfone quando a pessoa clicar em "Começar bateria" e **mantenha o stream aberto**. Assim, a gravação
  pode **começar sozinha** quando os 15 s de preparação acabarem, sem novo clique.
- **Timers:** **já existe** `contagemRegressiva(segundos, aCadaSegundo, aoTerminar)` e `formatarTempo(segundos)`
  em `app/static/js/nucleo/interface.js`. Use a do preparo (15 s) para iniciar a gravação e a da resposta (60 s)
  para pará-la.
- **Formato do áudio:** o Chrome grava `audio/webm;codecs=opus` e o Firefox, `audio/ogg;codecs=opus`. Envie com o
  tipo que o `recorder.mimeType` informar. O servidor converte tudo pelo FFmpeg (item 5), então os dois funcionam.
  O reconhecimento de fala **do navegador** (usado no estudo) só funciona no Chrome e no Edge. O Speaking, com
  Whisper no servidor, funciona também no Firefox.
- **Envio:** crie `app/static/js/nucleo/api-speaking.js` (importando `requisitarJSON` de `api.js`, que é base) e
  envie com `FormData`, como `api.avaliarFala` faz. Não
  defina o `Content-Type` à mão, porque o navegador monta o multipart. Use `requisitarJSON`, que já trata a sessão
  vencida e o formato de erro.
- **Página:** template em `app/templates/paginas/speaking.html`, rota no **seu** `app/api/speaking.py` (router
  `paginas`) com `pagina_protegida(...)` de `app/api/paginas.py`, JS em `static/js/paginas/speaking.js` com
  `registrarPagina` (importado no seu ponto de encaixe de `main.js`). Botão e CSS: encaixes do `base.html`. Na limpeza da página, **pare o
  stream do microfone e cancele os timers**, como faz o `Gravador.encerrar()`.

## 5. Transcrição (Whisper / faster-whisper)

- **É a parte mais pesada do app:** biblioteca nativa (CTranslate2), modelo de centenas de MB e muito uso de CPU.
  Faça um serviço próprio (ex.: `app/services/transcricao.py`), sem FastAPI.
- **Converter antes de transcrever:** `midia.audio_pcm(arquivo, inicio, fim, taxa)` (em `app/services/midia.py`)
  já transforma qualquer áudio em PCM mono com o FFmpeg. O Whisper espera **16 kHz**. Veja
  `app/services/avaliacao.py`, que faz isso com a gravação do usuário num arquivo temporário.
- **Carregue o modelo uma vez só,** sob demanda e protegido por um `Lock`, guardando-o em `config.PASTA_MODELOS`
  (`dados/modelos/`). É o mesmo padrão do Vosk em `app/services/alinhamento.py` (`_carregar_modelo`). Comece com um
  modelo pequeno em CPU (ex.: `base.en` com `compute_type="int8"`).
- **Nunca transcreva dentro da requisição bloqueando o servidor.** Use `await asyncio.to_thread(...)`.
- **"Processamento somente após o término da bateria":** o upload de cada resposta só grava o arquivo e devolve
  logo. Quando a última resposta chega, a sessão vai para `processando`. A tela consulta o estado (polling, como o
  player faz com `/status` do download) até ficar `concluida`.
- O app roda num **único processo** (há estado em memória). Uma fila externa (Celery, RQ) seria mudança de
  infraestrutura: combine antes com o Membro 4.

## 6. Métricas e avaliação por LLM

- Com `word_timestamps=True`, o faster-whisper devolve o início e o fim de cada palavra. Daí saem, em funções
  **puras** e testáveis sem áudio:
  - **duração** (da 1ª à última palavra);
  - **palavras por minuto**;
  - **pausas** (intervalos entre palavras acima de um limiar, ex.: 0,5 s);
  - **% do tempo usado** (duração ÷ 60 s).
- `app/services/avaliacao.py` já mede ritmo e velocidade da fala com tempos de palavras (Vosk). Use como referência.
**LLM (avaliação da fala transcrita):**
- **O serviço já existe: `app/services/llm.py`** (README, seção "LLM e desafios com IA"). **Não o altere**
  (`CLAUDE.md`, seção 3). Os prompts da sua feature ficam no seu serviço (ex.: `app/services/speaking_llm.py`):
  ```python
  from app.services import llm
  resultado = llm.gerar_json(sistema=INSTRUCOES, usuario=texto, modelo=SeuModeloPydantic)
  ```
  Ele manda o schema do modelo, valida a resposta, tenta de novo uma vez se vier fora do formato e converte as
  falhas no erro padrão (502/503/504). A chamada é bloqueante: rota `def` ou `asyncio.to_thread`.
- **Provedor:** Gemini Flash (grátis no desenvolvimento, pago no deploy; decisão da equipe). Crie a **sua** chave em
  https://aistudio.google.com/apikey e coloque em `LLM_CHAVE` no seu `.env` (nunca no Git).
- **Cota diária (10 desafios por dia, decisão da equipe):** `Depends(exigir_cota("speaking"))` (de `app/api/llm.py`)
  **só** na rota que cria o desafio.
- **Aviso de privacidade:** mostre `criarAvisoIA(aviso)` (`componentes/aviso-ia.js`, texto de `GET /api/llm/situacao`)
  na tela, **antes** do envio.
- Feedback estruturado: schema Pydantic com fluência, clareza e conteúdo (nota + comentário).
- **Transcrição (Whisper, Vosk ou outra) é decisão sua** (item 5); o `llm.py` só recebe o texto.

## 7. Erros

O formato já é padronizado (`app/erros.py`):

```python
from app.erros import ErroDaApi
raise ErroDaApi(502, "A avaliação está indisponível agora. A sua transcrição foi salva.", codigo="llm_indisponivel")
```

- Áudio ilegível: **400** (como em `api/avaliacoes.py`). Áudio grande demais: **413**. LLM fora: **502**.
- **Se a avaliação falhar, não perca a transcrição.** Grave-a primeiro e marque a sessão com `erro` na avaliação,
  para dar para reprocessar depois.
- Não capture `Exception` genérica só para devolver 500. O app já faz isso, com a stack no log.

## 8. Testes

- **Testes em `tests/speaking/`** (fixtures próprias em `tests/speaking/conftest.py`; o `tests/conftest.py` é base).
- **Nunca rode o Whisper nem a LLM nos testes comuns.** LLM: fixture **`llm_falsa`**. Transcrição:
  `monkeypatch.setattr(servico, "transcrever", falsa)`, devolvendo palavras com tempos. Assim, as métricas e o fluxo são testados em milissegundos.
- Um teste opcional com o Whisper de verdade (um áudio curto) pode ficar desligado por variável de ambiente, como
  os testes de navegador (`E2E=1`).
- Fixtures em `tests/conftest.py`: `entrar_como("ana@exemplo.com")` (use dois para testar isolamento) e
  `engine_teste`.
- **Microfone em teste automático:** o Chromium do Playwright aceita os argumentos
  `--use-fake-ui-for-media-stream` e `--use-fake-device-for-media-stream`, que geram um microfone falso, sem pedido
  de permissão. Assim dá para testar os timers e a gravação automática. Veja `tests/test_e2e_navegador.py` para
  subir o servidor de teste. O teste manual com o Firefox e o pedido de permissão real continua necessário.
- Antes de cada commit: `pytest && ruff check .` (e também no Postgres, com `TEST_DATABASE_URL`).

## 9. Para o Membro 4 (Docker e deploy no final)

Anote no `README_MEMBRO2.md`, seção "Para o Membro 4" (ver `CLAUDE.md`, seção 10), porque **é a feature que mais muda o Docker**:
- versões de `faster-whisper` (ou da opção escolhida) e dependências, no seu bloco do `requirements.txt`
  (**com versão fixa**);
- qual modelo do Whisper, o tamanho dele e onde fica (baixado no build ou na primeira execução, em `dados/modelos/`);
- **uso de CPU e memória** medido numa transcrição de 60 s, para dimensionar a máquina de produção;
- variáveis novas do `.env`, se houver (só com a confirmação do usuário), e onde ficam os arquivos de áudio.
