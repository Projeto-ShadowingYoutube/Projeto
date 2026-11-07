// Salva as configurações de estudo do usuário no servidor (PATCH /api/configuracoes).
//
// A velocidade é salva com atraso: arrastar o slider dispara dezenas de eventos, e só o valor final interessa.
// Se a pessoa sair da página antes do atraso terminar, a página chama salvarPendentes().
import { api } from "./api.js";

const ATRASO_MS = 500;
let pendente = null; // { valor, temporizador }

export function salvarVelocidade(valor) {
    clearTimeout(pendente?.temporizador);
    pendente = { valor, temporizador: setTimeout(enviar, ATRASO_MS) };
}

export function salvarPendentes() {
    if (!pendente) return;
    clearTimeout(pendente.temporizador);
    enviar();
}

function enviar() {
    const { valor } = pendente;
    pendente = null;
    // Falhar ao salvar uma preferência não deve interromper o estudo: só registra no console.
    api.configuracoes.alterar({ velocidade: valor })
        .catch((erro) => console.error("Não foi possível salvar a velocidade:", erro));
}
