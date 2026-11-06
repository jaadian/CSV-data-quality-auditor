# Git history and publishing

The repository contains a **real, short Git history** starting from the supplied v1.1.0 snapshot. Earlier development happened outside this Git repository, so its previous commits cannot be reconstructed honestly from a ZIP. The commits after the import record changes made during this review.

## Review the history

```bash
git log --oneline --decorate
git show --stat HEAD
```

The initial import is a snapshot, **not** a claim that all source files were written in one sitting. Later commits correspond to actual changes.

## Before publishing

1. Open `docs/learning_log.md` and personally reproduce at least one regression test. Fill in the personal reflections section based on what you observed.
2. Replace `<your-username>` in `README.md` with your real GitHub username.
3. Run `python -m pip install -e ".[dev]"`, `pytest`, `ruff check .`, `ruff format --check .`, and `mypy`.
4. Download and generate the datasets, then run `python scripts/verify_datasets.py`. The raw datasets are intentionally excluded from Git.
5. Review `git status`, then publish only when you are happy with the results.

## Set up your identity for future commits

```bash
git config user.name "Your Name"
git config user.email "your-verified-github-email@example.com"
```

These settings affect **future** commits. Do not rewrite earlier commits just to make them appear to have been authored by somebody else.

## Push this existing repository

Create an empty GitHub repository named `csv-data-quality-auditor` (do not initialize it with a README), then run:

```bash
git remote add origin <your-repository-SSH-or-HTTPS-URL>
git push -u origin main
```

Uploading individual files through GitHub's web interface will **not** preserve the `.git` history in this archive. Extract the ZIP and use Git from the extracted directory instead.
