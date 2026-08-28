"""The `aura` operator surface: record a decision, verify a package.

Two commands, one for each end of the M0 product loop:

    aura record   application event -> Evidence Package
    aura verify   Evidence Package  -> VERIFIED / TAMPERED / INVALID

The command layer parses arguments, reads files, and prints results. It computes
nothing that is protected: `record` delegates to `app.producer`, which delegates to
`core`, and `verify` calls `app.verifier.verify_package` unchanged. No canonical
form, digest, or chain rule is restated here, so the surface cannot drift away from
the implementation it exposes.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.producer import (DecisionEvent, ProducerError, append_event, build_package,
                          derive_policy_repr, input_digest, write_package)
from app.verifier import INVALID, TAMPERED, VERIFIED, verify_package
from core import M0_PACKAGE_PROFILE

__all__ = ["main", "EXIT_STATUS", "EXIT_OK", "EXIT_USAGE", "EXIT_REFUSED"]

# `verify` reports the verdict through its exit status, so a caller that never reads
# stdout still gets the answer. The three states keep the values ADR-0006 fixed.
EXIT_STATUS = {VERIFIED: 0, TAMPERED: 2, INVALID: 3}

EXIT_OK = 0
EXIT_USAGE = 64        # the command line could not be understood
EXIT_REFUSED = 65      # the command was understood; the event is not recordable


def _utc_now() -> str:
    """Return the current instant in the single spelling M0 accepts."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json_document(path: Path, label: str):
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProducerError(f"{label}: cannot be read ({exc})") from exc
    except UnicodeDecodeError as exc:
        raise ProducerError(f"{label}: not readable as UTF-8 ({exc})") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProducerError(
            f"{label}: malformed JSON ({exc.msg} at line {exc.lineno})"
        ) from exc


def _parse_violation(spec: str) -> dict:
    """Parse ``RULE:ACTION:CONFIDENCE``.

    Split from the right twice, so a rule identifier may contain a colon while the
    action and confidence -- which may not -- stay unambiguous.
    """
    parts = spec.rsplit(":", 2)
    if len(parts) != 3 or not all(part for part in parts):
        raise ProducerError(
            f"--violation {spec!r} is not RULE:ACTION:CONFIDENCE "
            f"(for example LOAN.DTI_EXCEEDED:BLOCK:0.95)"
        )
    rule, action, confidence = parts
    # Confidence is handed on as the text the operator typed. core.models converts it
    # through Decimal, so an exact decimal is scaled exactly rather than being routed
    # through a float first.
    return {"rule": rule, "action": action, "confidence": confidence}


def _parse_metadata(spec: str) -> tuple[str, str]:
    key, separator, value = spec.partition("=")
    if not separator or not key:
        raise ProducerError(f"--metadata {spec!r} is not KEY=VALUE")
    return key, value


def _resolve_input_hash(args) -> str:
    """Return the input reference, from a supplied digest or a local input file.

    M0 records a reference, never the input itself, so both routes end at the same
    protected member. ``--input-file`` exists because most applications hold the
    input as bytes and would otherwise have to reproduce the digest by hand.
    """
    if args.input_hash and args.input_file:
        raise ProducerError("--input-hash and --input-file are mutually exclusive")
    if args.input_hash:
        return args.input_hash
    if args.input_file:
        path = Path(args.input_file)
        try:
            return input_digest(path.read_bytes())
        except OSError as exc:
            raise ProducerError(f"--input-file {path}: cannot be read ({exc})") from exc
    raise ProducerError("one of --input-hash or --input-file is required")


def _event_from_args(args, policy_document) -> DecisionEvent:
    metadata = dict(_parse_metadata(spec) for spec in args.metadata)
    policy_repr = (args.policy_repr if args.policy_repr is not None
                   else derive_policy_repr(policy_document))
    return DecisionEvent(
        request_id=args.request_id,
        timestamp=args.timestamp or _utc_now(),
        decision=args.decision,
        input_hash=_resolve_input_hash(args),
        policy_repr=policy_repr,
        violations=[_parse_violation(spec) for spec in args.violation],
        metadata=metadata,
        shadow_hash=args.shadow_hash,
    )


def _events_from_file(path: Path, policy_document) -> list[DecisionEvent]:
    document = _read_json_document(path, str(path))
    if isinstance(document, dict):
        document = [document]
    if not isinstance(document, list):
        raise ProducerError(
            f"{path}: expected a JSON array of events, or a single event object"
        )
    default_repr = derive_policy_repr(policy_document)
    events = []
    for index, raw in enumerate(document):
        try:
            event = DecisionEvent.from_mapping(raw)
        except ProducerError as exc:
            raise ProducerError(f"{path}: event {index}: {exc}") from exc
        if "policy_repr" not in raw:
            event = DecisionEvent(
                request_id=event.request_id, timestamp=event.timestamp,
                decision=event.decision, input_hash=event.input_hash,
                policy_repr=default_repr, violations=event.violations,
                metadata=event.metadata, shadow_hash=event.shadow_hash,
            )
        events.append(event)
    if not events:
        raise ProducerError(f"{path}: contains no events")
    return events


