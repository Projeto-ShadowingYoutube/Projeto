// Destaques da redação corrigida (Writing Challenge, Membro 3). Módulo PURO: sem imports e sem DOM, para que os
// testes (tests/writing/test_paginas.py) executem este mesmo código no Node.js.

export const CATEGORIAS_AVALIADAS = ["gramatica", "vocabulario", "coerencia", "organizacao", "atendimento_tarefa"];

export const NOMES_DAS_CATEGORIAS = {
    gramatica: "Gramática",
    vocabulario: "Vocabulário",
    coerencia: "Coerência",
    organizacao: "Organização",
    atendimento_tarefa: "Atendimento à tarefa",
};

export const NOMES_DAS_GRAVIDADES = { 1: "leve", 2: "média", 3: "alta" };

// Divide o texto em partes: [{ texto, trecho }], com trecho = índice em `trechos` (parte destacada) ou null.
// As posições inicio/fim vêm do servidor em caracteres Unicode (como no Python). Por isso o recorte usa
// Array.from(texto), e não texto.slice: no JS, um emoji ocupa 2 posições e deslocaria os destaques seguintes.
// O servidor já entrega trechos sem sobreposição (D14), mas a tela não confia cegamente: trecho fora dos limites,
// vazio ou sobreposto a outro é ignorado. A concatenação das partes é sempre igual ao texto original.
export function partesDoTexto(texto, trechos = []) {
    const caracteres = Array.from(texto);
    const validos = trechos
        .map((trecho, indice) => ({ inicio: trecho.inicio, fim: trecho.fim, indice }))
        .filter(({ inicio, fim }) => Number.isInteger(inicio) && Number.isInteger(fim)
            && inicio >= 0 && fim <= caracteres.length && inicio < fim)
        .sort((a, b) => a.inicio - b.inicio || a.indice - b.indice);

    const partes = [];
    let posicao = 0;
    for (const { inicio, fim, indice } of validos) {
        if (inicio < posicao) continue;  // sobreposto ao anterior
        if (inicio > posicao) partes.push({ texto: caracteres.slice(posicao, inicio).join(""), trecho: null });
        partes.push({ texto: caracteres.slice(inicio, fim).join(""), trecho: indice });
        posicao = fim;
    }
    if (posicao < caracteres.length) partes.push({ texto: caracteres.slice(posicao).join(""), trecho: null });
    return partes;
}

// Rewrite Challenge: destaca o trecho apontado (citacao) dentro da frase a reescrever. → [{ texto, destaque }]
// A citação e a frase vêm do servidor como textos inteiros (sem posições), então indexOf/slice são consistentes
// entre si. Citação ausente: a frase inteira, sem destaque. Repetida na frase: destaca a primeira ocorrência.
export function partesDaFrase(frase, citacao) {
    const inicio = citacao ? frase.indexOf(citacao) : -1;
    if (inicio === -1) return [{ texto: frase, destaque: false }];
    const fim = inicio + citacao.length;
    return [
        { texto: frase.slice(0, inicio), destaque: false },
        { texto: citacao, destaque: true },
        { texto: frase.slice(fim), destaque: false },
    ].filter((parte) => parte.texto);
}

// 7.4 → "7,4"
export function formatarNota(nota) {
    return Number(nota).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}
