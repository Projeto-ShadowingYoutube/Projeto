// Cliente da API do Writing Challenge (Membro 3). Usa requisitarJSON/enviarJSON de api.js (base, não alterada), que
// já levam ao login quando a sessão vence e transformam erros em exceções com erro.message e erro.codigo.
import { enviarJSON, requisitarJSON } from "./api.js";

const redacao = (id) => `/api/writing/attempts/${id}`;

export const apiWriting = {
    categorias: () => requisitarJSON("/api/writing/categorias"),
    listar: () => requisitarJSON("/api/writing/attempts"),
    obter: (id) => requisitarJSON(redacao(id)),
    // Sem categoria: "Surpresa". Gasta 1 desafio da cota diária.
    criar: (categoria) => enviarJSON("/api/writing/challenges", "POST", categoria ? { categoria } : {}),
    salvar: (id, texto) => enviarJSON(redacao(id), "PATCH", { texto }),
    enviar: (id, texto) => enviarJSON(`${redacao(id)}/submissao`, "POST", { texto }),
    // "Avaliar de novo" depois de uma falha da correção (até 3 por redação; não gasta cota).
    avaliar: (id) => enviarJSON(`${redacao(id)}/avaliacao`, "POST"),
    // Rewrite Challenge: o estado (rodada, problemas, histórico) e o envio de uma rodada inteira.
    rewrite: (id) => requisitarJSON(`${redacao(id)}/rewrite`),
    enviarRewrite: (id, reescritas) => enviarJSON(`${redacao(id)}/rewrite`, "POST", { reescritas }),

    // Autosave ao fechar a aba ou recarregar (evento pagehide). keepalive: o navegador conclui o envio mesmo com a
    // página indo embora. Não dá para esperar a resposta, então falhas são ignoradas (valem os autosaves anteriores).
    salvarAoSair: (id, texto) => {
        try {
            fetch(redacao(id), {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ texto }),
                keepalive: true,
            }).catch(() => {});
        } catch {
            // navegador sem keepalive (ou corpo grande demais para ele): nada a fazer
        }
    },
};
