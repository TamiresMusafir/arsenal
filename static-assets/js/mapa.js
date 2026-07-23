// mapa.js - Gerenciamento de upload e visualização de dados
document.addEventListener('DOMContentLoaded', function() {
    // Elementos do DOM
    const elementos = {
        btnBaixarModelo: document.getElementById('btnBaixarModelo'),
        btnUploadArquivo: document.getElementById('btnUploadArquivo'),
        btnLimparTabela: document.getElementById('btnLimparTabela'),
        inputArquivo: document.getElementById('inputArquivo'),
        areaTabela: document.getElementById('areaTabela'),
        cabecalhoTabela: document.getElementById('cabecalhoTabela'),
        corpoTabela: document.getElementById('corpoTabela'),
        estadoVazio: document.getElementById('estadoVazio'),
        infoArquivo: document.getElementById('infoArquivo'),
        mensagemStatus: document.getElementById('mensagemStatus'),
        progressBar: document.getElementById('progressBar'),
        progressBarInner: document.querySelector('#progressBar .progress-bar'),
        nomeArquivo: document.getElementById('nomeArquivo'),
        totalLinhas: document.getElementById('totalLinhas'),
        totalColunas: document.getElementById('totalColunas')
    };
    
    // Configuração
    const config = {
        baseUrl: window.location.pathname.replace(/\/$/, ''),
        formatosAceitos: ['.csv', '.xls', '.xlsx', '.ods'],
        tempoExibicaoMensagem: 5000,
        tempoExibicaoProgresso: 1500
    };
    
    // Inicializar eventos
    inicializarEventos(elementos, config);
});

function inicializarEventos(el, cfg) {
    // Download do modelo base
    el.btnBaixarModelo.addEventListener('click', () => {
        window.location.href = cfg.baseUrl + '/baixar-modelo-base/';
    });
    
    // Abrir seletor de arquivos
    el.btnUploadArquivo.addEventListener('click', () => {
        el.inputArquivo.click();
    });
    
    // Processar upload
    el.inputArquivo.addEventListener('change', async (e) => {
        await processarUpload(e.target.files, el, cfg);
    });
    
    // Limpar tabela
    el.btnLimparTabela.addEventListener('click', () => {
        limparTabela(el);
    });
    
    // Drag and drop
    inicializarDragAndDrop(el, cfg);
}

async function processarUpload(arquivos, el, cfg) {
    if (arquivos.length === 0) return;
    
    mostrarProgresso(el.progressBar, el.progressBarInner, true);
    
    for (let i = 0; i < arquivos.length; i++) {
        const arquivo = arquivos[i];
        atualizarProgresso(el.progressBarInner, (i / arquivos.length) * 100);
        
        const formData = new FormData();
        formData.append('arquivo', arquivo);
        
        try {
            const response = await fetch(cfg.baseUrl + '/processar-upload/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            
            const data = await response.json();
            
            if (data.success) {
                exibirDados(data.dados, el);
                mostrarMensagem(el.mensagemStatus, 'success', 
                    `<i class="fa-solid fa-circle-check me-2"></i>
                     Arquivo "${arquivo.name}" processado com sucesso! 
                     (${data.dados.total_linhas} linhas, ${data.dados.total_colunas} colunas)`);
            } else {
                console.error('Erro detalhado:', data);
                mostrarMensagem(el.mensagemStatus, 'danger', 
                    `<i class="fa-solid fa-circle-exclamation me-2"></i>
                     Erro ao processar "${arquivo.name}": ${data.error}`);
            }
        } catch (error) {
            console.error('Erro na requisição:', error);
            mostrarMensagem(el.mensagemStatus, 'danger', 
                `<i class="fa-solid fa-triangle-exclamation me-2"></i>
                 Erro ao enviar "${arquivo.name}": ${error.message}`);
        }
        
        atualizarProgresso(el.progressBarInner, ((i + 1) / arquivos.length) * 100);
    }
    
    setTimeout(() => {
        mostrarProgresso(el.progressBar, el.progressBarInner, false);
    }, cfg.tempoExibicaoProgresso);
    
    // Limpar input
    el.inputArquivo.value = '';
}

function exibirDados(dados, el) {
    // Limpar tabela
    el.cabecalhoTabela.innerHTML = '';
    el.corpoTabela.innerHTML = '';
    
    // Cabeçalho com índice
    const thIndice = document.createElement('th');
    thIndice.textContent = '#';
    thIndice.style.width = '50px';
    thIndice.className = 'text-center';
    el.cabecalhoTabela.appendChild(thIndice);
    
    // Colunas do arquivo
    dados.colunas.forEach(coluna => {
        const th = document.createElement('th');
        th.textContent = coluna || 'Coluna sem nome';
        th.className = 'text-nowrap';
        el.cabecalhoTabela.appendChild(th);
    });
    
    // Linhas com dados (limitar a 1000 linhas para performance)
    const maxLinhas = 1000;
    const linhasParaExibir = dados.linhas.slice(0, maxLinhas);
    
    linhasParaExibir.forEach((linha, index) => {
        const tr = document.createElement('tr');
        
        // Índice da linha
        const tdIndice = document.createElement('td');
        tdIndice.textContent = index + 1;
        tdIndice.className = 'text-center fw-bold';
        tdIndice.style.width = '50px';
        tr.appendChild(tdIndice);
        
        // Dados
        linha.forEach(celula => {
            const td = document.createElement('td');
            // Tratar valores nulos/undefined
            if (celula === null || celula === undefined || celula === 'None') {
                td.textContent = '';
                td.className = 'text-muted font-italic';
            } else {
                td.textContent = typeof celula === 'object' ? JSON.stringify(celula) : String(celula);
            }
            tr.appendChild(td);
        });
        
        el.corpoTabela.appendChild(tr);
    });
    
    // Mostrar aviso se houver mais linhas
    if (dados.linhas.length > maxLinhas) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = dados.colunas.length + 1;
        td.className = 'text-center text-warning bg-light';
        td.textContent = `⚠️ Exibindo apenas as primeiras ${maxLinhas} linhas de ${dados.linhas.length} total`;
        tr.appendChild(td);
        el.corpoTabela.appendChild(tr);
    }
    
    // Atualizar informações
    el.nomeArquivo.innerHTML = `<i class="fa-solid fa-file me-1"></i> ${dados.nome_arquivo}`;
    el.totalLinhas.innerHTML = `<i class="fa-solid fa-list me-1"></i> Linhas: ${dados.total_linhas}`;
    el.totalColunas.innerHTML = `<i class="fa-solid fa-table-columns me-1"></i> Colunas: ${dados.total_colunas}`;
    
    // Mostrar elementos
    el.areaTabela.style.display = 'block';
    el.infoArquivo.style.display = 'block';
    el.estadoVazio.style.display = 'none';
    el.btnLimparTabela.style.display = 'inline-block';
}

