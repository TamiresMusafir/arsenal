document.addEventListener('DOMContentLoaded', function() {
            // Botão para baixar modelo base
            document.getElementById('btnBaixarModelo').addEventListener('click', function() {
               // Cria um arquivo CSV de exemplo
               const headers = 'Fornecedor,Produto,Preço Unitário,Quantidade,Total\n';
               const dados = 'Fornecedor A,Produto 1,100,10,1000\nFornecedor B,Produto 2,150,5,750\nFornecedor C,Produto 3,200,8,1600\n';
               const conteudo = headers + dados;
               
               const blob = new Blob([conteudo], { type: 'text/csv;charset=utf-8;' });
               const link = document.createElement('a');
               link.href = URL.createObjectURL(blob);
               link.download = 'modelo_mapa_comparativo.csv';
               document.body.appendChild(link);
               link.click();
               document.body.removeChild(link);
               URL.revokeObjectURL(link.href);
            });
            
            // Botão para upload de arquivos
            document.getElementById('btnUploadArquivo').addEventListener('click', function() {
               document.getElementById('inputArquivo').click();
            });
            
            // Quando selecionar arquivos
            document.getElementById('inputArquivo').addEventListener('change', function(e) {
               const arquivos = this.files;
               
               if (arquivos.length > 0) {
                  let mensagem = 'Arquivos selecionados:\n';
                  for (let i = 0; i < arquivos.length; i++) {
                     mensagem += `- ${arquivos[i].name}\n`;
                  }
                  alert(mensagem);
                  
                  // Exemplo de processamento do primeiro arquivo
                  const arquivo = arquivos[0];
                  if (arquivo) {
                     const leitor = new FileReader();
                     leitor.onload = function(evento) {
                        const conteudo = evento.target.result;
                        
                        // Processamento básico do CSV
                        const linhas = conteudo.split('\n');
                        if (linhas.length > 0) {
                           const cabecalho = linhas[0].split(',');
                           const dados = linhas.slice(1).filter(linha => linha.trim() !== '');
                           
                           // Monta a tabela
                           const cabecalhoHtml = cabecalho.map(col => `<th>${col.trim()}</th>`).join('');
                           document.getElementById('cabecalhoTabela').innerHTML = cabecalhoHtml;
                           
                           const corpoHtml = dados.map(linha => {
                              const colunas = linha.split(',');
                              return `<tr>${colunas.map(col => `<td>${col.trim()}</td>`).join('')}</tr>`;
                           }).join('');
                           document.getElementById('corpoTabela').innerHTML = corpoHtml;
                           
                           // Mostra a tabela
                           document.getElementById('areaTabela').style.display = 'block';
                        }
                     };
                     leitor.readAsText(arquivo);
                  }
                  
                  // Limpa o input para permitir selecionar o mesmo arquivo novamente
                  this.value = '';
               }
            });
         });