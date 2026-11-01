// Elementos globais do base.html: modal de erro, tela de carregamento e contador de tokens.

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

export function atualizarTokens(valor) {
    const contador = elemento("token-count");
    contador.textContent = valor;
    contador.classList.toggle("token-low", Number(valor) === 0);
}

export function iniciarModalErro() {
    const fechar = () => { elemento("erroModal").style.display = "none"; };
    elemento("fecharErro").addEventListener("click", fechar);
    elemento("botaoErro").addEventListener("click", fechar);
}
