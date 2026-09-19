# Cursor optimization rules

Follow these rules strictly when interacting with this repository to avoid wasting context and token budget.

## 1. Minimal context principle

- Do not read the entire repository to answer a narrow question.
- Work only with the files provided via `@files`.
- If additional context is required, explicitly ask the user for the relevant paths.

## 2. Direct answers and incremental code changes

- Keep responses concise and actionable.
- Prefer incremental code edits over rewriting broad files.
- If only a small section changed, provide the minimal patch instead of restating the whole file.
- Remove long docstrings and verbose comments from code examples shown in chat unless explicitly requested.

## 3. FastAPI guidance

- Avoid broad architecture refactors unless the task explicitly targets architecture.
- Focus on narrow fixes such as Pydantic typing issues or dependency injection (`Depends`) problems without generating unnecessary boilerplate.
- Prefer surgical changes over structural rewrites.
