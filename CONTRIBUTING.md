# Contributing to Open News

Thank you for your interest in contributing to `open-news`! This document outlines the process for reporting issues, suggesting improvements, and submitting code changes.

## Table of Contents
- [Code of Conduct](#code-of-conduct)
- [How to Report Issues](#how-to-report-issues)
- [Suggesting Enhancements](#suggesting-enhancements)
- [Development Setup](#development-setup)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Submitting Pull Requests](#submitting-pull-requests)
- [Questions?](#questions)

## Code of Conduct
We expect all contributors to be respectful and constructive. Harassment, hate speech, or any form of abuse will not be tolerated.

## How to Report Issues
If you find a bug, please open a GitHub issue with the following:

- **Clear title** describing the problem.
- **Steps to reproduce** (include URLs, code snippets, and the exact command you ran).
- **Expected vs. actual behaviour**.
- **Environment** (Python version, OS, package versions from `pip list`).
- **Logs** (if any, with `DEBUG` logging enabled).

## Suggesting Enhancements
We welcome ideas for new features or improvements. Before opening an issue, search existing issues to avoid duplicates.

In your suggestion, explain:
- What problem it solves.
- How you envision the API or behaviour.
- Any alternatives you’ve considered.

## Development Setup
1. **Fork the repository** and clone it locally.
2. **Set up a virtual environment** (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate      # Linux/macOS
   venv\Scripts\activate         # Windows
   ```
3. **Install the package in editable mode with the development dependencies**:
   ```bash
   python -m pip install -e ".[dev]"
   ```
   The current `[dev]` extra provides pytest, coverage, VCR, HTTP mocking, and tox.

## Coding Standards
- **Formatting**: Keep changes consistent with the surrounding code style.
- **Linting**: Review changed code for import, syntax, and style issues before opening a PR.
- **Type hints**: Add type annotations to new public functions.
- **Docstrings**: Follow Google style or NumPy style; include parameters, returns, and exceptions.

## Testing
- We use `pytest` for unit tests.
- **All new features must include tests**. Bug fixes should include a regression test.
- Mock external HTTP requests using `respx`, `pytest-vcr`, or the repository's existing fixtures to avoid hitting real URLs during tests.
- Run the test suite locally:
  ```bash
  pytest tests/
  ```
- Ensure test coverage does not decrease. If possible, run:
  ```bash
   python -m pytest --cov=open_news tests/
  ```

## Submitting Pull Requests
1. **Create a new branch** from `main` with a descriptive name (`fix-google-date-parsing` or `add-timeout-option`).
2. **Make your changes**, following the coding standards.
3. **Add or update tests** and documentation (README, docstrings).
4. **Run the test suite** and ensure it passes.
5. **Push your branch** and open a Pull Request (PR) against the `main` branch.
6. In the PR description, include:
   - What the PR does.
   - Any related issue numbers (e.g., "Fixes #42").
   - Screenshots or logs if relevant.
7. A maintainer will review your PR. Please be responsive to feedback.

### PR Checklist
- [ ] Code is formatted with Black.
- [ ] Linter (Ruff) reports no errors.
- [ ] Type hints added and `mypy` passes.
- [ ] New tests are included and pass.
- [ ] Documentation updated (if applicable).
- [ ] PR targets `main` and has no merge conflicts.

## Questions?
If you’re unsure about anything, feel free to open a Discussion or ask in an existing issue thread. We’re happy to help you get started!

**Thank you for helping make `open-news` better!** 🚀
