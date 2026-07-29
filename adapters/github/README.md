# GitHub Actions adapter

The canonical GitHub Action entry point is the **repository root** [`action.yml`](../../action.yml).

Do not duplicate that file here — vendoring or referencing this repo should use:

```yaml
uses: your-org/spring-boot-doc-agent@vX
# or, from a checkout of this repo:
uses: ./action.yml
```

## Workflow snippet

See [`workflow-snippet.yml`](workflow-snippet.yml) for a minimal job that installs `doc-engine`, runs the pipeline, and gates on `certification.json`.
