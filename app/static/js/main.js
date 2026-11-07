// Ponto de entrada do front-end (carregado pelo base.html como módulo).
import { api } from "./nucleo/api.js";
import { atualizarTokens, iniciarModalErro } from "./nucleo/interface.js";
import { iniciarCicloDeVida } from "./nucleo/paginas.js";
import { iniciarTema } from "./nucleo/tema.js";

// Cada página se registra ao ser importada.
import "./paginas/auth.js";
import "./paginas/decks.js";
import "./paginas/estudo.js";
import "./paginas/revisao.js";

iniciarTema();
iniciarModalErro();
iniciarCicloDeVida();

// Contador de tokens e botão "Sair" só existem na navbar de quem está logado.
if (document.getElementById("token-count")) {
    api.tokens()
        .then((dados) => atualizarTokens(dados.tokens_restantes, dados.renova_em))
        .catch(() => {});
}

document.getElementById("sair")?.addEventListener("click", async () => {
    try {
        await api.auth.logout();
    } finally {
        // Carga completa: a navbar volta ao estado "sem usuário" e nenhuma página antiga fica na tela.
        location.assign("/login");
    }
});