def _cmd_record(args) -> int:
    output = Path(args.output)
    policy_path = Path(args.policy)
    policy_document = _read_json_document(policy_path, str(policy_path))

    existing = (output / "manifest.json").is_file()
    if existing and not args.append:
        raise ProducerError(
            f"{output} already holds an evidence package; pass --append to extend its "
            f"chain, or choose a different --output. Overwriting a package in place "
            f"would discard evidence already recorded."
        )
    if args.append and not existing:
        raise ProducerError(f"--append: {output} does not hold an evidence package")

    if args.events:
        events = _events_from_file(Path(args.events), policy_document)
    else:
        for required in ("decision", "request_id"):
            if getattr(args, required) is None:
                raise ProducerError(
                    f"--{required.replace('_', '-')} is required unless --events is used"
                )
        events = [_event_from_args(args, policy_document)]

    if args.append:
        if len(events) != 1:
            # Each append re-reads the package to find the terminus, so a batch would
            # need the intermediate states written anyway. Refused rather than
            # silently looping, so the operator sees the shape of what happens.
            raise ProducerError(
                "--append records one event at a time; run the command once per event"
            )
        files = append_event(output, events[0], policy_document=policy_document)
    else:
        package_id = args.package_id or output.resolve().name
        files = build_package(package_id, policy_document, events)

    write_package(output, files)

    records = files["evidence/audit.jsonl"].decode("utf-8").splitlines()
    manifest = json.loads(files["manifest.json"])
    if args.json:
        print(json.dumps({
            "package": str(output),
            "package_id": manifest["package_id"],
            "entries": manifest["entry_count"],
            "chain_head": manifest["chain_head"],
        }, indent=2, sort_keys=True))
    else:
        print("AURA EVIDENCE PRODUCER")
        print(f"Profile:    {manifest['profile']}")
        print(f"Package:    {output}")
        print(f"Package id: {manifest['package_id']}")
        print(f"Entries:    {manifest['entry_count']}")
        print(f"Chain head: {manifest['chain_head']}")
        print(f"Recorded:   {len(records)} sealed record(s)")
    return EXIT_OK


def _cmd_verify(args) -> int:
    result = verify_package(args.package)

    if args.json:
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    else:
        print("AURA EVIDENCE VERIFIER")
        print(f"Profile: {M0_PACKAGE_PROFILE}")
        if result.package_id:
            print(f"Package: {result.package_id}")
        if result.entries:
            print(f"Entries: {result.entries}")
        print(f"Result: {result.status}")
        for reason in result.reasons:
            print(f"  - {reason}", file=sys.stderr)

    return EXIT_STATUS[result.status]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aura",
        description="Record application decisions as M0 evidence, and verify it.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser(
        "record",
        help="record an application decision as an M0 Evidence Package",
        description="Turn an application event into a portable Evidence Package.",
    )
    record.add_argument("--output", required=True, metavar="DIR",
                        help="package directory to create, or to extend with --append")
    record.add_argument("--policy", required=True, metavar="FILE",
                        help="the policy document the decision was taken under")
    record.add_argument("--decision", choices=("ALLOW", "DENY", "REQUIRE_APPROVAL"),
                        help="the decision the application reached")
    record.add_argument("--request-id", metavar="ID",
                        help="the application's identifier for this decision")
    record.add_argument("--input-hash", metavar="HEX64",
                        help="digest of the decision input, already computed")
    record.add_argument("--input-file", metavar="FILE",
                        help="local input whose bytes are digested to the input reference")
    record.add_argument("--timestamp", metavar="RFC3339",
                        help="decision time as YYYY-MM-DDThh:mm:ssZ (default: now, UTC)")
    record.add_argument("--policy-repr", metavar="TEXT",
                        help="human-readable policy label (default: derived from the "
                             "policy document)")
    record.add_argument("--violation", action="append", default=[], metavar="R:A:C",
                        help="RULE:ACTION:CONFIDENCE; repeatable, order is protected")
    record.add_argument("--metadata", action="append", default=[], metavar="KEY=VALUE",
                        help="string metadata; repeatable")
    record.add_argument("--shadow-hash", metavar="HEX64",
                        help="optional shadow digest; absent when not given")
    record.add_argument("--package-id", metavar="ID",
                        help="package identifier (default: the output directory name)")
    record.add_argument("--events", metavar="FILE",
                        help="JSON array of events, recorded as one chain")
    record.add_argument("--append", action="store_true",
                        help="extend the chain of an existing package")
    record.add_argument("--json", action="store_true", help="emit the result as JSON")
    record.set_defaults(handler=_cmd_record)

    verify = sub.add_parser(
        "verify",
        help="verify an M0 Evidence Package",
        description="Verify a package from its directory alone.",
    )
    verify.add_argument("package", help="path to the evidence package directory")
    verify.add_argument("--json", action="store_true", help="emit the result as JSON")
    verify.set_defaults(handler=_cmd_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except ProducerError as exc:
        print(f"aura {args.command}: {exc}", file=sys.stderr)
        return EXIT_REFUSED
