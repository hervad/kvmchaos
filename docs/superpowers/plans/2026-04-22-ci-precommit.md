# CI and Pre-commit Hooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add pre-commit hooks (ruff lint + format) and a GitHub Actions CI pipeline (ruff + pytest on every push/PR) so quality gates run automatically without developer thought.

**Architecture:** Pre-commit uses the `pre-commit` framework with the official `ruff-pre-commit` hooks repo — no extra dev dependencies needed in pyproject.toml since `pre-commit` is installed as a uv tool. CI uses GitHub Actions with `astral-sh/setup-uv` and installs `libvirt-dev` from apt before running the test suite.

**Tech Stack:** `pre-commit` framework, `astral-sh/ruff-pre-commit`, GitHub Actions (`ubuntu-latest`), `astral-sh/setup-uv@v5`.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `.pre-commit-config.yaml` | Declare ruff lint and format hooks |
| Create | `.github/workflows/ci.yml` | GitHub Actions: lint + test on push/PR |

No pyproject.toml changes needed. `pre-commit` is installed as a uv tool, not a project dependency.

---

## Task 1: Pre-commit hooks

**Files:**
- Create: `.pre-commit-config.yaml`

- [ ] **Step 1: Install pre-commit as a uv tool**

```bash
uv tool install pre-commit
```

Expected: `pre-commit` available at `~/.local/bin/pre-commit` (already on your PATH).

- [ ] **Step 2: Create `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.11
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

- [ ] **Step 3: Install the hooks into the repo**

```bash
pre-commit install
```

Expected output:
```
pre-commit installed at .git/hooks/pre-commit
```

- [ ] **Step 4: Run hooks against all files to verify they pass clean**

```bash
pre-commit run --all-files
```

Expected: all hooks pass (ruff and ruff-format already clean).

- [ ] **Step 5: Commit**

```bash
git add .pre-commit-config.yaml
git commit -m "chore: add pre-commit hooks for ruff lint and format"
```

The commit itself will trigger the hooks — they must pass for the commit to succeed.

---

## Task 2: GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create the workflows directory**

```bash
mkdir -p .github/workflows
```

- [ ] **Step 2: Create `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Install system dependencies
        run: sudo apt-get install -y libvirt-dev pkg-config

      - name: Install uv
        uses: astral-sh/setup-uv@v5

      - name: Install project dependencies
        run: uv sync

      - name: Lint
        run: uv run ruff check

      - name: Format check
        run: uv run ruff format --check

      - name: Test
        run: uv run pytest -q
```

- [ ] **Step 3: Validate the YAML is well-formed**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo "YAML OK"
```

Expected: `YAML OK`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "chore: add GitHub Actions CI pipeline"
```

---

## Manual Verification Steps (after both tasks complete)

### Pre-commit

**Verify hooks are installed:**
```bash
cat .git/hooks/pre-commit   # must exist and be non-empty
```

**Verify hooks block bad code:**
```bash
# Introduce a lint violation
echo "import os,sys" >> src/kvmchaos/__init__.py
git add src/kvmchaos/__init__.py
git commit -m "test"
# Expected: commit blocked, ruff fixes the import and reports it
git checkout src/kvmchaos/__init__.py   # restore
```

**Verify hooks pass on clean code:**
```bash
git commit --allow-empty -m "chore: test clean commit"
# Expected: hooks run and pass, commit succeeds
```

### GitHub Actions CI

**Push to main and observe:**
```bash
git push
# Then: https://github.com/<your-repo>/actions
# Expected: CI workflow triggered, all steps green
```

**Verify CI catches a lint error (optional):**
```bash
git checkout -b test-ci-failure
echo "x=1+1" >> src/kvmchaos/__init__.py   # missing whitespace, ruff will catch it
git add src/kvmchaos/__init__.py
git commit -m "test: introduce lint error" --no-verify   # bypass pre-commit for this test
git push -u origin test-ci-failure
# Open a PR — CI should fail on the Lint step
git checkout main
git branch -D test-ci-failure
git push origin --delete test-ci-failure
```
