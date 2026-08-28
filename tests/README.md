# tests/

Repository-level and cross-cutting tests.

At Genesis these were **governance invariant tests** only: checks that the repository's
own rules hold. M0 added the evidence suites, and the product loop added the suites that
exercise the path from an application event to a verdict.

| File or directory | Checks |
| --- | --- |
| `test_structure.py` | Reserved directories exist with READMEs; required governance documents exist; the ADR index and the ADR directory agree; no boundary-violating Git configuration |
| `test_register.py` | The register validates; and the validator actually rejects each violation it claims to reject |
| `conformance/` | The canonical bytes, the digests, the three verifier states, and the package boundary — including oracles that do not depend on the implementation under test |
| `mutation/` | One protected element altered at a time, against the reference package; each must classify as `TAMPERED` |
| `test_independence.py` | The reference package verifies in an isolated environment that holds neither the producer nor this repository |
| `product/` | The product loop: `test_producer.py` (event → package), `test_end_to_end.py` (the acceptance experiment through the `aura` command line), `test_producer_mutations.py` (the adversarial matrix against a *produced* package), `test_clean_room.py` (produced in environment A, verified in environment B) |

The product suites build their packages through `app.producer` and `aura record` rather
than copying the committed fixture. A suite that only ever mutated the checked-in package
would be testing the fixture, not the product.

`test_register.py` deliberately tests the **validator**, not just the register. A validator
that passes everything would leave a green build and no enforcement.

## Run

```sh
make check
# or
python3 -m unittest discover -s tests -v
```

Python 3.11 standard library only (ADR-0002, OQ-4).

Product tests live in `product/`; `_m0.py` and `_product.py` hold the helpers they share.
