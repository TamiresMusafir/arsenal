# Arsenal

## Sobre o projeto

O **Arsenal** é um sistema desenvolvido em **Python** com **Django** para automatizar o processo de depuração de orçamentos.

O objetivo é reduzir o trabalho manual realizado na análise de e-mails e anexos, organizando automaticamente as informações em planilhas já existentes. Futuramente, o sistema contará com funcionalidades como:

- Leitura automática de e-mails;
- Extração de informações dos anexos;
- Organização e validação dos dados;
- Preenchimento de planilhas modelo;
- Histórico das execuções;
- Dashboard para acompanhamento do processo.

---

# Tecnologias

- Python 3
- Django
- Bootstrap (interface)
- HTML
- CSS
- JavaScript

---

# Como executar o projeto

## 1. Entrar na pasta do projeto

```bash
cd arsenal
```

## 2. Criar o ambiente virtual

```bash
python3 -m venv .venv
```

O ambiente virtual isola as dependências do projeto, evitando conflitos com outros projetos Python instalados na máquina.
Se já criado, pule para o passo 3.

## 3. Ativar o ambiente virtual

```bash
source .venv/bin/activate
```

Após a ativação, o terminal deverá exibir algo semelhante a:

```text
(.venv) usuario@maquina:~/arsenal$
```

## 4. Instalar o Django

```bash
pip install django
```

Esse comando instala o framework Django dentro do ambiente virtual.

## 5. Criar o projeto Django

```bash
django-admin startproject config .
```

Esse comando cria a estrutura inicial do projeto.

- `config` é o nome da pasta que armazenará as configurações do projeto.
- O `.` indica que o projeto será criado na pasta atual, evitando a criação de uma pasta adicional.

Após esse comando, a estrutura será semelhante a:

```text
arsenal/
│
├── .venv/
├── config/
├── manage.py
```

## 6. Executar as migrações

```bash
python manage.py migrate
```

Esse comando cria as tabelas iniciais do banco de dados utilizadas pelo Django, como usuários, permissões, sessões e outras estruturas internas.

Por padrão, será criado automaticamente um banco SQLite chamado:

```text
db.sqlite3
```

na raiz do projeto.

## 7. Iniciar o servidor de desenvolvimento

```bash
python manage.py runserver
```

Esse comando inicia o **servidor de desenvolvimento** do Django. Ele é utilizado durante a criação e os testes da aplicação.

Após executá-lo, o terminal exibirá uma mensagem semelhante a:

```text
Starting development server at http://127.0.0.1:8000/
```

Abra o navegador e acesse:

```text
http://127.0.0.1:8000/
```

Se tudo estiver configurado corretamente, será exibida a página padrão do Django, indicando que o projeto foi criado com sucesso.

---

## Próximos passos

Após concluir essa configuração inicial, o próximo passo será criar as aplicações (Apps) do Django responsáveis por cada módulo do sistema, como leitura de e-mails, processamento de planilhas, dashboard e gerenciamento de usuários.
