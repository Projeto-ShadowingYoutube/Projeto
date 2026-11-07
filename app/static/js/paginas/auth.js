// Telas de login e cadastro (templates/paginas/login.html e cadastro.html).
// Depois de entrar, carrega a página inteira de novo (a navbar passa a mostrar o usuário) no endereço "proximo".
import { api } from "../nucleo/api.js";
import { registrarPagina } from "../nucleo/paginas.js";

// Mesma regra do servidor (caminho_seguro em app/api/paginas.py): só caminhos deste site.
function destinoSeguro(proximo) {
    const interno = proximo && proximo.startsWith("/") && !proximo.startsWith("//") && !proximo.includes("\\");
    return interno ? proximo : "/";
}

function iniciarFormulario(raiz, enviar) {
    const formulario = raiz.querySelector("form");
    const erro = raiz.querySelector(".auth-erro");
    const botao = formulario.querySelector("button[type=submit]");

    // Foco no e-mail só se a pessoa ainda não clicou em nenhum campo. Esta função roda alguns milissegundos depois
    // de o formulário aparecer (o HTMX inicia a página após o "settle"); focar sempre roubaria o foco de quem já
    // começou a digitar (por isso também não usamos o atributo autofocus).
    if (!formulario.contains(document.activeElement)) formulario.querySelector("input")?.focus();

    formulario.addEventListener("submit", async (evento) => {
        evento.preventDefault();
        erro.hidden = true;
        botao.disabled = true;
        try {
            await enviar(new FormData(formulario));
            location.assign(destinoSeguro(raiz.dataset.proximo));
        } catch (falha) {
            erro.textContent = falha.message;
            erro.hidden = false;
            botao.disabled = false;
        }
    });
    botao.disabled = false; // o envio agora é pelo JS (o template deixa o botão desabilitado até aqui)
}

registrarPagina("login", (raiz) => {
    iniciarFormulario(raiz, (dados) => api.auth.login(dados.get("email"), dados.get("senha")));
});

registrarPagina("cadastro", (raiz) => {
    iniciarFormulario(raiz, async (dados) => {
        if (dados.get("senha") !== dados.get("confirmacao")) throw new Error("As senhas não conferem.");
        return api.auth.cadastro(dados.get("email"), dados.get("senha"));
    });
});
