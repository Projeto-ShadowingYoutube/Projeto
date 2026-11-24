// Cliente da API do Reading Challenge (Membro 1): todas as URLs de /api/reading ficam aqui.
// Usa requisitarJSON/enviarJSON da base, que já tratam a sessão vencida (vai ao login) e o formato de erro
// (erro.message, erro.codigo).
import { enviarJSON, requisitarJSON } from "./api.js";

const BASE = "/api/reading/challenges";

export const apiReading = {
    // { modalidade, fonte, ppm } → desafio com o texto (sem as perguntas). Gasta 1 da cota diária.
    criar: (escolhas) => enviarJSON(BASE, "POST", escolhas),
    resumo: (id) => requisitarJSON(`${BASE}/${id}`),
    // O texto de novo (ex.: depois do F5), só dentro do prazo; depois, erro.codigo "leitura_encerrada".
    texto: (id) => requisitarJSON(`${BASE}/${id}/texto`),
    // Fim da leitura → as perguntas, sem as respostas. Idempotente.
    encerrarLeitura: (id) => enviarJSON(`${BASE}/${id}/encerrar-leitura`, "POST"),
    enviarRespostas: (id, respostas) => enviarJSON(`${BASE}/${id}/respostas`, "POST", { respostas }),
    resultado: (id) => requisitarJSON(`${BASE}/${id}/resultado`),
    avaliar: (id) => enviarJSON(`${BASE}/${id}/avaliar`, "POST"),
};
