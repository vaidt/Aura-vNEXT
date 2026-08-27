# provenance/

The provenance system: how anything from the frozen corpus is traced, and how that trace
survives vNEXT's independent Git history.

| Path | Status | Purpose |
| --- | --- | --- |
| [`PROVENANCE-POLICY.md`](PROVENANCE-POLICY.md) | NORMATIVE | What must be recorded, and why a clean history must not lose it |
| [`TRANSFER-REGISTER.md`](TRANSFER-REGISTER.md) | NORMATIVE | What the register means and how to amend it |
| [`transfer-register.json`](transfer-register.json) | DATA | The register itself |
| [`transfer-register.schema.json`](transfer-register.schema.json) | SCHEMA | Register shape, JSON Schema 2020-12 |
| [`CORPUS-INDEX.md`](CORPUS-INDEX.md) | FACTUAL RECORD | The frozen source repositories and their freeze commits |
| [`BOUNDARY-INCIDENTS.md`](BOUNDARY-INCIDENTS.md) | FACTUAL RECORD | Detected boundary violations |
| [`records/`](records/) | RECORD | One provenance record per transferred artifact |

## Current state

**No artifact has been discovered, reviewed, verified, approved, or transferred.**
The register is empty and `corpus_reachable` is `false` — the corpus was not reachable
from the Genesis environment (see `CORPUS-INDEX.md` §2).

## Validate

```sh
python3 tools/validate_register.py
```
