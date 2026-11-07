// Salva as configurações de estudo do usuário no servidor (PATCH /api/configuracoes).
//
// Os controles (velocidade, volume) são salvos com atraso: arrastar um slider dispara dezenas de eventos, e só o
// valor final interessa. Mudanças feitas dentro do atraso vão juntas num PATCH só (ex.: {velocidade, volume}).
// Se a pessoa sair da página antes do atraso terminar, a página chama salvarPendentes().
import { api } from "./api.js";

const ATRASO_MS = 500;
let pendente = null; // { mudancas: {campo: valor}, temporizador }

function salvarComAtraso(campo, valor) {
    clearTimeout(pendente?.temporizador);
    pendente = { mudancas: { ...pendente?.mudancas, [campo]: valor }, temporizador: setTimeout(enviar, ATRASO_MS) };
}

export const salvarVelocidade = (valor) => salvarComAtraso("velocidade", valor);
export const salvarVolume = (valor) => salvarComAtraso("volume", valor);

export function salvarPendentes() {
    if (!pendente) return;
    clearTimeout(pendente.temporizador);
    enviar();
}

function enviar() {
    const { mudancas } = pendente;
    pendente = null;
    // Falhar ao salvar uma preferência não deve interromper o estudo: só registra no console.
    api.configuracoes.alterar(mudancas)
        .catch((erro) => console.error("Não foi possível salvar as configurações:", erro));
}
