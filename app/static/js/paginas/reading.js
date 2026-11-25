// Reading Challenge (Membro 1): página /reading (templates/paginas/reading.html).
//
// Etapas: início (aviso de IA, cota e escolhas) → leitura (texto, crédito e timer) → perguntas → resultado; e o
// histórico, a partir do início ou do resultado.
// - O timer parte do segundos_restantes calculado pelo servidor (o relógio do navegador não manda); no zero, a
//   leitura é encerrada pela mesma rota do botão. O servidor valida o prazo de novo (R6).
// - F5 no meio do desafio: a URL guarda ?desafio=ID e a página retoma do estado do servidor; as respostas que ainda
//   não foram enviadas voltam do rascunho (sessionStorage).
// - Conteúdo da API (texto, título, crédito, perguntas, comentários da LLM, mensagens) entra sempre por
//   textContent, nunca como HTML.
import { criarAvisoIA } from "../componentes/aviso-ia.js";
import { criarEstadoVazio } from "../componentes/estado-vazio.js";
import { api } from "../nucleo/api.js";
import { apiReading } from "../nucleo/api-reading.js";
import { contagemRegressiva, formatarTempo, mostrarErro } from "../nucleo/interface.js";
import { registrarPagina } from "../nucleo/paginas.js";

const LIMITE_RESPOSTA = 1000; // o mesmo do servidor (schemas_reading.LIMITE_RESPOSTA_DO_USUARIO)
const MODALIDADES = { multipla_escolha: "Múltipla escolha", aberta: "Resposta aberta" };
const ESTADOS = {
    lendo: "Em leitura", respondendo: "Respondendo", avaliando: "Corrigindo", erro_avaliacao: "Erro na correção",
};
const MARCAS = { 1: "✓", 0.5: "½", 0: "✗" };

// 5400 → "1 h 30 min"; 90 → "2 min"
function formatarEspera(segundos) {
    const horas = Math.floor(segundos / 3600);
    if (horas) return `${horas} h ${Math.floor((segundos % 3600) / 60)} min`;
    return `${Math.max(1, Math.ceil(segundos / 60))} min`;
}

// "2026-11-23T10:05:00" (horário de Brasília, como o servidor grava) → "23/11/2026 10:05"
function formatarData(iso) {
    const [data, hora] = iso.split("T");
    const [ano, mes, dia] = data.split("-");
    return `${dia}/${mes}/${ano} ${hora.slice(0, 5)}`;
}

function formatarNota(nota) {
    return nota.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
}

function desafioDaUrl() {
    const id = Number(new URLSearchParams(location.search).get("desafio"));
    return Number.isInteger(id) && id > 0 ? id : null;
}

function guardarNaUrl(id) {
    const url = new URL(location.href);
    if (id) url.searchParams.set("desafio", id);
    else url.searchParams.delete("desafio");
    history.replaceState(history.state, "", url);
}

// Rascunho das respostas (DR40): só uma conveniência para o F5. O armazenamento pode estar bloqueado ou cheio.
const chaveDoRascunho = (id) => `reading-rascunho-${id}`;

function lerRascunho(id) {
    try {
        const respostas = JSON.parse(sessionStorage.getItem(chaveDoRascunho(id)) || "[]");
        return Array.isArray(respostas) ? respostas : [];
    } catch {
        return [];
    }
}

function salvarRascunho(id, respostas) {
    try { sessionStorage.setItem(chaveDoRascunho(id), JSON.stringify(respostas)); } catch { /* sem rascunho */ }
}

function apagarRascunho(id) {
    try { sessionStorage.removeItem(chaveDoRascunho(id)); } catch { /* nada a apagar */ }
}

function criar(tag, { classe, texto } = {}) {
    const elemento = document.createElement(tag);
    if (classe) elemento.className = classe;
    if (texto !== undefined) elemento.textContent = texto;
    return elemento;
}

function botao(rotulo, aoClicar, principal = false) {
    const elemento = criar("button", { classe: principal ? "reading-botao principal" : "reading-botao", texto: rotulo });
    elemento.type = "button";
    elemento.addEventListener("click", aoClicar);
    return elemento;
}

// Parágrafos do texto e o crédito (com o link do original só se for https: nunca "javascript:").
function preencherTexto(conteudo, credito, texto) {
    conteudo.replaceChildren(...texto.conteudo.split(/\n{2,}/).map((trecho) => criar("p", { texto: trecho })));
    credito.replaceChildren(document.createTextNode(texto.credito));
    if (typeof texto.url === "string" && texto.url.startsWith("https://")) {
        const link = criar("a", { texto: " Ver o original" });
        link.href = texto.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        credito.append(link);
    }
}

