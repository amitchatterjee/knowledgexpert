# Copilot Instructions for knowledgexpert

Scope: This file applies only to this repository.

## Coding Style
- Keep implementation lean and non-defensive.
- Assume required packages are installed and the runtime environment is compatible.
- Do not add compatibility fallbacks for missing dependencies.
- Avoid unnecessary null checks and broad safety wrappers in core modules.
- Rely on CLI/config layers for guardrails and input validation.
- Prefer concise code; avoid code bloat from redundant exception handling.

## Planning vs Execution
- When drafting or discussing a plan, do not execute implementation steps unless explicitly requested.
