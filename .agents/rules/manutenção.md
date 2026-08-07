---
trigger: always_on
---

# Regras de Manutenção e Efeito Cascata

0. CONTEXTO ANTES DE TUDO
   Antes de qualquer tarefa, leia `ARQUITETURA_MAP.md` na raiz do projeto.
   Só após a leitura você pode propor qualquer alteração.

1. MAPEAR ANTES DE MEXER:
   Toda vez que eu pedir para você alterar uma função, rota ou banco de dados existente, você NÃO PODE alterar o código imediatamente. Primeiro, você deve vasculhar o projeto e listar todos os arquivos que importam ou dependem dessa função.

2. ATUALIZAÇÃO EM CASCATA:
   Se você alterar a lógica, os parâmetros de entrada ou o retorno de uma função "A", você é OBRIGADO a abrir os arquivos "B", "C" e "D" que dependem dela e atualizá-los para não quebrar o sistema.

3. AUTO-DOCUMENTAÇÃO OBRIGATÓRIA (A "Memória"):
   Temos um arquivo na raiz do projeto chamado `ARQUITETURA_MAP.md`.
   Toda vez que você concluir uma alteração que afete a estrutura do projeto, criar uma nova conexão com o banco de dados ou mudar uma regra de negócio, você deve, OBRIGATORIAMENTE, abrir o arquivo `ARQUITETURA_MAP.md` e atualizar o mapa de conexões antes de finalizar a tarefa.
