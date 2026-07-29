#!/usr/bin/env python3
"""Remove answer candidates whose locator and claimed identity disagree."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_contract as contract


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("input must be a JSON object")
    return value


def answer_object(payload: dict[str, Any]) -> dict[str, Any]:
    answer = payload.get("answer")
    return answer if isinstance(answer, dict) else payload


def identity_for_url(url: str) -> dict[str, str] | None:
    parsed = urlsplit(url.strip())
    host = (parsed.hostname or "").casefold()
    path = parsed.path.strip("/")
    if host in {"github.com", "www.github.com"}:
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 2 and all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts[:2]):
            return {"kind": "github", "value": f"{parts[0]}/{parts[1].removesuffix('.git')}"}
    if host in {"arxiv.org", "export.arxiv.org"}:
        match = re.fullmatch(r"abs/([^/]+)", path) or re.fullmatch(r"pdf/([^/]+?)(?:\.pdf)?", path)
        if match:
            return {"kind": "arxiv", "value": match.group(1)}
    if host in {"doi.org", "dx.doi.org"} and path:
        return {"kind": "doi", "value": path}
    if host == "pubmed.ncbi.nlm.nih.gov":
        match = re.fullmatch(r"(\d+)", path)
        if match:
            return {"kind": "pmid", "value": match.group(1)}
    if parsed.scheme in {"http", "https"} and host:
        return {"kind": "official_url", "value": url}
    return None


def display_title_matches(title: str, resolved_title: str, kind: str) -> bool:
    """Allow normal display-title variants without accepting a different claim."""
    candidate = contract.normalized_text(title)
    resolved = contract.normalized_text(resolved_title)
    if not candidate or not resolved:
        return False
    if candidate == resolved or candidate in resolved or resolved in candidate:
        # A very short generic label should not pass merely because it is a substring.
        candidate_word_count = len(re.findall(r"[a-z0-9]+", title.casefold()))
        return candidate_word_count >= 2 and min(len(candidate), len(resolved)) / max(len(candidate), len(resolved)) >= 0.25
    score = contract.title_similarity(title, [resolved_title])
    if kind in {"arxiv", "doi", "pmid"}:
        # This admits title prefixes/suffixes and punctuation changes, but rejects
        # a materially different title at the same locator.
        return score >= 0.88
    # Official documentation often adds a product or site suffix to the page title.
    if score >= 0.88:
        return True
    candidate_tokens = set(candidate.split())
    resolved_tokens = set(resolved.split())
    overlap = len(candidate_tokens & resolved_tokens)
    return overlap >= 2 and overlap / max(len(candidate_tokens), 1) >= 0.5


def verify_source(source: dict[str, Any], timeout: float) -> dict[str, Any]:
    title = str(source.get("title") or "")
    url = str(source.get("url") or "")
    identity = identity_for_url(url)
    if identity is None:
        return {"status": "unresolved", "reason": "unsupported_locator", "title": title, "url": url}
    # GitHub display titles often add a short description after owner/repository.
    # Verify the canonical repository identity first, then require its owner and
    # repository name to remain visible in the displayed title.
    verification_title = title or identity["value"]
    if identity["kind"] == "github":
        verification_title = identity["value"]
    candidate = {"title": verification_title, "source_identity": {**contract.identity_template(), **identity}}
    result = contract.verify_candidate_source(
        candidate,
        timeout,
        allow_official_url=identity["kind"] == "official_url",
        require_title_match=False,
    )
    if result.get("status") == "verified":
        resolved_title = str(result.get("resolved_title") or "")
        if identity["kind"] == "official_url":
            resolved_normalized = contract.normalized_text(resolved_title)
            host = (urlsplit(url).hostname or "").removeprefix("www.")
            host_normalized = contract.normalized_text(host)
            if not resolved_normalized or resolved_normalized in {host_normalized, f"www{host_normalized}"}:
                result["status"] = "unresolved"
                result["evidence"] = "publisher page returned no usable title metadata"
                return {
                    "status": "unresolved",
                    "reason": str(result["evidence"]),
                    "title": title,
                    "url": url,
                    "resolved_title": resolved_title,
                    "canonical_id": str(result.get("canonical_id") or ""),
                }
        if identity["kind"] == "github":
            normalized_display = contract.normalized_text(title)
            normalized_repo = contract.normalized_text(identity["value"])
            repo_name = contract.normalized_text(identity["value"].split("/", 1)[-1])
            title_ok = normalized_repo in normalized_display or repo_name in normalized_display
        else:
            title_ok = display_title_matches(title, resolved_title, identity["kind"])
        if not title_ok:
            result["status"] = "failed"
            result["evidence"] = f"display title does not match authoritative title; score={contract.title_similarity(title, [str(result.get('resolved_title') or '')]):.4f}"
    return {
        "status": str(result.get("status") or "failed"),
        "reason": str(result.get("evidence") or "identity_verification_failed"),
        "title": title,
        "url": url,
        "resolved_title": str(result.get("resolved_title") or ""),
        "canonical_id": str(result.get("canonical_id") or ""),
    }


def gate(payload: dict[str, Any], timeout: float) -> tuple[dict[str, Any], dict[str, Any]]:
    answer = copy.deepcopy(answer_object(payload))
    if not isinstance(answer.get("sources"), list):
        raise ValueError("answer.sources must be a list")
    trace = answer.get("discovery_trace")
    if not isinstance(trace, dict):
        raise ValueError("answer.discovery_trace must be an object")
    source_results = [verify_source(source, timeout) for source in answer["sources"] if isinstance(source, dict)]
    sources_ok = [source for source, result in zip(answer["sources"], source_results) if result["status"] == "verified"]
    for index, source in enumerate(sources_ok, start=1):
        source["rank"] = index
    failures = [result for result in source_results if result["status"] != "verified"]
    for result in failures:
        answer.setdefault("gaps", []).append(
            f"identity_gate_removed: {result['title']} ({result['url']}): {result['reason']}"
        )
    answer["sources"] = sources_ok
    report = {
        "sources_checked": len(source_results),
        "sources_kept": len(sources_ok),
        "removed": failures,
        "status": "pass" if not failures else "filtered",
    }
    return answer, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args()
    if not 0.2 <= args.timeout <= 60:
        raise ValueError("timeout must be between 0.2 and 60 seconds")
    sanitized, report = gate(load(Path(args.input).expanduser()), args.timeout)
    Path(args.output).expanduser().write_text(json.dumps(sanitized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(args.report).expanduser().write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
