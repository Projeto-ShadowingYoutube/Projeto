// Alterna entre o tema claro e o escuro. O CSS faz o resto a partir do atributo data-theme da tag <html>.

export function iniciarTema() {
    const raiz = document.documentElement;
    const botao = document.getElementById("mode");

    function aplicarTema(tema) {
        raiz.dataset.theme = tema;
        botao.textContent = tema === "dark" ? "☀️" : "🌙";
        try {
            localStorage.setItem("tema", tema);
        } catch {
            // Sem acesso ao localStorage (ex: janela anônima): o tema só não fica salvo.
        }
    }

    let temaSalvo = null;
    try {
        temaSalvo = localStorage.getItem("tema");
    } catch {}

    aplicarTema(temaSalvo === "light" ? "light" : "dark");
    botao.addEventListener("click", () => aplicarTema(raiz.dataset.theme === "dark" ? "light" : "dark"));
}
