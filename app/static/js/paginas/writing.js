// Página do Writing Challenge (templates/paginas/writing.html), Membro 3. Três telas na mesma página:
//   início (categorias, aviso de IA, cota, redações recentes) → editor (contador, timer, autosave) → fim (enviada).
// A redação aberta fica na URL (/writing?redacao=7): recarregar a página volta ao editor com o texto e o tempo.
// Conteúdo do servidor (tema, texto, nomes) entra só com textContent/value, nunca innerHTML.
import { criarAvisoIA } from "../componentes/aviso-ia.js";
import { criarEstadoVazio } from "../componentes/estado-vazio.js";
import { api } from "../nucleo/api.js";
import { apiWriting } from "../nucleo/api-writing.js";
import { contagemRegressiva, formatarTempo, mostrarErro } from "../nucleo/interface.js";
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
        ["inicio", "editor", "fim"].map((nome) => [nome, raiz.querySelector(`[data-tela="${nome}"]`)]),
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
        Object.entries(telas).forEach(([chave, tela]) => { tela.hidden = chave !== nome; });
    }

    function definirUrl(id) {
        history.replaceState(history.state, "", id ? `/writing?redacao=${id}` : "/writing");
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
        try {
            abrirEditor(await apiWriting.criar(categoria));
        } catch (erro) {
            mostrarErro(erro.message);  // ex.: 429, com o tempo até a cota renovar
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
        botao.append(nome, estado, detalhe);
        botao.addEventListener("click", () => abrir(item.id));
        return botao;
    }

    async function abrir(id) {
        let dados;
        try {
            dados = await apiWriting.obter(id);
        } catch (erro) {
            mostrarErro(erro.message);
            await abrirInicio();
            return;
        }
        if (dados.estado === "rascunho") abrirEditor(dados);
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
        clearTimeout(temporizador);
        botaoEnviar.disabled = true;
        botaoEnviar.textContent = "Enviando…";
        texto.readOnly = true;
        try {
            if (salvando) await salvando.catch(() => {});
            const enviada = await apiWriting.enviar(redacao.id, texto.value);
            pararEditor();
            mostrarEnviada(enviada);
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
            } else {
                mostrarErro(erro.message);
                texto.readOnly = false;  // o texto continua na tela; dá para tentar de novo
            }
        } finally {
            enviando = false;
            botaoEnviar.textContent = "Enviar redação";
            if (redacao?.estado === "rascunho" && !telas.editor.hidden) atualizarContador();
        }
    }

    function mostrarEnviada(dados) {
        redacao = dados;
        definirUrl(dados.id);
        mostrarFim(
            "Redação enviada",
            `${dados.categoria_nome} · ${plural(dados.palavras, "palavra", "palavras")}`,
            (dados.usou_ultimo_salvamento ? "O tempo tinha acabado: foi enviado o último texto salvo. " : "")
            + "A correção por IA ainda não está disponível nesta versão.",
        );
    }

    function mostrarFim(titulo, textoPrincipal, aviso) {
        campo("fim-titulo").textContent = titulo;
        campo("fim-texto").textContent = textoPrincipal;
        campo("fim-aviso").textContent = aviso;
        mostrarTela("fim");
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
    window.addEventListener("pagehide", salvarAoSair);           // fechar a aba ou recarregar
    document.addEventListener("visibilitychange", aoMudarVisibilidade);  // trocar de aba (e celular em segundo plano)

    const id = Number(new URLSearchParams(location.search).get("redacao"));
    if (id) {
        carregarSituacao();  // o aviso de IA do editor vem daqui (o início carrega o seu sozinho)
        abrir(id);
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
