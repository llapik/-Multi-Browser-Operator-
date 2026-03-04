# CLAUDE.md — Multi-Browser Operator

This file provides guidance for AI assistants (Claude, Copilot, etc.) working in this repository.

---

## Project Overview

**Multi-Browser Operator** is a project intended to manage and control multiple browser instances. Based on the repository name, the likely use cases include:

- Web automation across multiple browsers simultaneously
- Cross-browser testing orchestration
- Browser-based scraping or monitoring at scale
- Parallel browser session management

> **Current status:** The project is in its initial setup phase. Only `LICENSE` and `README.md` exist. No source code has been written yet.

---

## Repository Layout

```
-Multi-Browser-Operator-/
├── CLAUDE.md          # This file — AI assistant guidance
├── LICENSE            # MIT License (Copyright 2026 llapik)
└── README.md          # Project description (stub)
```

As the project grows, the expected structure should follow the conventions below.

---

## Development Conventions

### Language & Tooling

The language and framework have not yet been decided. When they are chosen, update this section with:

- Primary language (e.g., TypeScript, Python, Go)
- Package manager (e.g., npm/pnpm, pip, go mod)
- Formatter and linter config (e.g., ESLint + Prettier, ruff, gofmt)
- Test framework (e.g., Jest, pytest, testing)

### Code Style (General Defaults)

Until project-specific tooling is configured, follow these defaults:

- Prefer explicit over implicit; avoid magic values — use named constants.
- Keep functions small and single-purpose.
- Validate inputs at system boundaries (user input, external APIs); trust internal code.
- Avoid premature abstractions — three similar lines of code is better than a speculative helper.
- Do not add docstrings, comments, or type annotations to unchanged code.
- Only add comments where logic is not self-evident.

### Error Handling

- Handle errors at the boundary where they can be meaningfully acted on.
- Do not add error handling for scenarios that cannot happen.
- Propagate errors upward with enough context to diagnose the root cause.

### Security

- Never commit secrets, credentials, API keys, or tokens.
- Add `.env` and secrets files to `.gitignore` immediately when introduced.
- Validate and sanitize all external input before use.
- Avoid shell injection, XSS, SQL injection, and other OWASP Top 10 vulnerabilities.

---

## Git Workflow

### Branches

| Branch pattern | Purpose |
|---|---|
| `master` | Stable, production-ready code |
| `claude/<task-id>` | AI-assisted development branches |
| `feature/<name>` | Human-driven feature development |
| `fix/<name>` | Bug fixes |

### Commit Messages

Use short, imperative commit messages:

```
Add multi-browser session manager
Fix race condition in tab lifecycle
Refactor browser pool initialization
```

- Present tense, imperative mood ("Add", not "Added" or "Adds")
- 72 characters max for the subject line
- Add a body (separated by blank line) only when context is non-obvious

### Push Rules

- Never force-push to `master`.
- Claude branches must follow the pattern `claude/<task-id>` — the branch must start with `claude/`.
- Always push with `-u` to set upstream tracking: `git push -u origin <branch>`.

---

## Working with AI Assistants

### What to do

- Read existing code before suggesting modifications.
- Make only the changes directly requested or clearly necessary.
- Keep solutions minimal — avoid adding features, refactoring, or "improvements" beyond scope.
- When taking irreversible actions (deleting files, force-pushing, dropping data), confirm with the user first.

### What to avoid

- Do not create files unless absolutely necessary.
- Do not add backwards-compatibility shims for removed code.
- Do not over-engineer for hypothetical future requirements.
- Do not add CI/CD steps, feature flags, or environment abstractions prematurely.

---

## Getting Started (Placeholder)

This section will be updated once the project stack is chosen. Expected steps:

```bash
# Clone the repository
git clone <repo-url>
cd -Multi-Browser-Operator-

# Install dependencies (TBD based on stack)
# <package manager install command>

# Run tests (TBD)
# <test command>

# Run the project (TBD)
# <start command>
```

---

## License

MIT — see [LICENSE](./LICENSE) for full terms.
