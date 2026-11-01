// Ciclo de vida das páginas carregadas pelo HTMX.
//
// Cada template com JavaScript tem uma raiz <div class="pagina" data-pagina="nome">.
// Quando o HTMX coloca essa página na tela, a função registrada para o nome é chamada com a raiz.
// Ela pode devolver uma função de limpeza, que é chamada antes de a página sair da tela.

const paginasRegistradas = {};
let limparPaginaAtual = null;

export function registrarPagina(nome, iniciar) {
    paginasRegistradas[nome] = iniciar;
}

export function iniciarCicloDeVida() {
    htmx.onLoad((elemento) => {
        if (!elemento.matches?.("[data-pagina]")) return;
        const iniciar = paginasRegistradas[elemento.dataset.pagina];
        if (iniciar) limparPaginaAtual = iniciar(elemento) || null;
    });

    document.body.addEventListener("htmx:beforeSwap", (evento) => {
        if (evento.detail.target?.tagName !== "MAIN" || !limparPaginaAtual) return;
        limparPaginaAtual();
        limparPaginaAtual = null;
    });
}

export function navegarPara(url) {
    htmx.ajax("GET", url, { target: "main", swap: "innerHTML" });
    // O estado { htmx: true } faz o HTMX tratar o botão "voltar" do navegador nessa entrada do histórico.
    history.pushState({ htmx: true }, "", url);
}
