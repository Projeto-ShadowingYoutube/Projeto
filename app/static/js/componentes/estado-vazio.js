// Estado vazio (B12): quando uma área não tem nada para mostrar, explica por quê e oferece a próxima ação.
//
// criarEstadoVazio({ titulo, texto, acoes: [{ rotulo, aoClicar, principal }] }) → elemento pronto para inserir.
// O visual (.estado-vazio) está em static/css/decks.css.

export function criarEstadoVazio({ titulo, texto, acoes = [] }) {
    const bloco = document.createElement("div");
    bloco.className = "estado-vazio";

    const cabecalho = document.createElement("p");
    cabecalho.className = "estado-vazio-titulo";
    cabecalho.textContent = titulo;
    bloco.append(cabecalho);

    if (texto) {
        const explicacao = document.createElement("p");
        explicacao.className = "estado-vazio-texto";
        explicacao.textContent = texto;
        bloco.append(explicacao);
    }

    if (acoes.length) {
        const botoes = document.createElement("div");
        botoes.className = "estado-vazio-acoes";
        for (const { rotulo, aoClicar, principal } of acoes) {
            const botao = document.createElement("button");
            botao.type = "button";
            botao.className = principal ? "estado-vazio-botao principal" : "estado-vazio-botao";
            botao.textContent = rotulo;
            botao.addEventListener("click", aoClicar);
            botoes.append(botao);
        }
        bloco.append(botoes);
    }
    return bloco;
}
