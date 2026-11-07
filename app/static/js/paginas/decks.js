// Página de Decks (templates/paginas/decks.html): dashboard com Novos / Revisar / Total de cada Deck.
import { executar, pedirNome } from "../componentes/escolha-deck.js";
import { criarEstadoVazio } from "../componentes/estado-vazio.js";
import { api } from "../nucleo/api.js";
import { navegarPara, registrarPagina } from "../nucleo/paginas.js";

const elemento = (id) => document.getElementById(id);

registrarPagina("decks", () => {
    const corpo = elemento("corpoTabelaDecksRevisao");
    const botoesDeSelecao = ["btnRenomearDeckRevisao", "btnDeletarDeckRevisao", "btnRevisarDeck"].map(elemento);
    let selecionado = null;

    function selecionar(id) {
        selecionado = id;
        botoesDeSelecao.forEach((botao) => { botao.disabled = id === null; });
        corpo.querySelectorAll(".dashboard-tr-deck").forEach((linha) => {
            linha.classList.toggle("selected", Number(linha.dataset.id) === id);
        });
    }

    // Linha que ocupa a tabela inteira com um estado vazio (B12): o motivo e o que fazer.
    function linhaDeAviso(estado) {
        const linha = document.createElement("tr");
        const celula = document.createElement("td");
        celula.colSpan = 4;
        celula.className = "dashboard-aviso";
        celula.append(criarEstadoVazio(estado));
        linha.append(celula);
        return linha;
    }

    function linhaDoDeck(deck) {
        const linha = document.createElement("tr");
        linha.className = "dashboard-tr-deck";
        linha.dataset.id = deck.id;
        [
            ["td-deck-name", deck.nome],
            ["td-novos text-blue", deck.novos],
            ["td-revisar text-green", deck.revisar],
            ["td-qtd-total text-yellow", deck.quantidade_total],
        ].forEach(([classe, valor]) => {
            const celula = document.createElement("td");
            celula.className = classe;
            celula.textContent = valor;
            linha.append(celula);
        });
        linha.addEventListener("click", () => selecionar(deck.id));
        linha.addEventListener("dblclick", () => revisar(deck.id));
        return linha;
    }

    async function recarregar() {
        selecionar(null);
        let decks;
        try {
            decks = await api.decks.listar();
        } catch (erro) {
            corpo.replaceChildren(linhaDeAviso({
                titulo: "Não foi possível carregar os seus Decks.",
                texto: erro.message,
                acoes: [{ rotulo: "Tentar de novo", principal: true, aoClicar: recarregar }],
            }));
            return;
        }
        corpo.replaceChildren(...(decks.length ? decks.map(linhaDoDeck) : [linhaDeAviso({
            titulo: "Você ainda não tem Decks",
            texto: "Os Cards nascem no estudo: carregue um vídeo e salve as frases com o marcador 🔖. "
                + "Eles ficam guardados num Deck para você revisar depois.",
            acoes: [
                { rotulo: "Estudar um vídeo", principal: true, aoClicar: () => navegarPara("/") },
                { rotulo: "Criar Deck", aoClicar: () => elemento("btnCriarDeckRevisao").click() },
            ],
        })]));
    }

    function revisar(deckId) {
        navegarPara(`/decks/${deckId}/revisao`);
    }

    elemento("btnCriarDeckRevisao").onclick = async () => {
        const nome = await pedirNome("Criar novo Deck");
        if (nome !== null && await executar(() => api.decks.criar(nome))) await recarregar();
    };
    elemento("btnRenomearDeckRevisao").onclick = async () => {
        const nome = await pedirNome("Renomear Deck");
        if (nome !== null && await executar(() => api.decks.renomear(selecionado, nome))) await recarregar();
    };
    elemento("btnDeletarDeckRevisao").onclick = async () => {
        if (!confirm("Tem certeza que deseja deletar este deck permanentemente?")) return;
        if (await executar(() => api.decks.deletar(selecionado))) await recarregar();
    };
    elemento("btnRevisarDeck").onclick = () => revisar(selecionado);

    recarregar();
});
