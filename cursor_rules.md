# Instruções Otimizadas para o Cursor (Economia de Tokens)

Siga estas diretrizes estritas ao interagir com este repositório para evitar desperdício de contexto e tokens.

## 1. Princípio do Contexto Mínimo
*   **Nunca leia o repositório inteiro** para responder a perguntas pontuais.
*   Trabalhe estritamente com os arquivos fornecidos via `@arquivos`.
*   Se precisar de contexto adicional, peça explicitamente para o usuário fornecer os caminhos.

## 2. Respostas Diretas e Código Incremental
*   **Sem explicações prolixas:** Vá direto à solução ou correção.
*   **Código Incremental:** Não reescreva arquivos inteiros do FastAPI se apenas uma rota ou função mudou. Forneça apenas o trecho alterado ou um patch claro (ex: `// ... código existente ...`).
*   **Remova Docstrings e Comentários Longos** em códigos de exemplo expostos no chat, a menos que solicitado.

## 3. Gerenciamento do FastAPI
*   Evite sugerir refatorações completas de arquitetura (como mudar de instâncias simples para APIRouter) a menos que a tarefa seja explicitamente sobre arquitetura.
*   Foque em correções rápidas de tipagem do Pydantic ou injeção de dependência (`Depends`) sem gerar boilerplate desnecessário.