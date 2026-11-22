// Página do Writing Challenge (templates/paginas/writing.html), Membro 3. Cinco telas na mesma página:
//   início (categorias, aviso de IA, cota, redações recentes) → editor (contador, timer, autosave)
//   → resultado (notas, resumo, redação com os trechos destacados) ou fim (enviada sem correção / tempo esgotado)
//   → rewrite (reescrever as frases problemáticas, em até 2 rodadas, com a comparação e o veredito da IA).
// A redação aberta fica na URL (/writing?redacao=7): recarregar a página volta ao editor com o texto e o tempo.
// Conteúdo do servidor (tema, texto, nomes) entra só com textContent/value, nunca innerHTML.
import { criarAvisoIA } from "../componentes/aviso-ia.js";
import { criarEstadoVazio } from "../componentes/estado-vazio.js";
import {
    CATEGORIAS_AVALIADAS, NOMES_DAS_CATEGORIAS, NOMES_DAS_GRAVIDADES, formatarNota, partesDaFrase, partesDoTexto,
} from "../componentes/writing-destaques.js";
import { api } from "../nucleo/api.js";
import { apiWriting } from "../nucleo/api-writing.js";
import { contagemRegressiva, formatarTempo } from "../nucleo/interface.js";
import { registrarPagina } from "../nucleo/paginas.js";

