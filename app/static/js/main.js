// Ponto de entrada do front-end (carregado pelo base.html como módulo).
import { api } from "./nucleo/api.js";
import { atualizarTokens, iniciarModalErro } from "./nucleo/interface.js";
import { iniciarCicloDeVida } from "./nucleo/paginas.js";
import { iniciarTema } from "./nucleo/tema.js";

// Cada página se registra ao ser importada.
import "./paginas/decks.js";
import "./paginas/estudo.js";
import "./paginas/revisao.js";

iniciarTema();
iniciarModalErro();
iniciarCicloDeVida();

api.tokens()
    .then((dados) => atualizarTokens(dados.tokens_restantes))
    .catch(() => {});
