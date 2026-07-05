# Templates

Runnable skeletons that encode the patterns in the reference docs. Copy them into
a new replication and re-point them — they are starting code, not a finished
project. Rename the import package `pkg` to your project's name throughout.

```
templates/
├── config/sources.yaml            # the data-source registry (see references/data-sources.md)
├── src/pkg/datasources.py         # fetch clients: retry, provenance, block-vs-API split
├── src/pkg/engine.py              # the maths: each function == one equation; (panel, weights) contract
├── scripts/export_web_data.py     # raw panels + baseline -> web/data/index.json
├── web/index.html  app.js  engine.js  worker.js   # zero-build site + the JS twin
└── tests/test_web_engine_parity.py # the Python<->JS parity contract
```

Suggested order (mirrors the SKILL.md build sequence):

1. Fill in `config/sources.yaml` from the paper's data appendix.
2. Adapt `datasources.py` (keep the shared HTTP layer; add provider clients).
3. Write a `pipeline.py` that returns the `(panel, weights)` pair, then fill in the
   equation bodies in `engine.py`.
4. Validate against the authors' file; write `DECISIONS.md` + `differences_report.md`.
5. Wire `export_web_data.py`, port the engine to `engine.js`, and make the parity
   test pass before deploying the site.

The engine/JS bodies here implement a momentum-style example; replace them with
your paper's equations but keep the contract and the parameter-not-constant
discipline so robustness checks, country ports, and the JS twin all reuse the
same code.
