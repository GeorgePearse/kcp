# Building and publishing this documentation

The site uses MkDocs Material. Its source is in `docs/`, with navigation in `mkdocs.yml` and pinned top-level documentation dependencies in `requirements-docs.txt`.

## Local preview and checks

From the repository root:

```sh
python3 -m venv .venv-docs
.venv-docs/bin/pip install -r requirements-docs.txt
.venv-docs/bin/mkdocs build --strict
.venv-docs/bin/mkdocs serve
```

Open the local address printed by MkDocs. The generated `site/` directory and virtual environment are ignored by Git. The strict build rejects documentation warnings, including unresolved internal page links.

The report at `docs/reports/transport-v2.html` is a frozen copy of the October 10, 2026 benchmark artifact. It works without external assets. Editing prose or rebuilding the site does not regenerate or rerun that experiment.

## GitHub Pages

The public site is [georgepearse.github.io/kcp](https://georgepearse.github.io/kcp/). GitHub Pages serves the root of the `gh-pages` branch. Publish a reviewed local build with:

```sh
.venv-docs/bin/mkdocs gh-deploy --strict
```

This pushes generated output to `gh-pages`; it does not merge the source branch. The first publication was made from `docs/learning-fork-callout` while its source changes remained in a draft PR.

The documentation workflow validates pull requests. Once integrated into the default `english-docs` branch, source changes there also rebuild and update `gh-pages`. Because pushes made with the default Actions token do not themselves trigger a Pages build, the workflow explicitly requests one using the Pages API after deploying. Check both the documentation workflow and the Pages deployment before treating an update as live.

Source changes still go through a feature branch and draft PR. Publishing the documentation is separate from promoting any transport candidate.

References: [Material publishing guide](https://squidfunk.github.io/mkdocs-material/publishing-your-site/), [GitHub Pages publishing sources](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site), and [Pages build API](https://docs.github.com/en/rest/pages/pages#request-a-github-pages-build).
