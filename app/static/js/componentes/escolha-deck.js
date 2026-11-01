// Modais de Deck: o submodal que pede um nome (criar/renomear) e o modal "Escolher Deck" da página de estudo.
import { api } from "../nucleo/api.js";
import { mostrarErro } from "../nucleo/interface.js";

const elemento = (id) => document.getElementById(id);

// Submodal usado para criar e renomear Decks. Devolve o nome digitado, ou null se o usuário cancelar.
export function pedirNome(titulo) {
    const modal = elemento("subModalCriarDeck");
    const campo = elemento("novoNomeDeckInput");
    modal.querySelector(".submodal-titulo").textContent = titulo;
    campo.value = "";
    modal.style.display = "flex";
    campo.focus();

    return new Promise((resolve) => {
        const fechar = (valor) => {
            modal.style.display = "none";
            elemento("btnConfirmarCriarDeck").onclick = null;
            elemento("btnCancelarSubModal").onclick = null;
            elemento("btnCancelarSubModalX").onclick = null;
            campo.onkeydown = null;
            resolve(valor);
        };
        const confirmar = () => fechar(campo.value.trim() || "Deck");
        elemento("btnConfirmarCriarDeck").onclick = confirmar;
        elemento("btnCancelarSubModal").onclick = () => fechar(null);
        elemento("btnCancelarSubModalX").onclick = () => fechar(null);
        campo.onkeydown = (evento) => {
            if (evento.key === "Enter") confirmar();
            if (evento.key === "Escape") fechar(null);
        };
    });
}

// Executa uma ação da API. Devolve true se deu certo; se não, mostra o erro e devolve false.
export async function executar(acao) {
    try {
        await acao();
        return true;
    } catch (erro) {
        mostrarErro(erro.message);
        return false;
    }
}

// Modal "Escolher Deck" da página de estudo. Devolve o ID do Deck escolhido, ou null se cancelar.
export function escolherDeck() {
    const modal = elemento("modalDeck");
    const lista = elemento("listaDecks");
    const filtro = elemento("filtroInput");
    const btnSalvar = elemento("btnSalvar");
    const btnDeletar = elemento("btnDeletarDeckModal");
    let selecionado = null;

    function selecionar(id) {
        selecionado = id;
        btnSalvar.disabled = btnDeletar.disabled = id === null;
        lista.querySelectorAll(".modal-deck-item").forEach((item) => {
            item.classList.toggle("selected", Number(item.dataset.id) === id);
        });
    }

    function itemDeTexto(texto) {
        const item = document.createElement("li");
        item.className = "modal-deck-item apenas-texto";
        item.textContent = texto;
        return item;
    }

    function filtrar() {
        const termo = filtro.value.toLowerCase().trim();
        lista.querySelectorAll(".modal-deck-item:not(.apenas-texto)").forEach((item) => {
            item.style.display = item.textContent.toLowerCase().includes(termo) ? "" : "none";
        });
    }

    async function recarregar() {
        selecionar(null);
        let decks;
        try {
            decks = await api.decks.listar();
        } catch {
            lista.replaceChildren(itemDeTexto("Erro ao carregar baralhos."));
            return;
        }
        if (!decks.length) {
            lista.replaceChildren(itemDeTexto("Nenhum Deck encontrado."));
            return;
        }
        lista.replaceChildren(...decks.map((deck) => {
            const item = document.createElement("li");
            item.className = "modal-deck-item";
            item.dataset.id = deck.id;
            item.textContent = deck.nome;
            item.addEventListener("click", () => selecionar(deck.id));
            return item;
        }));
        filtrar();
    }

    filtro.value = "";
    filtro.oninput = filtrar;
    elemento("btnCriarDeckModal").onclick = async () => {
        const nome = await pedirNome("Criar novo Deck");
        if (nome !== null && await executar(() => api.decks.criar(nome))) await recarregar();
    };
    btnDeletar.onclick = async () => {
        if (!confirm("Tem certeza absoluta de que deseja deletar o baralho selecionado?")) return;
        if (await executar(() => api.decks.deletar(selecionado))) await recarregar();
    };

    const escolha = new Promise((resolve) => {
        const fechar = (valor) => {
            modal.style.display = "none";
            resolve(valor);
        };
        btnSalvar.onclick = () => fechar(selecionado);
        elemento("btnCancelar").onclick = () => fechar(null);
        elemento("btnCancelarRodape").onclick = () => fechar(null);
    });

    modal.style.display = "flex";
    recarregar();
    return escolha;
}