// MESMA regra de app/services/writing_texto.py (tests/writing/test_paginas.py confere que a expressão é a mesma).
const PALAVRA = /[\p{L}\p{N}]+(?:['’-][\p{L}\p{N}]+)*/gu;

export function contarPalavras(texto) {
    return (texto.normalize("NFC").match(PALAVRA) || []).length;
}

const MIN_PALAVRAS_ENVIO = 50;         // D3 (o servidor confere de novo)
const ATRASO_AUTOSAVE_MS = 3000;       // D12: salva 3 s depois de parar de digitar...
const INTERVALO_AUTOSAVE_MS = 30000;   // ...e a cada 30 s, se houver mudança
const QUANTIDADE_RECENTES = 10;
const NOMES_DOS_ESTADOS = {
    rascunho: "rascunho", enviada: "enviada", avaliada: "avaliada", erro_avaliacao: "erro na avaliação",
};

const plural = (n, singular, varias) => `${n} ${n === 1 ? singular : varias}`;
const hora = (dataIso) => dataIso.slice(11, 16);  // "2026-11-21T14:32:05" → "14:32" (o servidor já manda no horário de Brasília)
const data = (dataIso) => `${dataIso.slice(8, 10)}/${dataIso.slice(5, 7)} ${hora(dataIso)}`;

registrarPagina("writing", (raiz) => {
    const campo = (nome) => raiz.querySelector(`[data-${nome}]`);
    const telas = Object.fromEntries(
        ["inicio", "editor", "fim", "resultado", "rewrite"].map(
            (nome) => [nome, raiz.querySelector(`[data-tela="${nome}"]`)],
        ),
    );
    const texto = campo("texto");
    const botaoEnviar = campo("enviar");

    let redacao = null;         // a redação aberta no editor (resposta da API)
    let ultimoSalvo = "";       // o texto que o servidor já tem
    let salvando = null;        // promessa do autosave em andamento
    let enviando = false;
    let cancelarTimer = null;
    let temporizador = null;    // autosave com atraso
    let intervalo = null;       // autosave periódico
    let categorias = [];

    function mostrarTela(nome) {
        limparAviso();
        Object.entries(telas).forEach(([chave, tela]) => { tela.hidden = chave !== nome; });
    }

    // Erros na própria tela ([data-erro] de cada uma), e não no modal da base (mostrarErro): o botão "início" do
    // modal leva para a tela do Shadowing, fora do Writing. Como mostrarTela() apaga o aviso, quem troca de tela por
    // causa de um erro chama avisar() DEPOIS da troca.
    function avisar(mensagem) {
        const aviso = Object.values(telas).find((tela) => !tela.hidden)?.querySelector("[data-erro]");
        if (!aviso) return;
        aviso.textContent = mensagem;
        aviso.hidden = false;
    }

    function limparAviso() {
        raiz.querySelectorAll("[data-erro]").forEach((aviso) => {
            aviso.hidden = true;
            aviso.textContent = "";
        });
    }

    function definirUrl(id, noRewrite = false) {
        const url = id ? `/writing?redacao=${id}${noRewrite ? "&rewrite=1" : ""}` : "/writing";
        history.replaceState(history.state, "", url);
    }

    // --- Início ---

    async function abrirInicio() {
        pararEditor();
        redacao = null;
        definirUrl(null);
        mostrarTela("inicio");
        await Promise.all([carregarSituacao(), carregarCategorias(), carregarRecentes()]);
    }

    async function carregarSituacao() {
        let situacao;
        try {
            situacao = await api.situacaoLLM();
        } catch {
            campo("cota").textContent = "";
            return;
        }
        const { aviso, configurada, cotas } = situacao;
        campo("aviso-ia").replaceChildren(criarAvisoIA(aviso));
        campo("aviso-ia-envio").replaceChildren(criarAvisoIA(aviso));
        const cota = cotas.writing;
        campo("cota").textContent = `${cota.restantes} de ${cota.limite} desafios disponíveis hoje`;
        if (!configurada) {
            const nota = document.createElement("p");
            nota.className = "writing-nota";
            nota.textContent = "A correção por IA não está configurada neste servidor: você pode escrever e enviar, "
                + "mas a correção não ficará disponível.";
            campo("aviso-ia").append(nota);
        }
    }

    async function carregarCategorias() {
        const area = campo("categorias");
        try {
            if (!categorias.length) categorias = await apiWriting.categorias();
        } catch (erro) {
            area.replaceChildren(criarEstadoVazio({
                titulo: "Não foi possível carregar as categorias.", texto: erro.message,
                acoes: [{ rotulo: "Tentar de novo", principal: true, aoClicar: carregarCategorias }],
            }));
            return;
        }
        const botoes = categorias.map((categoria) => botaoDeCategoria(
            categoria.nome,
            `${categoria.prova} · ${categoria.tempo_limite_segundos / 60} min · ${categoria.palavras_minimas}+ palavras`,
            categoria.slug,
        ));
        botoes.push(botaoDeCategoria("Surpresa", "Uma categoria qualquer, sorteada", null, true));
        area.replaceChildren(...botoes);
    }

    function botaoDeCategoria(nome, detalhe, slug, surpresa = false) {
        const botao = document.createElement("button");
        botao.type = "button";
        botao.className = surpresa ? "writing-categoria-botao surpresa" : "writing-categoria-botao";
        const titulo = document.createElement("strong");
        titulo.textContent = nome;
        const descricao = document.createElement("span");
        descricao.textContent = detalhe;
        botao.append(titulo, descricao);
        botao.addEventListener("click", () => criarDesafio(slug));
        return botao;
    }

    async function criarDesafio(categoria) {
        const botoes = campo("categorias").querySelectorAll("button");
        botoes.forEach((botao) => { botao.disabled = true; });
        limparAviso();
        try {
            abrirEditor(await apiWriting.criar(categoria));
        } catch (erro) {
            avisar(erro.message);  // ex.: 429, com o tempo até a cota renovar
            carregarSituacao();
        } finally {
            botoes.forEach((botao) => { botao.disabled = false; });
        }
    }

    async function carregarRecentes() {
        const area = campo("recentes");
        let lista;
        try {
            lista = await apiWriting.listar();
        } catch (erro) {
            area.replaceChildren(criarEstadoVazio({
                titulo: "Não foi possível carregar as suas redações.", texto: erro.message,
                acoes: [{ rotulo: "Tentar de novo", principal: true, aoClicar: carregarRecentes }],
            }));
            return;
        }
        if (!lista.length) {
            area.replaceChildren(criarEstadoVazio({
                titulo: "Nenhuma redação ainda",
                texto: "Escolha uma categoria acima para começar. As suas redações aparecem aqui.",
            }));
            return;
        }
        area.replaceChildren(...lista.slice(0, QUANTIDADE_RECENTES).map(itemRecente));
    }

    function itemRecente(item) {
        const botao = document.createElement("button");
        botao.type = "button";
        botao.className = "writing-recente";
        const nome = document.createElement("strong");
        nome.textContent = item.categoria_nome;
        const estado = document.createElement("span");
        estado.className = `writing-estado ${item.estado}`;
        estado.textContent = NOMES_DOS_ESTADOS[item.estado] ?? item.estado;
        const detalhe = document.createElement("span");
        detalhe.className = "writing-recente-detalhe";
        detalhe.textContent = `${data(item.iniciada_em)} · ${plural(item.palavras, "palavra", "palavras")}`;
        botao.append(nome, estado);
        if (item.nota_geral !== null && item.nota_geral !== undefined) {
            const nota = document.createElement("span");
            nota.className = "writing-nota-recente";
            nota.title = "Nota geral";
            nota.textContent = formatarNota(item.nota_geral);
            botao.append(nota);
        }
        botao.append(detalhe);
        botao.addEventListener("click", () => abrir(item.id));
        return botao;
    }

    async function abrir(id) {
        let dados;
        try {
            dados = await apiWriting.obter(id);
        } catch (erro) {
            await abrirInicio();
            avisar(erro.message);  // depois da troca de tela (ex.: 404 de /writing?redacao=99999)
            return;
        }
        mostrarRedacao(dados);
    }

    // Leva cada redação à tela certa pelo estado dela.
    function mostrarRedacao(dados) {
        if (dados.estado === "rascunho") abrirEditor(dados);
        else if (dados.feedback) mostrarResultado(dados);
        else mostrarEnviada(dados);
    }

    // --- Editor ---

    function abrirEditor(dados) {
        pararEditor();
        redacao = dados;
        ultimoSalvo = dados.texto;
        definirUrl(dados.id);
        campo("categoria").textContent = dados.categoria_nome;
        campo("detalhe").textContent = `${dados.tempo_limite_segundos / 60} min · mínimo recomendado: `
            + plural(dados.palavras_minimas, "palavra", "palavras");
        campo("enunciado").textContent = dados.enunciado;
        texto.value = dados.texto;
        texto.readOnly = false;
        mostrarSalvo(dados.salva_em ? `Salvo às ${hora(dados.salva_em)}` : "");
        atualizarContador();
        mostrarTela("editor");
        texto.focus();
        intervalo = setInterval(salvar, INTERVALO_AUTOSAVE_MS);
        iniciarTimer(dados.segundos_restantes);
    }

    function iniciarTimer(segundos) {
        const timer = campo("timer");
        const aoAcabar = () => {
            timer.textContent = "0:00";
            timer.classList.add("acabando");
            enviar({ automatico: true });
        };
        if (segundos <= 0) {
            aoAcabar();
            return;
        }
        cancelarTimer = contagemRegressiva(segundos, (restante) => {
            timer.textContent = formatarTempo(restante);
            timer.classList.toggle("acabando", restante <= 60);
        }, aoAcabar);
    }

    function pararEditor() {
        cancelarTimer?.();
        cancelarTimer = null;
        clearTimeout(temporizador);
        clearInterval(intervalo);
        temporizador = intervalo = null;
    }

    function atualizarContador() {
        const palavras = contarPalavras(texto.value);
        const contador = campo("contador");
        contador.textContent = plural(palavras, "palavra", "palavras");
        contador.classList.toggle("atingiu", palavras >= redacao.palavras_minimas);
        const faltam = MIN_PALAVRAS_ENVIO - palavras;
        botaoEnviar.disabled = faltam > 0 || enviando;
        campo("dica").textContent = faltam > 0
            ? `Faltam ${plural(faltam, "palavra", "palavras")} para poder enviar.` : "";
    }

    function mostrarSalvo(mensagem, erro = false) {
        const salvo = campo("salvo");
        salvo.textContent = mensagem;
        salvo.classList.toggle("erro", erro);
    }

    function aoDigitar() {
        atualizarContador();
        if (texto.value !== ultimoSalvo) mostrarSalvo("Alterações não salvas");
        clearTimeout(temporizador);
        temporizador = setTimeout(salvar, ATRASO_AUTOSAVE_MS);
    }

    async function salvar() {
        clearTimeout(temporizador);
        temporizador = null;
        if (!redacao || redacao.estado !== "rascunho" || enviando) return;
        if (salvando) return salvando.then(salvar);  // um autosave por vez; depois confere se ainda falta salvar
        const conteudo = texto.value;
        if (conteudo === ultimoSalvo) return;
        mostrarSalvo("Salvando…");
        salvando = apiWriting.salvar(redacao.id, conteudo)
            .then((resposta) => {
                ultimoSalvo = conteudo;
                if (texto.value === conteudo) mostrarSalvo(`Salvo às ${hora(resposta.salva_em)}`);
            })
            .catch((erro) => {
                if (erro.codigo === "prazo_encerrado") enviar({ automatico: true });
                else if (erro.codigo === "redacao_ja_enviada") abrir(redacao.id);
                else mostrarSalvo("Não foi possível salvar; tentando de novo…", true);  // o autosave de 30 s tenta de novo
            })
            .finally(() => { salvando = null; });
        return salvando;
    }

    // --- Envio ---

    async function enviar({ automatico = false } = {}) {
        if (!redacao || redacao.estado !== "rascunho" || enviando) return;
        // D11: confirma no botão; o envio automático do fim do tempo não pergunta.
        if (!automatico && !confirm("Enviar a redação? Depois de enviada, ela não pode mais ser editada.")) return;
        enviando = true;
        limparAviso();
        clearTimeout(temporizador);
        botaoEnviar.disabled = true;
        botaoEnviar.textContent = "Enviando e corrigindo…";
        texto.readOnly = true;
        try {
            if (salvando) await salvando.catch(() => {});
            const enviada = await apiWriting.enviar(redacao.id, texto.value);
            pararEditor();
            mostrarRedacao(enviada);  // corrigida → resultado
        } catch (erro) {
            if (erro.codigo === "redacao_curta" && automatico) {
                pararEditor();
                mostrarFim(
                    "O tempo acabou",
                    `A redação tinha ${plural(erro.dados.palavras, "palavra", "palavras")}, e o mínimo para enviar é `
                    + `${erro.dados.minimo}. Ela ficou guardada como rascunho, mas não pode mais ser enviada.`,
                    "Que tal tentar outro tema?",
                );
            } else if (erro.codigo === "redacao_ja_enviada") {
                pararEditor();
                await abrir(redacao.id);
            } else if (erro.codigo?.startsWith("llm_")) {
                // A redação foi gravada ANTES da correção (W6): só a correção falhou. Recarrega para saber o estado
                // e quantas avaliações restam.
                pararEditor();
                await recarregarDepoisDaFalha(erro);
            } else {
                avisar(erro.message);
                texto.readOnly = false;  // o texto continua na tela; dá para tentar de novo
            }
        } finally {
            enviando = false;
            botaoEnviar.textContent = "Enviar redação";
            if (redacao?.estado === "rascunho" && !telas.editor.hidden) atualizarContador();
        }
    }

    // Redação enviada SEM correção (falhou ou ficou pendente): explica e oferece "Avaliar de novo", se ainda houver.
    function mostrarEnviada(dados, falha = null) {
        redacao = dados;
        definirUrl(dados.id);
        const restantes = dados.avaliacoes_restantes ?? 0;
        let aviso = dados.usou_ultimo_salvamento ? "O tempo tinha acabado: foi enviado o último texto salvo. " : "";
        if (falha) aviso += `A correção falhou: ${falha} `;
        else if (dados.estado === "erro_avaliacao") aviso += "A correção falhou. ";
        else aviso += "A correção ainda não foi feita. ";
        aviso += restantes > 0
            ? `Você pode pedir uma nova avaliação (${plural(restantes, "tentativa restante", "tentativas restantes")}).`
            : "As tentativas de avaliação desta redação acabaram.";
        mostrarFim("Redação enviada", `${dados.categoria_nome} · ${plural(dados.palavras, "palavra", "palavras")}`, aviso);
        const botao = campo("avaliar");
        botao.hidden = restantes <= 0;
        botao.disabled = false;
        botao.textContent = "Avaliar de novo";
    }

    function mostrarFim(titulo, textoPrincipal, aviso) {
        campo("fim-titulo").textContent = titulo;
        campo("fim-texto").textContent = textoPrincipal;
        campo("fim-aviso").textContent = aviso;
        campo("avaliar").hidden = true;  // só mostrarEnviada o reexibe
        mostrarTela("fim");
    }

    async function recarregarDepoisDaFalha(erro) {
        try {
            mostrarEnviada(await apiWriting.obter(redacao.id), erro.message);
        } catch {
            mostrarEnviada({ ...redacao, estado: "erro_avaliacao" }, erro.message);
        }
    }

    async function avaliarDeNovo() {
        const botao = campo("avaliar");
        botao.disabled = true;
        botao.textContent = "Corrigindo…";
        limparAviso();
        try {
            mostrarRedacao(await apiWriting.avaliar(redacao.id));
        } catch (erro) {
            if (erro.codigo?.startsWith("llm_") || erro.codigo === "limite_de_avaliacoes") {
                await recarregarDepoisDaFalha(erro);
            } else if (erro.codigo === "redacao_ja_avaliada") {
                await abrir(redacao.id);
            } else {
                avisar(erro.message);
                botao.disabled = false;
                botao.textContent = "Avaliar de novo";
            }
        }
    }

    // --- Resultado ---

    function mostrarResultado(dados) {
        redacao = dados;
        definirUrl(dados.id);
        const { feedback } = dados;
        campo("res-categoria").textContent = dados.categoria_nome;
        campo("res-info").textContent = plural(dados.palavras, "palavra", "palavras");
        campo("res-nota").textContent = formatarNota(feedback.nota_geral);
        campo("res-enunciado").textContent = dados.enunciado;
        campo("res-resumo").textContent = feedback.resumo;
        campo("res-notas").replaceChildren(...CATEGORIAS_AVALIADAS.map((categoria) => cartaoDeNota(
            categoria, feedback.notas[categoria], feedback.trechos.filter((t) => t.categoria === categoria).length,
        )));
        campo("res-texto").replaceChildren(...partesDoTexto(dados.texto, feedback.trechos).map((parte) => (
            parte.trecho === null ? document.createTextNode(parte.texto) : marcaDoTrecho(parte, feedback.trechos)
        )));
        campo("res-legenda").replaceChildren(...CATEGORIAS_AVALIADAS.map((categoria) => {
            const item = document.createElement("span");
            item.className = `writing-legenda-item cat-${categoria}`;
            item.textContent = NOMES_DAS_CATEGORIAS[categoria];
            return item;
        }));
        mostrarDicaDoTrecho(feedback.trechos.length);
        campo("res-rewrite").hidden = feedback.trechos.length === 0;  // sem trechos, não há o que reescrever
        mostrarTela("resultado");
    }

    function cartaoDeNota(categoria, { nota, comentario }, quantidadeDeTrechos) {
        const cartao = document.createElement("div");
        cartao.className = `writing-nota cat-${categoria}`;
        const titulo = document.createElement("div");
        titulo.className = "writing-nota-titulo";
        const nome = document.createElement("span");
        nome.textContent = NOMES_DAS_CATEGORIAS[categoria];
        const valor = document.createElement("strong");
        valor.textContent = nota;
        titulo.append(nome, valor);
        const barra = document.createElement("div");
        barra.className = "writing-nota-barra";
        barra.setAttribute("role", "img");
        barra.setAttribute("aria-label", `${nota} de 10`);
        const preenchida = document.createElement("span");
        preenchida.style.width = `${Math.max(0, Math.min(10, nota)) * 10}%`;
        barra.append(preenchida);
        const texto = document.createElement("p");
        texto.textContent = comentario;
        cartao.append(titulo, barra, texto);
        if (quantidadeDeTrechos) {
            const trechos = document.createElement("span");
            trechos.className = "writing-nota-trechos";
            trechos.textContent = `${plural(quantidadeDeTrechos, "trecho destacado", "trechos destacados")} no texto`;
            cartao.append(trechos);
        }
        return cartao;
    }

    function marcaDoTrecho(parte, trechos) {
        const trecho = trechos[parte.trecho];
        const marca = document.createElement("mark");
        marca.className = `writing-marca cat-${trecho.categoria}`;
        marca.textContent = parte.texto;
        marca.tabIndex = 0;
        marca.setAttribute("role", "button");
        marca.setAttribute("aria-label", `${NOMES_DAS_CATEGORIAS[trecho.categoria] ?? trecho.categoria}: ${parte.texto}`);
        const selecionar = () => selecionarTrecho(trecho, marca);
        marca.addEventListener("click", selecionar);
        marca.addEventListener("keydown", (evento) => {
            if (evento.key === "Enter" || evento.key === " ") {
                evento.preventDefault();
                selecionar();
            }
        });
        return marca;
    }

    function mostrarDicaDoTrecho(quantidade) {
        const dica = document.createElement("p");
        dica.className = "writing-trecho-dica";
        dica.textContent = quantidade
            ? "Clique num trecho destacado para ver a explicação."
            : "Nenhum trecho problemático foi apontado nesta redação.";
        campo("res-trecho").replaceChildren(dica);
    }

    function selecionarTrecho(trecho, marca) {
        campo("res-texto").querySelectorAll(".writing-marca.ativa").forEach((outra) => outra.classList.remove("ativa"));
        marca.classList.add("ativa");

        const titulo = document.createElement("p");
        titulo.className = `writing-trecho-titulo cat-${trecho.categoria}`;
        titulo.textContent = `${NOMES_DAS_CATEGORIAS[trecho.categoria] ?? trecho.categoria} · gravidade `
            + (NOMES_DAS_GRAVIDADES[trecho.gravidade] ?? trecho.gravidade);
        const citacao = document.createElement("blockquote");
        citacao.textContent = trecho.citacao;
        const explicacao = document.createElement("p");
        explicacao.textContent = trecho.explicacao;
        const instrucao = document.createElement("p");
        const rotulo = document.createElement("strong");
        rotulo.textContent = "O que fazer: ";
        instrucao.append(rotulo, document.createTextNode(trecho.instrucao_reescrita));

        // D18: a versão corrigida só aparece se a pessoa pedir (o Rewrite Challenge pede para reescrever esses trechos).
        const sugestao = document.createElement("p");
        sugestao.className = "writing-trecho-sugestao";
        sugestao.hidden = true;
        const rotuloSugestao = document.createElement("strong");
        rotuloSugestao.textContent = "Sugestão: ";
        sugestao.append(rotuloSugestao, document.createTextNode(trecho.sugestao));
        const verSugestao = document.createElement("button");
        verSugestao.type = "button";
        verSugestao.className = "writing-botao pequeno";
        verSugestao.textContent = "Ver sugestão";
        verSugestao.addEventListener("click", () => {
            sugestao.hidden = false;
            verSugestao.remove();
        });

        campo("res-trecho").replaceChildren(titulo, citacao, explicacao, instrucao, sugestao, verSugestao);
    }

    // --- Rewrite Challenge ---
    // A tela é sempre redesenhada a partir do servidor (GET/POST .../rewrite); a URL leva &rewrite=1 (F5 volta aqui).

    let rewriteId = null;
    const textoInicial = new Map();  // campo → texto com que ele começou (D26: só envia frases alteradas)

    async function abrirRewrite(id) {
        rewriteId = id;
        let desafio;
        try {
            desafio = await apiWriting.rewrite(id);
        } catch (erro) {
            await abrir(id);
            avisar(erro.message);  // depois da troca de tela
            return;
        }
        desenharRewrite(desafio);
    }

    // manter: {indice: texto} digitado antes de uma falha (D23: os textos continuam nos campos).
    function desenharRewrite(desafio, manter = {}) {
        definirUrl(rewriteId, true);
        const { concluido, historico } = desafio;
        campo("rw-rodada").textContent = concluido ? "Concluído" : `Rodada ${desafio.rodada_atual} de 2`;

        const indicesFeitos = new Set(historico.map((h) => h.indice));
        const melhorados = new Set(historico.filter((h) => h.avaliacao.melhorou).map((h) => h.indice));
        const total = indicesFeitos.size;
        campo("rw-intro").textContent = concluido
            ? `Rewrite concluído: ${melhorados.size} de ${total} ${total === 1 ? "frase melhorou" : "frases melhoraram"}.`
            : "Reescreva cada frase seguindo a instrução. Uma IA avalia se o problema foi resolvido sem criar erros "
                + "novos e sem mudar o sentido.";

        textoInicial.clear();
        campo("rw-problemas").replaceChildren(...desafio.problemas.map((problema, posicao) => {
            const ultima = historico.filter((h) => h.indice === problema.indice).at(-1);
            const inicial = ultima ? ultima.reescrita : problema.frase;  // D24 (rodada 1) e D25 (rodada 2)
            return cartaoDoProblema(problema, posicao + 1, manter[problema.indice] ?? inicial, inicial);
        }));
        campo("rw-envio").hidden = concluido;
        atualizarEnvioDoRewrite();

        campo("rw-titulo-historico").hidden = historico.length === 0;
        campo("rw-historico").replaceChildren(...historico.map(itemDoHistorico));
        mostrarTela("rewrite");
    }

    function cartaoDoProblema(problema, numero, valor, inicial) {
        const cartao = document.createElement("section");
        cartao.className = `writing-rw-problema cat-${problema.categoria}`;

        const titulo = document.createElement("p");
        titulo.className = "writing-trecho-titulo";
        titulo.textContent = `${numero} · ${NOMES_DAS_CATEGORIAS[problema.categoria] ?? problema.categoria} · gravidade `
            + (NOMES_DAS_GRAVIDADES[problema.gravidade] ?? problema.gravidade);

        const frase = document.createElement("p");
        frase.className = "writing-rw-frase";
        const rotuloFrase = document.createElement("strong");
        rotuloFrase.textContent = "Frase: ";
        frase.append(rotuloFrase, ...partesDaFrase(problema.frase, problema.citacao).map((parte) => {
            if (!parte.destaque) return document.createTextNode(parte.texto);
            const marca = document.createElement("mark");
            marca.className = `writing-marca cat-${problema.categoria}`;
            marca.textContent = parte.texto;
            return marca;
        }));

        const explicacao = paragrafoComRotulo("O problema: ", problema.explicacao);
        const instrucao = paragrafoComRotulo("O que fazer: ", problema.instrucao);

        const campoTexto = document.createElement("textarea");
        campoTexto.className = "writing-rw-texto";
        campoTexto.maxLength = 1000;
        campoTexto.rows = 3;
        campoTexto.spellcheck = false;
        campoTexto.value = valor;
        campoTexto.dataset.indice = problema.indice;
        campoTexto.setAttribute("aria-label", `Reescrita da frase ${numero}`);
        campoTexto.addEventListener("input", () => {
            limparAviso();
            atualizarEnvioDoRewrite();
        });
        textoInicial.set(campoTexto, inicial);

        cartao.append(titulo, frase, explicacao, instrucao, campoTexto);
        return cartao;
    }

    function paragrafoComRotulo(rotulo, texto) {
        const paragrafo = document.createElement("p");
        const negrito = document.createElement("strong");
        negrito.textContent = rotulo;
        paragrafo.append(negrito, document.createTextNode(texto));
        return paragrafo;
    }

    function camposDoRewrite() {
        return [...campo("rw-problemas").querySelectorAll(".writing-rw-texto")];
    }

    // D26: só envia quando todas as frases estão preenchidas E diferentes do texto com que o campo começou.
    function atualizarEnvioDoRewrite() {
        const campos = camposDoRewrite();
        const vazios = campos.filter((c) => !c.value.trim()).length;
        const iguais = campos.filter((c) => c.value.trim() && c.value === textoInicial.get(c)).length;
        const botao = campo("rw-enviar");
        botao.disabled = vazios > 0 || iguais > 0 || campos.length === 0;
        campo("rw-dica").textContent = vazios ? "Preencha todas as frases para enviar."
            : iguais ? `Altere ${iguais === 1 ? "a frase que ainda está igual" : `as ${iguais} frases que ainda estão iguais`} para enviar.`
                : "";
    }

    async function enviarRewrite() {
        const campos = camposDoRewrite();
        const reescritas = campos.map((c) => ({ indice: Number(c.dataset.indice), texto: c.value }));
        const botao = campo("rw-enviar");
        botao.disabled = true;
        botao.textContent = "Avaliando…";
        limparAviso();
        campos.forEach((c) => { c.readOnly = true; });
        try {
            desenharRewrite(await apiWriting.enviarRewrite(rewriteId, reescritas));
        } catch (erro) {
            if (erro.codigo === "rewrite_concluido" || erro.codigo === "rodada_ja_enviada") {
                // A rodada já está gravada: não há texto a perder. Recarrega e avisa (depois da troca de tela).
                await abrirRewrite(rewriteId);
                avisar(erro.message);
            } else {
                // D23: nada foi gravado e a rodada não foi gasta. O erro fica na tela, e os textos, nos campos.
                avisar(`Não foi possível avaliar agora: ${erro.message} As suas reescritas continuam aqui: `
                    + "tente enviar de novo.");
                campos.forEach((c) => { c.readOnly = false; });
                atualizarEnvioDoRewrite();
            }
        } finally {
            botao.textContent = "Enviar reescritas";
        }
    }

    function itemDoHistorico(item) {
        const cartao = document.createElement("div");
        cartao.className = `writing-rw-item cat-${item.categoria}`;

        const cabecalho = document.createElement("div");
        cabecalho.className = "writing-rw-item-cabecalho";
        const titulo = document.createElement("span");
        titulo.textContent = `Rodada ${item.rodada} · ${NOMES_DAS_CATEGORIAS[item.categoria] ?? item.categoria}`;
        const veredito = document.createElement("span");
        veredito.className = item.avaliacao.melhorou ? "writing-veredito melhorou" : "writing-veredito nao";
        veredito.textContent = `${item.avaliacao.melhorou ? "✓ Melhorou" : "✗ Ainda não"} · ${item.avaliacao.nota}/10`;
        cabecalho.append(titulo, veredito);

        // Comparação calculada no servidor (difflib): removido riscado, adicionado destacado.
        const comparacao = document.createElement("p");
        comparacao.className = "writing-rw-comparacao";
        comparacao.append(...item.comparacao.map((pedaco) => {
            if (pedaco.tipo === "igual") return document.createTextNode(pedaco.texto);
            const marca = document.createElement(pedaco.tipo === "removido" ? "del" : "ins");
            marca.textContent = pedaco.texto;
            return marca;
        }));

        const comentario = document.createElement("p");
        comentario.className = "writing-rw-comentario";
        comentario.textContent = item.avaliacao.comentario;

        cartao.append(cabecalho, comparacao, comentario);
        return cartao;
    }

    // --- Eventos e ciclo de vida ---

    const salvarAoSair = () => {
        if (redacao?.estado === "rascunho" && !enviando && texto.value !== ultimoSalvo) {
            apiWriting.salvarAoSair(redacao.id, texto.value);
        }
    };
    const aoMudarVisibilidade = () => { if (document.visibilityState === "hidden") salvar(); };

    texto.addEventListener("input", aoDigitar);
    botaoEnviar.addEventListener("click", () => enviar());
    campo("sair").addEventListener("click", async () => {
        await salvar();
        await abrirInicio();
    });
    campo("voltar").addEventListener("click", abrirInicio);
    campo("res-voltar").addEventListener("click", abrirInicio);
    campo("avaliar").addEventListener("click", avaliarDeNovo);
    campo("res-rewrite").addEventListener("click", () => abrirRewrite(redacao.id));
    campo("rw-enviar").addEventListener("click", enviarRewrite);
    campo("rw-voltar").addEventListener("click", () => abrir(rewriteId));
    window.addEventListener("pagehide", salvarAoSair);           // fechar a aba ou recarregar
    document.addEventListener("visibilitychange", aoMudarVisibilidade);  // trocar de aba (e celular em segundo plano)

    const parametros = new URLSearchParams(location.search);
    const id = Number(parametros.get("redacao"));
    if (id) {
        carregarSituacao();  // o aviso de IA do editor vem daqui (o início carrega o seu sozinho)
        if (parametros.get("rewrite") === "1") abrirRewrite(id);
        else abrir(id);
    } else {
        abrirInicio();
    }

    // Limpeza (navegação para outra página pelo HTMX): salva o que falta e para timers e listeners globais.
    return () => {
        salvarAoSair();
        pararEditor();
        window.removeEventListener("pagehide", salvarAoSair);
        document.removeEventListener("visibilitychange", aoMudarVisibilidade);
    };
});
