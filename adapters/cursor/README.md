# Cursor adapter

Use **doc-engine** as the orchestrator from Cursor automations or agent rules:

```bash
pip install -e /path/to/spring-boot-doc-agent
doc-engine pipeline run /path/to/target-repo \
  --compliance-profile certified \
  --out-dir /tmp/doc-run
python3 /path/to/spring-boot-doc-agent/scripts/verify_certification.py /tmp/doc-run/certification.json
```

Gate merges on `certified: true` in `certification.json`. Do not reimplement stage bash sequences in `.cursor` rules — call the CLI.
