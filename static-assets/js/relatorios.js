document.addEventListener('DOMContentLoaded', function() {
            // Botão Novo Relatório
            document.getElementById('btnGerarRelatorio').addEventListener('click', function() {
               alert('Abrindo formulário para novo relatório...');
            });
            
            // Botão Filtrar
            document.getElementById('btnFiltrar').addEventListener('click', function() {
               const tipo = document.getElementById('tipoRelatorio').value;
               const periodo = document.getElementById('periodoRelatorio').value;
               alert(`Filtrando relatórios: ${tipo} - ${periodo}`);
            });
            
            // Botão Exportar CSV
            document.getElementById('btnExportarCSV').addEventListener('click', function() {
               alert('Exportando relatórios para CSV...');
            });
            
            // Botão Exportar PDF
            document.getElementById('btnExportarPDF').addEventListener('click', function() {
               alert('Exportando relatórios para PDF...');
            });
            
            // Controle de datas (período personalizado)
            document.getElementById('periodoRelatorio').addEventListener('change', function() {
               const dataInicio = document.getElementById('dataInicio');
               const dataFim = document.getElementById('dataFim');
               if (this.value === 'personalizado') {
                  dataInicio.disabled = false;
                  dataFim.disabled = false;
                  dataInicio.style.opacity = '1';
                  dataFim.style.opacity = '1';
               } else {
                  dataInicio.disabled = true;
                  dataFim.disabled = true;
                  dataInicio.style.opacity = '0.5';
                  dataFim.style.opacity = '0.5';
                  dataInicio.value = '';
                  dataFim.value = '';
               }
            });
            
            // Inicializa com campos de data desabilitados
            document.getElementById('dataInicio').disabled = true;
            document.getElementById('dataFim').disabled = true;
            document.getElementById('dataInicio').style.opacity = '0.5';
            document.getElementById('dataFim').style.opacity = '0.5';
            
            // Ações dos botões de visualização e download
            document.querySelectorAll('.btn-outline-primary, .btn-outline-secondary').forEach(btn => {
               btn.addEventListener('click', function(e) {
                  e.stopPropagation();
                  if (this.classList.contains('btn-outline-primary')) {
                     alert('Visualizando relatório...');
                  } else if (this.classList.contains('btn-outline-secondary')) {
                     alert('Baixando relatório...');
                  }
               });
            });
         });