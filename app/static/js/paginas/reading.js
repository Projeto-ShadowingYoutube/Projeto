// Reading Challenge (Membro 1): página /reading (templates/paginas/reading.html).
//
// Etapas: início (aviso de IA, cota e escolhas) → leitura (texto, crédito e timer) → perguntas e resultado (R10).
// - O timer parte do segundos_restantes calculado pelo servidor (o relógio do navegador não manda); no zero, a
//   leitura é encerrada pela mesma rota do botão. O servidor valida o prazo de novo (R6).
// - F5 no meio do desafio: a URL guarda ?desafio=ID e a página retoma do estado do servidor.
// - Conteúdo da API (texto, título, crédito, mensagens) entra sempre por textContent, nunca como HTML.
import { criarAvisoIA } from "../componentes/aviso-ia.js";
import { criarEstadoVazio } from "../componentes/estado-vazio.js";
import { api } from "../nucleo/api.js";
import { apiReading } from "../nucleo/api-reading.js";
import { contagemRegressiva, formatarTempo, mostrarErro } from "../nucleo/interface.js";
import { registrarPagina } from "../nucleo/paginas.js";

// 5400 → "1 h 30 min"; 90 → "2 min"
function formatarEspera(segundos) {
    const horas = Math.floor(segundos / 3600);
    if (horas) return `${horas} h ${Math.floor((segundos % 3600) / 60)} min`;
    return `${Math.max(1, Math.ceil(segundos / 60))} min`;
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

registrarPagina("reading", (raiz) => {
    const $ = (id) => raiz.querySelector(`#${id}`);
    const formulario = $("readingForm");
    const botaoComecar = $("readingComecar");
    const carregando = $("readingCarregando");
    const erroInicio = $("readingErroInicio");
    const timer = $("readingTimer");
    const conteudo = $("readingConteudo");
    const controle = new AbortController(); // remove os listeners na limpeza
    let ativo = true;                       // a página ainda está na tela? (respostas que chegam depois são ignoradas)
    let desafioAtual = null;
    let cancelarTimer = null;
    let encerrando = false;

    function mostrarEtapa(nome) {
        raiz.querySelectorAll("[data-etapa]").forEach((secao) => { secao.hidden = secao.dataset.etapa !== nome; });
    }

    function pararTimer() {
        cancelarTimer?.();
        cancelarTimer = null;
    }

    // --- Início ---

    async function prepararInicio() {
        mostrarEtapa("inicio");
        botaoComecar.disabled = false;
        try {
            const situacao = await api.situacaoLLM();
            if (!ativo) return;
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

    function montarCredito(texto) {
        const credito = $("readingCredito");
        credito.replaceChildren(document.createTextNode(texto.credito));
        // Só links https: uma fonte nunca consegue injetar "javascript:" no href.
        if (typeof texto.url === "string" && texto.url.startsWith("https://")) {
            const link = document.createElement("a");
            link.href = texto.url;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            link.textContent = " Ver o original";
            credito.append(link);
        }
    }

    function mostrarLeitura(id, texto, segundos) {
        desafioAtual = id;
        encerrando = false;
        mostrarEtapa("leitura");
        $("readingTituloTexto").textContent = texto.titulo;
        conteudo.replaceChildren(...texto.conteudo.split(/\n{2,}/).map((trecho) => {
            const paragrafo = document.createElement("p");
            paragrafo.textContent = trecho;
            return paragrafo;
        }));
        montarCredito(texto);
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
            if (ativo) mostrarPerguntas(id, leitura);
        } catch (erro) {
            encerrando = false;
            if (ativo) mostrarErro(erro.message);
        }
    }

    // --- Perguntas e resultado: tela do bloco R10 ---

    function mostrarPerguntas(id, dados) {
        mostrarEtapa("perguntas");
        $("readingPerguntas").replaceChildren(criarEstadoVazio({
            titulo: "Leitura encerrada",
            texto: dados.perguntas
                ? `As ${dados.perguntas.length} perguntas aparecem aqui no próximo bloco (R10).`
                : "O resultado aparece aqui no próximo bloco (R10).",
            acoes: [{ rotulo: "Novo desafio", principal: true, aoClicar: novoDesafio }],
        }));
    }

    function novoDesafio() {
        pararTimer();
        desafioAtual = null;
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
                mostrarPerguntas(id, {}); // corrigido, avaliando ou erro_avaliacao: resultado (R10)
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

    formulario.addEventListener("submit", comecar, { signal: controle.signal });
    $("readingTerminei").addEventListener("click", () => { if (desafioAtual) encerrar(desafioAtual); },
        { signal: controle.signal });

    const id = desafioDaUrl();
    if (id) retomar(id);
    else prepararInicio();

    return () => {
        ativo = false;
        pararTimer();
        controle.abort();
    };
});