function limparTabela(el) {
    el.cabecalhoTabela.innerHTML = '';
    el.corpoTabela.innerHTML = '';
    el.areaTabela.style.display = 'none';
    el.infoArquivo.style.display = 'none';
    el.estadoVazio.style.display = 'block';
    el.btnLimparTabela.style.display = 'none';
    el.mensagemStatus.style.display = 'none';
}

function mostrarProgresso(bar, inner, mostrar) {
    if (mostrar) {
        bar.style.display = 'block';
        inner.style.width = '0%';
        inner.textContent = '0%';
        inner.setAttribute('aria-valuenow', 0);
    } else {
        bar.style.display = 'none';
        inner.style.width = '0%';
        inner.textContent = '0%';
        inner.setAttribute('aria-valuenow', 0);
    }
}

function atualizarProgresso(inner, porcentagem) {
    const rounded = Math.round(porcentagem);
    inner.style.width = rounded + '%';
    inner.textContent = rounded + '%';
    inner.setAttribute('aria-valuenow', rounded);
}

function mostrarMensagem(elemento, tipo, texto) {
    elemento.className = `alert alert-${tipo} alert-dismissible fade show`;
    elemento.innerHTML = `
        ${texto}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    elemento.style.display = 'block';
    
    // Auto-fechar após 5 segundos
    setTimeout(() => {
        if (elemento.style.display !== 'none') {
            elemento.style.display = 'none';
        }
    }, 5000);
}

function inicializarDragAndDrop(el, cfg) {
    const section = document.querySelector('section:last-child');
    if (!section) return;
    
    section.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.stopPropagation();
        section.style.border = '2px dashed #0d6efd';
        section.style.backgroundColor = '#f8f9fa';
    });
    
    section.addEventListener('dragleave', (e) => {
        e.preventDefault();
        e.stopPropagation();
        section.style.border = '';
        section.style.backgroundColor = '';
    });
    
    section.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        section.style.border = '';
        section.style.backgroundColor = '';
        
        const arquivos = e.dataTransfer.files;
        if (arquivos.length > 0) {
            const arquivosValidos = Array.from(arquivos).filter(arquivo => {
                const extensao = '.' + arquivo.name.split('.').pop().toLowerCase();
                return cfg.formatosAceitos.includes(extensao);
            });
            
            if (arquivosValidos.length > 0) {
                const dt = new DataTransfer();
                arquivosValidos.forEach(arquivo => dt.items.add(arquivo));
                el.inputArquivo.files = dt.files;
                el.inputArquivo.dispatchEvent(new Event('change'));
            } else {
                mostrarMensagem(el.mensagemStatus, 'warning', 
                    `<i class="fa-solid fa-triangle-exclamation me-2"></i>
                     Por favor, arraste apenas arquivos nos formatos: ${cfg.formatosAceitos.join(', ')}`);
            }
        }
    });
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
