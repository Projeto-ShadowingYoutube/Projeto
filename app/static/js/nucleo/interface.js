// Elementos globais do base.html: modal de erro, tela de carregamento e contador de tokens.
import { api } from "./api.js";

const elemento = (id) => document.getElementById(id);

export function mostrarErro(mensagem) {
    elemento("erro").textContent = mensagem;
    elemento("erroModal").style.display = "block";
}

export function mostrarCarregamento(mensagem) {
    const carregamento = elemento("carregamento");
    if (!carregamento) return;
    elemento("carregamentoTexto").textContent = mensagem;
    carregamento.style.display = "flex";
}

export function esconderCarregamento() {
    const carregamento = elemento("carregamento");
    if (carregamento) carregamento.style.display = "none";
}

// 252 → "4:12"
export function formatarTempo(segundos) {
    const minutos = Math.floor(segundos / 60);
    return `${minutos}:${String(segundos % 60).padStart(2, "0")}`;
}

// Contagem regressiva de "segundos": chama aCadaSegundo(restante) e, ao chegar a zero, aoTerminar().
// Devolve a função que cancela a contagem.
export function contagemRegressiva(segundos, aCadaSegundo, aoTerminar) {
    const fim = Date.now() + segundos * 1000;
    let intervalo = null;
    const passo = () => {
        const restante = Math.ceil((fim - Date.now()) / 1000);
        if (restante <= 0) {
            clearInterval(intervalo);
            aoTerminar?.();
            return;
        }
        aCadaSegundo(restante);
    };
    passo();
    intervalo = setInterval(passo, 1000);
    return () => clearInterval(intervalo);
}

let cancelarDicaDosTokens = null;

// Contador da navbar. renovaEm (segundos, ou null): quando os tokens da janela voltam. A dica do botão mostra o
// tempo e, ao chegar a zero, o contador se atualiza sozinho pelo servidor (ex.: de 0 de volta para 5).
export function atualizarTokens(valor, renovaEm = null) {
    const contador = elemento("token-count");
    if (!contador) return; // navbar sem usuário (telas de login/cadastro)
    contador.textContent = valor;
    contador.classList.toggle("token-low", Number(valor) === 0);

    const botao = contador.closest("button");
    cancelarDicaDosTokens?.();
    cancelarDicaDosTokens = null;
    botao.title = "Tokens: cada vídeo novo gasta 1";
    if (!renovaEm) return;
    cancelarDicaDosTokens = contagemRegressiva(
        renovaEm,
        (restante) => { botao.title = `Tokens renovam em ${formatarTempo(restante)}`; },
        () => {
            api.tokens().then((dados) => atualizarTokens(dados.tokens_restantes, dados.renova_em)).catch(() => {});
        },
    );
}

export function iniciarModalErro() {
    const fechar = () => { elemento("erroModal").style.display = "none"; };
    elemento("fecharErro").addEventListener("click", fechar);
    elemento("botaoErro").addEventListener("click", fechar);
}
