// Cliente da API do servidor: todas as URLs do app ficam aqui.

// Leva para o login e, depois de entrar, de volta para a página atual.
export function irParaLogin() {
    const aqui = location.pathname + location.search;
    location.assign(`/login?${new URLSearchParams({ proximo: aqui })}`);
}

// fetch que converte a resposta em JSON e transforma respostas de erro em exceções com a mensagem do servidor.
export async function requisitarJSON(url, opcoes) {
    const resposta = await fetch(url, opcoes);
    // Sessão ausente ou vencida (ex.: expirou no meio do estudo): vai para o login. As rotas /api/auth/ ficam de
    // fora: lá o 401 é "senha errada", e quem chamou mostra a mensagem na tela.
    if (resposta.status === 401 && !url.startsWith("/api/auth/")) {
        irParaLogin();
        return new Promise(() => {}); // a página vai ser trocada: quem chamou não deve mostrar erro
    }
    if (resposta.status === 204) return null;
    const dados = await resposta.json().catch(() => null);
    if (!resposta.ok) {
        // Formato de erro da API (app/erros.py e README): {detail, codigo, ...extras}.
        const erro = new Error(mensagemDeErro(dados) || `Erro ${resposta.status} ao acessar ${url}`);
        erro.status = resposta.status;
        erro.codigo = dados?.codigo ?? null; // estável: use para decidir o que fazer (o texto pode mudar)
        erro.dados = dados;                  // o corpo inteiro, com os extras (ex.: tokens_restantes, erros)
        throw erro;
    }
    return dados;
}

// "detail" é sempre texto na API atual. A lista só aparece em respostas no formato antigo do FastAPI.
function mensagemDeErro(dados) {
    const detalhe = dados?.detail;
    if (Array.isArray(detalhe)) return detalhe.map((problema) => problema.msg).join("; ");
    return detalhe;
}

// Exportada para as features novas criarem o próprio cliente (ex.: nucleo/api-reading.js), sem alterar este arquivo.
export function enviarJSON(url, metodo, corpo) {
    return requisitarJSON(url, {
        method: metodo,
        headers: corpo === undefined ? {} : { "Content-Type": "application/json" },
        body: corpo === undefined ? undefined : JSON.stringify(corpo),
    });
}

const consulta = (parametros) => new URLSearchParams(parametros).toString();

export const api = {
    auth: {
        login: (email, senha) => enviarJSON("/api/auth/login", "POST", { email, senha }),
        cadastro: (email, senha) => enviarJSON("/api/auth/cadastro", "POST", { email, senha }),
        logout: () => enviarJSON("/api/auth/logout", "POST"),
    },

    configuracoes: {
        obter: () => requisitarJSON("/api/configuracoes"),
        alterar: (mudancas) => enviarJSON("/api/configuracoes", "PATCH", mudancas),
    },

    tokens: () => requisitarJSON("/api/tokens"),
    // Desafios com IA: se a IA está configurada, aviso de privacidade e cota diária de cada feature.
    situacaoLLM: () => requisitarJSON("/api/llm/situacao"),
    legendas: (link) => requisitarJSON(`/api/legendas?${consulta({ url: link })}`),
    dicionario: (palavra, frase, indice) => requisitarJSON(`/api/dicionario?${consulta({ palavra, frase, indice })}`),

    videos: {
        status: (videoId) => requisitarJSON(`/api/videos/${videoId}/status`),
        url: (videoId) => `/api/videos/${videoId}`,
        urlAudio: (videoId, inicio, fim) => `/api/videos/${videoId}/audio?${consulta({ inicio, fim })}`, // sem uso desde o B9
        urlWaveform: (videoId, inicio, fim) => `/api/videos/${videoId}/waveform?${consulta({ inicio, fim })}`,
        temposPalavras: (videoId, inicio, fim, texto) =>
            requisitarJSON(`/api/videos/${videoId}/palavras?${consulta({ inicio, fim, texto })}`),
    },

    decks: {
        listar: () => requisitarJSON("/api/decks"),
        criar: (nome) => enviarJSON("/api/decks", "POST", { nome }),
        renomear: (deckId, nome) => enviarJSON(`/api/decks/${deckId}`, "PATCH", { nome }),
        deletar: (deckId) => enviarJSON(`/api/decks/${deckId}`, "DELETE"),
        salvarCard: (deckId, card) => enviarJSON(`/api/decks/${deckId}/cards`, "POST", card),
        cardsParaRevisar: (deckId) => requisitarJSON(`/api/decks/${deckId}/revisao`),
    },

    // dados: { contexto: { videoId, inicio, fim, texto }, gravacao: Blob, offset, duracao, transcricao, velocidade }
    avaliarFala: ({ contexto, gravacao, offset, duracao, transcricao, velocidade }) => {
        const formulario = new FormData();
        formulario.append("gravacao", gravacao, "gravacao.webm");
        Object.entries({
            video_id: contexto.videoId, inicio: contexto.inicio, fim: contexto.fim, texto: contexto.texto,
            transcricao, offset, duracao, velocidade,
        }).forEach(([chave, valor]) => formulario.append(chave, valor));
        return requisitarJSON("/api/avaliacoes", { method: "POST", body: formulario });
    },

    cards: {
        avaliar: (cardId, dificuldade) => enviarJSON(`/api/cards/${cardId}/avaliacao`, "POST", { dificuldade }),
        deletar: (cardId) => enviarJSON(`/api/cards/${cardId}`, "DELETE"),
    },
};