registrarPagina("reading", (raiz) => {
    const $ = (id) => raiz.querySelector(`#${id}`);
    const formulario = $("readingForm");
    const botaoComecar = $("readingComecar");
    const carregando = $("readingCarregando");
    const erroInicio = $("readingErroInicio");
    const timer = $("readingTimer");
    const conteudo = $("readingConteudo");
    const formRespostas = $("readingFormRespostas");
    const botaoEnviar = $("readingEnviar");
    const enviando = $("readingEnviando");
    const enviandoTexto = $("readingEnviandoTexto");
    const erroRespostas = $("readingErroRespostas");
    const controle = new AbortController(); // remove os listeners na limpeza
    let ativo = true;                       // a página ainda está na tela? (respostas que chegam depois são ignoradas)
    let desafioAtual = null;
    let perguntasAtuais = null;             // { id, modalidade, perguntas } da etapa de perguntas
    let avisoIA = null;
    let cancelarTimer = null;
    let encerrando = false;

    function mostrarEtapa(nome) {
        raiz.querySelectorAll("[data-etapa]").forEach((secao) => { secao.hidden = secao.dataset.etapa !== nome; });
        window.scrollTo?.(0, 0);
    }

    function pararTimer() {
        cancelarTimer?.();
        cancelarTimer = null;
    }

    async function textoDoAvisoIA() {
        if (!avisoIA) avisoIA = (await api.situacaoLLM()).aviso;
        return avisoIA;
    }

    // --- Início ---

    async function prepararInicio() {
        mostrarEtapa("inicio");
        botaoComecar.disabled = false;
        try {
            const situacao = await api.situacaoLLM();
            if (!ativo) return;
            avisoIA = situacao.aviso;
            $("readingAviso").replaceChildren(criarAvisoIA(situacao.aviso)); // antes de enviar qualquer coisa
            const cota = situacao.cotas.reading;
            let texto = `Desafios restantes hoje: ${cota.restantes} de ${cota.limite}.`;
            if (cota.restantes <= 0) {
                botaoComecar.disabled = true;
                texto += cota.renova_em ? ` Novos desafios em ${formatarEspera(cota.renova_em)}.` : "";
            }
            if (!situacao.configurada) texto += " A IA não está configurada: serão usadas perguntas prontas.";
            $("readingCota").textContent = texto;
        } catch (erro) {
            if (ativo) erroInicio.textContent = erro.message;
        }
    }

    async function comecar(evento) {
        evento.preventDefault();
        if (botaoComecar.disabled) return;
        const dados = new FormData(formulario);
        const escolhas = { modalidade: dados.get("modalidade"), fonte: dados.get("fonte"), ppm: Number(dados.get("ppm")) };
        botaoComecar.disabled = true;
        carregando.hidden = false;
        erroInicio.textContent = "";
        try {
            const desafio = await apiReading.criar(escolhas);
            if (!ativo) return;
            guardarNaUrl(desafio.id);
            mostrarLeitura(desafio.id, desafio.texto, desafio.segundos_restantes);
        } catch (erro) {
            if (!ativo) return;
            await prepararInicio(); // atualiza a cota (o desafio pode ter sido gasto) e reativa o botão
            erroInicio.textContent = erro.message;
        } finally {
            carregando.hidden = true;
        }
    }

    // --- Leitura ---

    function mostrarLeitura(id, texto, segundos) {
        desafioAtual = id;
        encerrando = false;
        mostrarEtapa("leitura");
        $("readingTituloTexto").textContent = texto.titulo;
        preencherTexto(conteudo, $("readingCredito"), texto);
        pararTimer();
        cancelarTimer = contagemRegressiva(
            segundos,
            (restante) => { timer.textContent = formatarTempo(restante); },
            () => { timer.textContent = formatarTempo(0); encerrar(id); },
        );
    }

    async function encerrar(id) {
        if (encerrando) return;
        encerrando = true;
        pararTimer();
        conteudo.replaceChildren(); // o texto sai da tela na hora
        try {
            const leitura = await apiReading.encerrarLeitura(id);
            if (ativo) await mostrarPerguntas(id, leitura);
        } catch (erro) {
            if (ativo) mostrarErro(erro.message);
        } finally {
            encerrando = false;
        }
    }

    // --- Perguntas ---

    function blocoDaPergunta(pergunta, modalidade, rascunho) {
        const bloco = criar("fieldset", { classe: "reading-pergunta" });
        bloco.dataset.ordem = pergunta.ordem;
        bloco.append(criar("legend", { texto: `${pergunta.ordem}. ${pergunta.enunciado}` }));
        const nome = `pergunta-${pergunta.ordem}`;
        if (modalidade === "multipla_escolha") {
            for (const alternativa of pergunta.alternativas) {
                const rotulo = criar("label", { classe: "reading-alternativa" });
                const opcao = criar("input");
                opcao.type = "radio";
                opcao.name = nome;
                opcao.value = alternativa;
                opcao.checked = rascunho === alternativa;
                rotulo.append(opcao, criar("span", { texto: alternativa }));
                bloco.append(rotulo);
            }
        } else {
            const caixa = criar("textarea", { classe: "reading-resposta" });
            caixa.name = nome;
            caixa.rows = 3;
            caixa.maxLength = LIMITE_RESPOSTA;
            caixa.value = typeof rascunho === "string" ? rascunho : "";
            caixa.setAttribute("aria-label", `Resposta da pergunta ${pergunta.ordem}`);
            const contador = criar("span", { classe: "reading-contador", texto: `${caixa.value.length}/${LIMITE_RESPOSTA}` });
            caixa.addEventListener("input", () => { contador.textContent = `${caixa.value.length}/${LIMITE_RESPOSTA}`; });
            bloco.append(caixa, contador);
        }
        return bloco;
    }

    async function mostrarPerguntas(id, leitura) {
        desafioAtual = id;
        perguntasAtuais = { id, modalidade: leitura.modalidade, perguntas: leitura.perguntas };
        const rascunho = lerRascunho(id);
        $("readingListaPerguntas").replaceChildren(...leitura.perguntas.map(
            (pergunta, indice) => blocoDaPergunta(pergunta, leitura.modalidade, rascunho[indice])));
        erroRespostas.textContent = "";
        botaoEnviar.disabled = false;
        const aviso = $("readingAvisoRespostas");
        aviso.replaceChildren();
        mostrarEtapa("perguntas");
        if (leitura.modalidade === "aberta") { // as respostas vão para a IA corrigir: o aviso vem antes do envio
            try {
                const texto = await textoDoAvisoIA();
                if (ativo) aviso.replaceChildren(criarAvisoIA(texto));
            } catch { /* sem o texto do aviso: o envio mostra o erro, se houver */ }
        }
    }

    function respostasDoFormulario() {
        return perguntasAtuais.perguntas.map((pergunta) => {
            const nome = `pergunta-${pergunta.ordem}`;
            if (perguntasAtuais.modalidade === "multipla_escolha") {
                return formRespostas.querySelector(`input[name="${nome}"]:checked`)?.value ?? "";
            }
            return formRespostas.querySelector(`textarea[name="${nome}"]`).value.trim();
        });
    }

    async function enviar(evento) {
        evento.preventDefault();
        if (!perguntasAtuais || botaoEnviar.disabled) return;
        const { id, modalidade } = perguntasAtuais;
        const respostas = respostasDoFormulario();
        const vazias = respostas.filter((resposta) => !resposta).length;
        if (vazias) {
            const texto = vazias === 1 ? "Há 1 pergunta sem resposta." : `Há ${vazias} perguntas sem resposta.`;
            if (!confirm(`${texto} Enviar mesmo assim?`)) return; // DR39
        }
        botaoEnviar.disabled = true;
        erroRespostas.textContent = "";
        enviandoTexto.textContent = modalidade === "aberta"
            ? "Corrigindo as respostas com a IA… Pode demorar até 1 minuto quando o serviço está lento."
            : "Enviando…";
        enviando.hidden = false;
        try {
            const resultado = await apiReading.enviarRespostas(id, respostas);
            apagarRascunho(id);
            if (ativo) mostrarResultado(resultado);
        } catch (erro) {
            if (!ativo) return;
            if (erro.codigo === "ja_respondido" || erro.codigo?.startsWith("llm_")) {
                // As respostas já estão gravadas (outra aba, clique duplo, ou a IA falhou ao corrigir).
                apagarRascunho(id);
                await abrirResultado(id, erro.codigo === "ja_respondido" ? null : erro.message);
            } else {
                erroRespostas.textContent = erro.message;
                botaoEnviar.disabled = false;
            }
        } finally {
            enviando.hidden = true;
        }
    }

    // --- Resultado ---

    async function abrirResultado(id, mensagem = null) {
        try {
            const resultado = await apiReading.resultado(id);
            if (ativo) mostrarResultado(resultado, mensagem);
        } catch (erro) {
            if (ativo) mostrarErro(erro.message);
        }
    }

    function blocoDaCorrecao(pergunta, modalidade) {
        const situacao = pergunta.pontuacao === null ? "pendente"
            : pergunta.pontuacao === 1 ? "certo" : pergunta.pontuacao === 0 ? "errado" : "parcial";
        const bloco = criar("div", { classe: `reading-correcao ${situacao}` });
        bloco.dataset.ordem = pergunta.ordem;
        const marca = pergunta.pontuacao === null ? "…" : MARCAS[pergunta.pontuacao];
        bloco.append(criar("p", { classe: "reading-correcao-titulo", texto: `${marca} ${pergunta.ordem}. ${pergunta.enunciado}` }));

        const sua = criar("p", { texto: "Sua resposta: " });
        sua.append(pergunta.resposta
            ? criar("span", { classe: "reading-resposta-dada", texto: pergunta.resposta })
            : criar("em", { texto: "Sem resposta" }));
        bloco.append(sua);
        const rotuloCorreta = modalidade === "aberta" ? "Resposta esperada: " : "Resposta correta: ";
        bloco.append(criar("p", { texto: rotuloCorreta + pergunta.resposta_correta }));
        bloco.append(criar("p", { classe: "reading-justificativa", texto: `Justificativa: ${pergunta.justificativa}` }));
        if (pergunta.comentario) {
            bloco.append(criar("p", { classe: "reading-comentario", texto: `Comentário da correção: ${pergunta.comentario}` }));
        }
        return bloco;
    }

    function mostrarResultado(resultado, mensagem = null) {
        const id = resultado.id;
        desafioAtual = id;
        perguntasAtuais = null;
        guardarNaUrl(id);
        const cartao = $("readingResultado");
        const partes = [criar("h2", { texto: "Resultado" })];

        if (resultado.nota !== null) {
            partes.push(criar("p", { classe: "reading-nota", texto: `Nota ${formatarNota(resultado.nota)}/10` }));
            let acertos = `${resultado.acertos} de ${resultado.perguntas.length} perguntas certas.`;
            if (resultado.modalidade === "aberta") acertos += " ½ = parcialmente correta.";
            partes.push(criar("p", { classe: "reading-acertos", texto: acertos }));
        } else if (resultado.estado === "erro_avaliacao") {
            partes.push(criar("p", { classe: "reading-erro", texto: mensagem || "Não foi possível corrigir as respostas agora." }));
            partes.push(criar("p", { texto: "As suas respostas estão guardadas. Tente corrigir de novo em instantes." }));
            const tentar = botao("TENTAR CORRIGIR DE NOVO", () => avaliarDeNovo(id, tentar), true);
            tentar.id = "readingAvaliarDeNovo";
            partes.push(tentar);
        } else {
            partes.push(criar("p", { texto: "A correção está em andamento." }));
            partes.push(botao("ATUALIZAR", () => abrirResultado(id)));
        }

        let detalhes = `Leitura: ${formatarTempo(resultado.tempo_leitura_segundos)} · `
            + `Respostas: ${formatarTempo(resultado.tempo_resposta_segundos)} · ${MODALIDADES[resultado.modalidade]}`;
        if (resultado.usou_reserva) detalhes += " · Perguntas prontas";
        partes.push(criar("p", { classe: "reading-detalhes", texto: detalhes }));

        const lista = criar("div", { classe: "reading-lista" });
        lista.append(...resultado.perguntas.map((pergunta) => blocoDaCorrecao(pergunta, resultado.modalidade)));
        partes.push(lista);

        const texto = criar("details", { classe: "reading-texto-resultado" });
        const conteudoDoTexto = criar("div");
        const credito = criar("p", { classe: "reading-credito" });
        texto.append(criar("summary", { texto: "Ver o texto" }), criar("h3", { texto: resultado.texto.titulo }),
            conteudoDoTexto, credito);
        preencherTexto(conteudoDoTexto, credito, resultado.texto);
        partes.push(texto);

        const acoes = criar("div", { classe: "reading-acoes" });
        acoes.append(botao("NOVO DESAFIO", novoDesafio, true), botao("HISTÓRICO", mostrarHistorico));
        partes.push(acoes);

        cartao.replaceChildren(...partes);
        mostrarEtapa("resultado");
    }

    async function avaliarDeNovo(id, botaoTentar) {
        botaoTentar.disabled = true;
        botaoTentar.textContent = "CORRIGINDO… (pode demorar até 1 minuto)";
        try {
            const resultado = await apiReading.avaliar(id);
            if (ativo) mostrarResultado(resultado);
        } catch (erro) {
            if (!ativo) return;
            await abrirResultado(id, erro.codigo === "avaliacao_indisponivel" ? null : erro.message);
        }
    }

    // --- Histórico ---

    function abrirDoHistorico(item) {
        guardarNaUrl(item.id);
        if (item.estado === "lendo" || item.estado === "respondendo") retomar(item.id);
        else abrirResultado(item.id);
    }

    function linhaDoHistorico(item) {
        const linha = criar("tr", { classe: "reading-historico-linha" });
        linha.dataset.id = item.id;
        const resultado = item.nota !== null ? `${formatarNota(item.nota)}/10` : ESTADOS[item.estado] ?? item.estado;
        for (const valor of [formatarData(item.iniciado_em), item.titulo, MODALIDADES[item.modalidade], resultado]) {
            linha.append(criar("td", { texto: valor }));
        }
        const acao = criar("td");
        const continuar = item.estado === "lendo" || item.estado === "respondendo";
        acao.append(botao(continuar ? "Continuar" : "Ver", () => abrirDoHistorico(item)));
        linha.append(acao);
        return linha;
    }

    async function mostrarHistorico() {
        pararTimer();
        desafioAtual = null;
        perguntasAtuais = null;
        guardarNaUrl(null);
        const area = $("readingHistorico");
        area.replaceChildren(criar("p", { classe: "reading-carregando", texto: "Carregando…" }));
        mostrarEtapa("historico");
        try {
            const itens = await apiReading.historico();
            if (!ativo) return;
            if (!itens.length) {
                area.replaceChildren(criarEstadoVazio({
                    titulo: "Nenhum desafio ainda",
                    texto: "Os desafios que você fizer aparecem aqui, com a nota e a correção de cada pergunta.",
                    acoes: [{ rotulo: "Começar um desafio", principal: true, aoClicar: novoDesafio }],
                }));
                return;
            }
            const tabela = criar("table", { classe: "reading-historico" });
            const cabecalho = criar("tr");
            for (const titulo of ["Data", "Texto", "Tipo", "Resultado", ""]) cabecalho.append(criar("th", { texto: titulo }));
            const corpo = criar("tbody");
            corpo.append(...itens.map(linhaDoHistorico));
            tabela.append(criar("thead"), corpo);
            tabela.tHead.append(cabecalho);
            area.replaceChildren(tabela);
        } catch (erro) {
            if (ativo) area.replaceChildren(criar("p", { classe: "reading-erro", texto: erro.message }));
        }
    }

    function novoDesafio() {
        pararTimer();
        desafioAtual = null;
        perguntasAtuais = null;
        guardarNaUrl(null);
        prepararInicio();
    }

    // --- Retomar depois do F5 (?desafio=ID) ---

    async function retomar(id) {
        try {
            const resumo = await apiReading.resumo(id);
            if (!ativo) return;
            if (resumo.estado === "lendo" && resumo.segundos_restantes > 0) {
                const texto = await apiReading.texto(id);
                if (ativo) mostrarLeitura(id, texto, texto.segundos_restantes);
            } else if (resumo.estado === "lendo" || resumo.estado === "respondendo") {
                desafioAtual = id;
                await encerrar(id); // prazo vencido (DR24) ou já encerrado: o servidor devolve as perguntas
            } else {
                await abrirResultado(id); // corrigido, avaliando ou erro_avaliacao
            }
        } catch (erro) {
            if (!ativo) return;
            if (erro.codigo === "leitura_encerrada") { // o prazo venceu entre o resumo e o texto
                await encerrar(id);
                return;
            }
            guardarNaUrl(null);
            await prepararInicio();
            erroInicio.textContent = erro.status === 404 ? "Desafio não encontrado." : erro.message;
        }
    }

    const opcoes = { signal: controle.signal };
    formulario.addEventListener("submit", comecar, opcoes);
    $("readingTerminei").addEventListener("click", () => { if (desafioAtual) encerrar(desafioAtual); }, opcoes);
    $("readingVerHistorico").addEventListener("click", mostrarHistorico, opcoes);
    $("readingNovoDoHistorico").addEventListener("click", novoDesafio, opcoes);
    formRespostas.addEventListener("submit", enviar, opcoes);
    // Rascunho: a cada mudança nas respostas (F5 não perde o que já foi escrito ou marcado).
    formRespostas.addEventListener("input", () => {
        if (perguntasAtuais) salvarRascunho(perguntasAtuais.id, respostasDoFormulario());
    }, opcoes);

    const id = desafioDaUrl();
    if (id) retomar(id);
    else prepararInicio();

    return () => {
        ativo = false;
        pararTimer();
        controle.abort();
    };
});
