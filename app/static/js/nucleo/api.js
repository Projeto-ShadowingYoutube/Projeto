// Cliente da API do servidor: todas as URLs do app ficam aqui.

// fetch que converte a resposta em JSON e transforma respostas de erro em exceções com a mensagem do servidor.
export async function requisitarJSON(url, opcoes) {
    const resposta = await fetch(url, opcoes);
    if (resposta.status === 204) return null;
    const dados = await resposta.json().catch(() => null);
    if (!resposta.ok) {
        const erro = new Error(mensagemDeErro(dados) || `Erro ${resposta.status} ao acessar ${url}`);
        erro.status = resposta.status;
        erro.dados = dados;
        throw erro;
    }
    return dados;
}

// O FastAPI devolve "detail" como texto ou, em erros de validação, como lista de problemas.
function mensagemDeErro(dados) {
    const detalhe = dados?.detail;
    if (Array.isArray(detalhe)) return detalhe.map((problema) => problema.msg).join("; ");
    return detalhe;
}

function enviarJSON(url, metodo, corpo) {
    return requisitarJSON(url, {
        method: metodo,
        headers: corpo === undefined ? {} : { "Content-Type": "application/json" },
        body: corpo === undefined ? undefined : JSON.stringify(corpo),
    });
}

const consulta = (parametros) => new URLSearchParams(parametros).toString();

export const api = {
    tokens: () => requisitarJSON("/api/tokens"),
    legendas: (link) => requisitarJSON(`/api/legendas?${consulta({ url: link })}`),
    dicionario: (palavra, frase, indice) => requisitarJSON(`/api/dicionario?${consulta({ palavra, frase, indice })}`),

    videos: {
        status: (videoId) => requisitarJSON(`/api/videos/${videoId}/status`),
        url: (videoId) => `/api/videos/${videoId}`,
        urlAudio: (videoId, inicio, fim) => `/api/videos/${videoId}/audio?${consulta({ inicio, fim })}`,
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
