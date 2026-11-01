// Exibe a legenda palavra por palavra, com o botão de ocultar (desfoque) e o popup de dicionário ao clicar numa palavra.
//
// Modo karaokê: a palavra que está sendo dita no vídeo fica destacada, e as já ditas ficam coloridas.
// O tempo de cada palavra vem do servidor (app/services/frases.py e karaoke.py); sem ele (Cards da revisão), é estimado aqui
// do mesmo jeito: a duração é dividida pelas palavras conforme o tamanho delas.
import { api } from "../nucleo/api.js";

export const Legenda = (() => {
    let oculta = false;
    let fraseAtual = "";
    let tempos = [];          // [início, fim] de cada palavra, em segundos desde o início da frase
    let palavraAtual = -1;
    let karaoke = lerPreferenciaKaraoke();

    function lerPreferenciaKaraoke() {
        try {
            return localStorage.getItem("karaoke") !== "desligado";
        } catch {
            return true;
        }
    }

    const CLASSES = {
        Noun: "substantivo", Verb: "verbo", Adjective: "adjetivo", Adverb: "advérbio",
        Preposition: "preposição", Conjunction: "conjunção", Pronoun: "pronome", Determiner: "determinante",
        Article: "artigo", Interjection: "interjeição", Numeral: "numeral", Particle: "partícula",
        "Proper noun": "nome próprio", Contraction: "contração", Prefix: "prefixo", Suffix: "sufixo",
    };

    function criarElemento(tag, classe, texto) {
        const elemento = document.createElement(tag);
        if (classe) elemento.className = classe;
        if (texto !== undefined) elemento.textContent = texto;
        return elemento;
    }

    // "temposPalavras" vem do servidor; sem ele, os tempos são estimados a partir da "duracao" da frase.
    function mostrar(frase, { temposPalavras = null, duracao = 0 } = {}) {
        fraseAtual = frase;
        const legenda = document.getElementById("legenda");
        legenda.replaceChildren();
        // Mesma separação por espaços usada no servidor (dicionario.py e frases.py).
        const palavras = frase.split(/\s+/).filter(Boolean);
        palavras.forEach((palavra, indice) => {
            if (indice > 0) legenda.append(" ");
            const span = criarElemento("span", "palavra-legenda", palavra);
            span.dataset.indice = indice;
            legenda.append(span);
        });
        tempos = temposPalavras?.length === palavras.length ? temposPalavras : estimarTempos(palavras, duracao);
        palavraAtual = -1;
    }

    // Mesma regra de app/services/frases.py: letras + 2, e +3 se a palavra termina em pontuação (pausa).
    function estimarTempos(palavras, duracao) {
        const pesos = palavras.map((p) => p.replace(/[^\p{L}\p{N}]/gu, "").length + 2 + (/[,.;:?!…—]$/.test(p) ? 3 : 0));
        const total = pesos.reduce((a, b) => a + b, 0);
        let cursor = 0;
        return pesos.map((peso) => {
            const inicio = cursor;
            cursor += (duracao * peso) / total;
            return [inicio, cursor];
        });
    }

    // A legenda começa com o tempo estimado de cada palavra e troca pelo tempo medido (legenda automática
    // do YouTube ou alinhamento do áudio, ver app/services/karaoke.py) quando o servidor responde.
    function carregarTempos(videoId, inicio, fim) {
        const frase = fraseAtual;
        api.videos.temposPalavras(videoId, inicio, fim, frase)
            .then((resposta) => {
                if (!resposta.tempos || frase !== fraseAtual || resposta.tempos.length !== tempos.length) return;
                tempos = resposta.tempos;
                palavraAtual = -1;
            })
            .catch(() => {}); // sem resposta, fica a estimativa
    }

    // Chamado a cada frame com os segundos desde o início da frase.
    function destacar(decorrido) {
        if (!karaoke || !tempos.length) return;
        let indice = tempos.findIndex(([, fim]) => decorrido < fim);
        if (indice === -1) indice = tempos.length; // passou da última palavra
        if (decorrido < tempos[0][0]) indice = -1;
        if (indice === palavraAtual) return;
        palavraAtual = indice;
        document.querySelectorAll("#legenda .palavra-legenda").forEach((span, i) => {
            span.classList.toggle("dita", i < indice);
            span.classList.toggle("atual", i === indice);
        });
    }

    // Marca as palavras que o usuário não disse na última gravação (null limpa as marcas).
    function marcarDitas(ditas) {
        document.querySelectorAll("#legenda .palavra-legenda").forEach((span, i) => {
            span.classList.toggle("faltou", ditas?.[i] === false);
        });
    }

    function alternarKaraoke() {
        karaoke = !karaoke;
        try {
            localStorage.setItem("karaoke", karaoke ? "ligado" : "desligado");
        } catch {}
        atualizarBotaoKaraoke();
        palavraAtual = -1;
        if (!karaoke) {
            document.querySelectorAll("#legenda .palavra-legenda").forEach((span) => span.classList.remove("dita", "atual"));
        }
    }

    function atualizarBotaoKaraoke() {
        const botao = document.getElementById("karaoke");
        if (!botao) return;
        botao.classList.toggle("ativo", karaoke);
        botao.title = karaoke ? "Desligar modo karaokê" : "Ligar modo karaokê";
    }

    // Mostra um aviso no lugar da legenda (sem popup de dicionário).
    function mostrarAviso(texto) {
        fraseAtual = "";
        document.getElementById("legenda").textContent = texto;
    }

    function alternarOcultar() {
        oculta = !oculta;
        document.getElementById("legenda").classList.toggle("oculta", oculta);
        document.getElementById("olho").src = oculta ? "/static/img/olhoOFF.svg" : "/static/img/olho.svg";
        if (oculta) fecharPopup();
    }

    // Toca o áudio gravado do dicionário; se não houver (ou o servidor de áudio falhar), usa a voz do navegador.
    function pronunciar(texto, urlAudio) {
        const falar = () => {
            const fala = new SpeechSynthesisUtterance(texto);
            fala.lang = "en-US";
            speechSynthesis.cancel();
            speechSynthesis.speak(fala);
        };
        if (!urlAudio) return falar();
        new Audio(urlAudio).play().catch(falar);
    }

    async function abrirPopup(span) {
        fecharPopup();
        const popup = criarElemento("div");
        popup.id = "popupPalavra";
        popup.append(criarElemento("span", "popup-loading", "Buscando..."));
        document.body.append(popup);
        posicionarPopup(popup, span);

        try {
            const dados = await api.dicionario(span.textContent, fraseAtual, span.dataset.indice);
            popup.replaceChildren(...conteudoDoPopup(dados));
        } catch (erro) {
            popup.replaceChildren(criarElemento("div", "popup-erro", erro.message));
        }
        posicionarPopup(popup, span);
    }

    function conteudoDoPopup(dados) {
        const cabecalho = criarElemento("div", "popup-header");
        cabecalho.append(criarElemento("span", "popup-palavra", dados.palavra));
        if (dados.fonetica) cabecalho.append(criarElemento("span", "popup-fonetica", dados.fonetica));

        const partes = [cabecalho];
        if (dados.lema.toLowerCase() !== dados.palavra.toLowerCase()) {
            partes.push(criarElemento("div", "popup-lema", `forma base: ${dados.lema}`));
        }

        dados.classes.forEach((classe) => {
            const titulo = criarElemento("div", "popup-classe", CLASSES[classe.classe] || classe.classe.toLowerCase());
            if (classe.do_contexto) titulo.append(criarElemento("span", "popup-contexto", "nesta frase"));
            const lista = criarElemento("ol", "popup-definicoes");
            classe.definicoes.forEach(({ definicao, exemplo }) => {
                const item = criarElemento("li", "popup-definicao", definicao);
                if (exemplo) item.append(criarElemento("div", "popup-exemplo", `"${exemplo}"`));
                lista.append(item);
            });
            partes.push(titulo, lista);
        });

        // O áudio do dicionário é da forma base; para outra forma (ex: "vectors"), a voz do navegador lê a palavra exata.
        const urlAudio = dados.lema.toLowerCase() === dados.palavra.toLowerCase() ? dados.audio : null;
        const botao = criarElemento("button", "popup-audio-btn", "🔊 Ouvir");
        botao.addEventListener("click", () => pronunciar(dados.palavra, urlAudio));
        partes.push(botao, criarElemento("div", "popup-fonte", `Fonte: ${dados.fonte}`));
        return partes;
    }

    function posicionarPopup(popup, span) {
        const retangulo = span.getBoundingClientRect();
        let topo = retangulo.top + window.scrollY - popup.offsetHeight - 10;
        let esquerda = retangulo.left + window.scrollX + retangulo.width / 2 - popup.offsetWidth / 2;

        if (topo < window.scrollY + 10) topo = retangulo.bottom + window.scrollY + 10;
        esquerda = Math.max(10, Math.min(esquerda, window.innerWidth + window.scrollX - popup.offsetWidth - 10));

        popup.style.top = `${topo}px`;
        popup.style.left = `${esquerda}px`;
    }

    function fecharPopup() {
        document.getElementById("popupPalavra")?.remove();
    }

    // Um único escutador para a página toda, já que o HTMX troca os elementos a cada navegação.
    document.addEventListener("click", (evento) => {
        if (evento.target.closest("#ocultar")) return alternarOcultar();
        if (evento.target.closest("#karaoke")) return alternarKaraoke();

        const palavra = evento.target.closest(".palavra-legenda");
        if (palavra && !oculta) return abrirPopup(palavra);

        if (!evento.target.closest("#popupPalavra")) fecharPopup();
    });

    return {
        mostrar,
        mostrarAviso,
        destacar,
        carregarTempos,
        marcarDitas,
        fecharPopup,
        reiniciar: () => {
            oculta = false;
            tempos = [];
            atualizarBotaoKaraoke();
        },
    };
})();
