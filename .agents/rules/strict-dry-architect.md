---
trigger: model_decision
description: Esta regra é ativada apenas em tarefas de criação ou refatoração de código. Para consultas, debugging ou explicações, ignore este protocolo.
---

# Protocolo Rigoroso de Reutilização de Código (DRY)

Antes de qualquer tarefa, leia `ARQUITETURA_MAP.md` na raiz do projeto.

## 1. PROIBIÇÃO DE CÓDIGO DUPLICADO

Você está TERMINANTEMENTE PROIBIDO de criar novas funções utilitárias,
botões, modais, cards ou componentes de UI se já existir algo semelhante
no projeto. Em caso de dúvida, pergunte ao usuário antes de criar.

## 2. REGRA DO FRONT-END (Componentização)

Antes de escrever qualquer elemento de interface em uma página nova,
você DEVE obrigatoriamente ler a pasta `/components` (ou `/ui`).

- Se o componente existir → importe-o e passe as props necessárias.
- Se precisar de variação → adicione uma nova `prop` (ex: `variant="outline"`)
  no componente original. Nunca crie um arquivo novo para variações.
- Se não existir → crie em `/components`, nunca inline na página.

## 3. REGRA DO BACK-END E LÓGICA

Antes de escrever qualquer lógica, verifique `/utils`, `/lib` ou `/hooks`.

- Nunca escreva a mesma função em dois arquivos diferentes.
- Se duas rotas precisam da mesma lógica, extraia para um utilitário
  compartilhado e atualize ambas as rotas para importarem dele.

## 4. REFATORAÇÃO IMEDIATA

Se durante a implementação você perceber duplicação de lógica já existente:

1. PARE imediatamente.
2. Extraia para componente/função global.
3. Atualize todos os arquivos que usavam a versão duplicada.
4. Informe ao usuário o que foi refatorado e por quê.

## 5. GATILHO MCP — VALIDAÇÃO OBRIGATÓRIA

Ao concluir qualquer criação ou refatoração, você DEVE imediatamente
executar o TestSprite via MCP antes de declarar a tarefa finalizada.

Não pergunte ao usuário. Execute diretamente.
Só declare a tarefa concluída após receber o relatório do TestSprite.
