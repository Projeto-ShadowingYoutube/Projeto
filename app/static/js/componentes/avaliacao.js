// Painel com a avaliação da fala (app/services/avaliacao.py): nota geral, notas de palavras, ritmo e
// entonação, o desenho das duas melodias e dicas. Também marca na legenda as palavras que faltaram.
import { Legenda } from "./legenda.js";

export const Avaliacao = (() => {
    const NOTAS = [
        ["palavras", "Palavras", "Quantas palavras da frase você disse."],
        ["ritmo", "Ritmo", "Se as pausas e a duração de cada palavra acompanham o original (sem contar a velocidade)."],
        ["entonacao", "Entonação", "Se a melodia da sua voz (onde sobe e desce) acompanha a do original."],
    ];

    const elemento = (id) => document.getElementById(id);

    function criar(tag, classe, texto) {
        const novo = document.createElement(tag);
        if (classe) novo.className = classe;
        if (texto !== undefined) novo.textContent = texto;
        return novo;
    }

    const faixa = (nota) => (nota >= 80 ? "boa" : nota >= 50 ? "media" : "fraca");

    function medidor(nome, titulo, explicacao, nota) {
        const linha = criar("div", "avaliacao-medidor");
        linha.title = explicacao;
        const barra = criar("div", "avaliacao-barra");
        const preenchimento = criar("div", `avaliacao-preenchimento ${nota === null ? "" : faixa(nota)}`);
        preenchimento.style.width = `${nota ?? 0}%`;
        barra.append(preenchimento);
        linha.append(criar("span", "avaliacao-rotulo", titulo), barra, criar("span", "avaliacao-numero", nota ?? "—"));
        linha.dataset.nota = nome;
        return linha;
    }

    // As duas melodias (semitons) num mini gráfico: original tracejado, usuário em roxo.
    function graficoDaEntonacao({ curva_original: original, curva_usuario: usuario }) {
        const largura = 300;
        const altura = 60;
        const todos = [...original, ...usuario];
        const minimo = Math.min(...todos);
        const amplitude = Math.max(...todos) - minimo || 1;
        const pontos = (curva) => curva
            .map((valor, i) => `${(i / (curva.length - 1)) * largura},${altura - 4 - ((valor - minimo) / amplitude) * (altura - 8)}`)
            .join(" ");

        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", `0 0 ${largura} ${altura}`);
        svg.setAttribute("preserveAspectRatio", "none");
        svg.classList.add("avaliacao-grafico");
        for (const [curva, classe] of [[original, "linha-original"], [usuario, "linha-usuario"]]) {
            const linha = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
            linha.setAttribute("points", pontos(curva));
            linha.setAttribute("class", classe);
            svg.append(linha);
        }
        const legenda = criar("div", "avaliacao-legenda-grafico");
        legenda.append(criar("span", "item-original", "original"), criar("span", "item-usuario", "você"));
        const bloco = criar("div", "avaliacao-entonacao");
        bloco.append(svg, legenda);
        return bloco;
    }

    // Cada dica é [texto com a legenda visível, texto com a legenda oculta]. As duas versões vão para a
    // página e o CSS mostra a certa, então a dica acompanha o botão do olho na hora.
    function dicas(resultado, palavras) {
        const lista = [];
        const faltaram = palavras.filter((_, i) => resultado.palavras.ditas[i] === false);
        if (faltaram.length) {
            // Com a legenda oculta, não entrega a resposta.
            lista.push([`Faltou: ${faltaram.join(" ")}`,
                `Faltaram ${faltaram.length} palavra(s). Mostre a legenda para ver quais.`]);
        }
        if (resultado.ritmo && resultado.ritmo.nota < 70) {
            const dica = "Ritmo: ouça de novo e repare onde a pessoa pausa e quais palavras ela estica.";
            lista.push([dica, dica]);
        }
        if (resultado.entonacao && resultado.entonacao.nota < 60) {
            const dica = "Entonação: imite a melodia, onde a voz sobe e onde desce.";
            lista.push([dica, dica]);
        }
        if (!lista.length) lista.push(["Muito bom! Tente agora com a legenda oculta.", "Excelente!"]);
        return lista;
    }

    function itemDeDica([comLegenda, semLegenda]) {
        const item = criar("li");
        item.append(criar("span", "com-legenda", comLegenda), criar("span", "sem-legenda", semLegenda));
        return item;
    }

    // "avaliacao": null (nada a mostrar) | "avaliando" | "erro" | resultado do servidor.
    function mostrar(avaliacao, texto) {
        const painel = elemento("avaliacao");
        if (!painel) return;
        Legenda.marcarDitas(avaliacao?.palavras?.ditas ?? null);
        painel.hidden = avaliacao === null;
        if (avaliacao === null) return;

        if (avaliacao === "avaliando" || avaliacao === "erro") {
            painel.replaceChildren(criar(
                "p", "avaliacao-status",
                avaliacao === "avaliando" ? "Avaliando sua fala..." : "Não foi possível avaliar esta gravação.",
            ));
            return;
        }

        const nota = criar("div", `avaliacao-nota ${faixa(avaliacao.nota)}`);
        nota.append(criar("strong", "", avaliacao.nota), criar("span", "", "nota"));
        const medidores = criar("div", "avaliacao-medidores");
        NOTAS.forEach(([nome, titulo, explicacao]) => {
            // Sem entonação (desligada no servidor ou sem voz detectada), a linha nem aparece.
            if (nome === "entonacao" && !avaliacao.entonacao) return;
            medidores.append(medidor(nome, titulo, explicacao, avaliacao[nome]?.nota ?? null));
        });
        const topo = criar("div", "avaliacao-topo");
        topo.append(nota, medidores);

        const partes = [topo];
        if (avaliacao.entonacao) partes.push(graficoDaEntonacao(avaliacao.entonacao));
        const listaDeDicas = criar("ul", "avaliacao-dicas");
        dicas(avaliacao, texto.split(/\s+/).filter(Boolean)).forEach((dica) => listaDeDicas.append(itemDeDica(dica)));
        partes.push(listaDeDicas);
        painel.replaceChildren(...partes);
    }

    return { mostrar };
})();
