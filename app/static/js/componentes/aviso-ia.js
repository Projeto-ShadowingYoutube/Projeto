// Aviso de privacidade dos desafios com IA (Reading, Writing, Speaking): o texto do usuário vai para um
// provedor externo de IA. Mostre-o na tela do desafio ANTES de a pessoa enviar o texto ou a gravação.
//
// criarAvisoIA(texto) → elemento pronto para inserir. O texto vem de api.situacaoLLM() (campo "aviso"),
// para a redação ficar num lugar só (app/api/llm.py). O visual (.aviso-ia) está em static/css/decks.css.

export function criarAvisoIA(texto) {
    const aviso = document.createElement("p");
    aviso.className = "aviso-ia";
    aviso.setAttribute("role", "note");

    const icone = document.createElement("span");
    icone.className = "aviso-ia-icone";
    icone.setAttribute("aria-hidden", "true");
    icone.textContent = "ⓘ";

    const mensagem = document.createElement("span");
    mensagem.textContent = texto; // textContent, nunca innerHTML

    aviso.append(icone, mensagem);
    return aviso;
}
