# Membro 3 — Writing Challenge + Rewrite Challenge

> Documentação da feature do Membro 3 (branch `Membro3`, criada a partir da `Membro4` no commit `49636dd`).
> Regras do trabalho: `CLAUDE.md`. Guia da feature: `docs/guias/MEMBRO3_WRITING.md`. Nada desta feature vai no
> `README.md`.

## Visão geral

O **Writing Challenge** treina a escrita em inglês no formato das provas TOEFL e IELTS: a pessoa escolhe uma categoria
(ou "Surpresa"), recebe um tema sorteado e escreve uma redação com contador de palavras, timer regressivo e
salvamento automático. Ao enviar, uma IA corrige o texto em cinco categorias (gramática, vocabulário, coerência,
organização e atendimento à tarefa), com nota, comentário e os trechos problemáticos destacados no próprio texto.

O **Rewrite Challenge** vem depois da correção: o sistema escolhe até 3 trechos problemáticos, dá uma instrução de
reescrita para cada um, compara a versão original com a reescrita (palavra a palavra) e a IA avalia se melhorou. O
histórico original → feedback → reescritas fica guardado, e o texto original nunca é sobrescrito.

## Como usar

_(preenchido a partir do W4, quando a tela existir)_

Para a correção por IA funcionar localmente, coloque a **sua** chave do Gemini em `LLM_CHAVE` no `.env` (crie em
https://aistudio.google.com/apikey; nunca no Git). Sem ela, o app sobe normalmente e a correção responde 503
(`llm_nao_configurada`). Os testes **não** precisam da chave.

## Arquitetura

_(atualizada a cada bloco)_

Arquivos previstos (todos novos, com o nome da feature):

| Camada | Arquivos |
|---|---|
| Modelos | `app/models_writing.py` |
| Schemas (entrada/saída e contrato da LLM) | `app/schemas_writing.py` |
| Rotas (`/api/writing/...` e página `/writing`) | `app/api/writing.py` |
| Regras de negócio | `app/services/writing_temas.py`, `writing_texto.py`, `writing_desafios.py`, `writing_llm.py`, `writing_rewrite.py` |
| Migrações | `migrations/versions/0301_*.py` (esquema), `0302_*.py` (temas iniciais) |
| Tela | `app/templates/paginas/writing.html`, `app/static/js/paginas/writing.js`, `app/static/js/nucleo/api-writing.js`, `app/static/css/writing.css` |
| Testes | `tests/writing/` |

Pontos de encaixe usados (só o bloco `Membro 3 (Writing)` de cada um): `app/models.py`, `app/main.py`,
`app/static/js/main.js`, `app/templates/base.html` (CSS e botão da navbar).

Fluxo: tela (`writing.js`) → `api-writing.js` (`requisitarJSON`/`enviarJSON`) → `app/api/writing.py` (login, dono,
cota) → `services/writing_*.py` → banco (SQLModel) e LLM (`llm.gerar_json`, prompts em `writing_llm.py`).

## API

_(preenchida a partir do W3)_

## Banco de dados

_(preenchido no W1 e no W2)_

Faixa de migrações do Membro 3: `0301`, `0302`, … A primeira tem `down_revision = "0006"`.

## Decisões

| ID | Data | Decisão | Motivo |
|---|---|---|---|
| D1 | 21/11/2026 | Notas de **0 a 10 (inteiro) por categoria**; a nota geral é a **média calculada pelo servidor** | Mais legível na tela; a média não depende de a LLM fazer contas certo |
| D2 | 21/11/2026 | No fim do timer, o front envia sozinho. Após o **prazo + 30 s de tolerância**, o servidor recusa o autosave e **envia o último texto salvo**, ignorando o que chegar | Ninguém perde a redação, e ninguém ganha tempo burlando o timer da tela |
| D3 | 21/11/2026 | **Mínimo de 50 palavras** para enviar; **máximo de 10.000 caracteres**. O mínimo do tema (ex.: 250) não bloqueia, só pesa no "atendimento à tarefa" | Evita gastar LLM com textos de teste; protege banco e custo |
| D4 | 21/11/2026 | "Avaliar de novo" após falha: **até 3 vezes por tentativa**. Rewrite: **até 3 problemas**, avaliados **numa chamada só**, **até 2 rodadas por redação** | A cota diária só conta a criação; sem limites, uma redação geraria chamadas sem fim |
| D5 | 21/11/2026 | A pessoa escolhe a **categoria** ou "**Surpresa**" (categoria aleatória); o tema dentro dela é sempre sorteado | Controle para treinar uma prova sem perder o sorteio |
| D6 | 21/11/2026 | Comentários e explicações **em português**; citações e sugestões de reescrita **em inglês** | Mais didático para quem está aprendendo |
| D7 | 21/11/2026 | Avaliação **síncrona**: a submissão grava o texto, chama a LLM e devolve o resultado | Padrão do projeto (rotas `def`); fila assíncrona seria mais código e risco sem ganho real |
| D8 | 21/11/2026 | **Um commit por bloco** (W0 = este plano, depois W1 … W10), feito pelo usuário, só com a suíte inteira e o `ruff` verdes, verificados antes de cada commit | Histórico organizado; cada commit deixa a branch funcionando |

Todas as decisões respeitam a base protegida: os limites viram constantes nos serviços `writing_*.py` (nada em
`app/config.py`), nenhuma variável de ambiente ou dependência nova, `llm.py` usado sem alteração e a cota só na rota
que cria o desafio.

## Plano e progresso

### Mapa de dependências

```
W1 Modelos + migração 0301 (esquema)
 └─► W2 Temas (categorias, migração 0302 de dados, sorteio, contagem de palavras)
      └─► W3 API do desafio (criar com cota, ler, autosave, submissão com prazo no servidor)
           ├─► W4 Tela do editor (contador, timer, autosave, aviso de IA)
           └─► W5 Contrato JSON + prompt + serviço de avaliação (puro, sem rotas)
                └─► W6 Avaliação na API (persistência, erro_avaliacao, "avaliar de novo")
                     ├─► W7 Tela de resultado + destaque dos trechos      ◄── W4
                     └─► W8 Rewrite no backend (seleção, comandos, diff, avaliação, histórico)
                          └─► W9 Tela do Rewrite                           ◄── W7
                               └─► W10 Integração ponta a ponta + entrega ao Membro 4
```

### Blocos

| ID | Bloco | Tarefas atendidas | Status |
|---|---|---|---|
| W0 | Plano (este README) | — | ✅ concluído |
| W1 | Modelos e migração do esquema (0301) | Modelagem WritingPrompt/Attempt/Feedback (+ WritingRewrite); migration das tabelas | ⏳ Etapa A |
| W2 | Temas e regras puras (0302) | Categorias TOEFL/IELTS; seleção aleatória; regra de contagem de palavras | pendente |
| W3 | API do desafio | Endpoint de criação; endpoint de submissão; autosave (servidor); timer no servidor | pendente |
| W4 | Tela do editor | Interface do editor; contador de palavras JS; timer regressivo; autosave periódico | pendente |
| W5 | Serviço de avaliação | Contrato JSON; prompt das 5 categorias; serviço de avaliação; validação Pydantic; score por categoria | pendente |
| W6 | Avaliação na API | Persistência do feedback e da versão original; timeout e resposta inválida; testes de tamanhos e tipos | pendente |
| W7 | Tela de resultado | Interface de resultado; destaque dos trechos problemáticos | pendente |
| W8 | Rewrite no backend | Seleção dos problemas; comando por problema; endpoint da reescrita; comparação; avaliação da 2ª versão; histórico | pendente |
| W9 | Tela do Rewrite | Interface do Rewrite Challenge | pendente |
| W10 | Integração e entrega | Testes unitários da avaliação (fechamento); testes de integração da sequência completa | pendente |

### Cronograma (2 dias)

| Quando | Blocos | Marco |
|---|---|---|
| Dia 1, manhã | W1, W2, W3 | Backend do desafio pronto e testado |
| Dia 1, tarde | W4, W5 | Editor usável; serviço de avaliação testado com a LLM falsa |
| Dia 2, manhã | W6, W7 | **MVP:** escrever → enviar → ver a correção com destaques |
| Dia 2, tarde | W8, W9, W10 | Rewrite completo, integração e entrega ao Membro 4 |

Essencial (MVP): W1–W7. Completa o escopo: W8–W10. Adiável sem perder tarefas: teste E2E no navegador e acabamento
visual. Se o prazo apertar, a proposta é um 3º dia curto para o W10, sem cortar tarefas nem testes.

### Estratégia de testes

- Regras puras (W2, W5, W8): testes unitários sem banco nem HTTP.
- LLM: sempre `llm_falsa` (resposta válida, JSON inválido, citação inexistente/repetida, timeout, provedor fora, 503).
- API: duas contas (`entrar_como`), outro usuário → 404; estados (409); prazo; cota (429); limites (422).
- Persistência: `engine_teste` confere que o texto original continua intacto.
- Migrações: `test_migracoes` (SQLite) e upgrade/downgrade no Postgres.
- Regressão a cada bloco: suíte inteira (referência: 266 aprovados, 2 pulados), `ruff`, `test_base_protegida`,
  `git diff --stat` (só arquivos novos + encaixes).
- Mutação a cada bloco: quebrar de propósito uma regra importante, ver um teste falhar e restaurar.

### Registro por bloco

#### W0 — Plano
- **Status:** concluído (21/11/2026).
- **Arquivos:** `README_MEMBRO3.md` (criado).
- **Linha de base (FASE 0):** branch `Membro3`, commit `49636dd`, banco local na 0006; `pytest` (SQLite): 268
  coletados, **266 aprovados, 2 pulados** (E2E sem `E2E=1`; Postgres sem `TEST_DATABASE_URL`), 0 falhas; `ruff`:
  limpo. Aviso preexistente da base: `StarletteDeprecationWarning` (httpx no TestClient), não reprova nada.
- **Próxima ação:** Etapa A do W1.

## Testes

```powershell
.\venv\Scripts\Activate.ps1
python -m pytest              # suíte inteira (SQLite temporário)
python -m pytest tests/writing   # só os testes do Writing
python -m ruff check .
```

_(a lista do que cada arquivo cobre é preenchida a cada bloco)_

## Alterações na base

Nenhuma.

## Para o Membro 4

_(preenchido ao longo dos blocos; checklist da seção 10 do `CLAUDE.md`)_

- Dependências novas: nenhuma prevista (`difflib` é da biblioteca padrão).
- Variáveis de ambiente novas: nenhuma (usa as da LLM que já existem).
- Migrações: `0301` (esquema) e `0302` (dados: temas iniciais). Na integração, juntar as cabeças das três faixas com
  `alembic merge` **antes** de rodar `python -m app.migrar` (com várias cabeças, `migrar.revisao_mais_recente()`,
  que usa `get_current_head()`, falha).
