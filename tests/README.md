# tests/

Repository-level and cross-cutting tests.

At Genesis these are **governance invariant tests**: they check that the repository's own
rules hold. They are not product tests, because there is no product yet.

| File | Checks |
| --- | --- |
| `test_structure.py` | Reserved directories exist with READMEs; required governance documents exist; the ADR index and the ADR directory agree; no boundary-violating Git configuration |
| `test_register.py` | The register validates; and the validator actually rejects each violation it claims to reject |

`test_register.py` deliberately tests the **validator**, not just the register. A validator
that passes everything would leave a green build and no enforcement.

## Run

```sh
make check
# or
python3 -m unittest discover -s tests -v
```

Python 3.11 standard library only (ADR-0002, OQ-4).

Product tests will live with their modules; this directory holds what spans them.
