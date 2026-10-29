# hand-claim-audit

An offline checker comparing Markdown promises about hand-related vision capabilities with static Python source evidence. Version 0.1.0 requires Python 3.9 or later and has no runtime dependencies.

Install and run:

```sh
python3 -m pip install hand-claim-audit
hand-claim-audit . --json
python3 -m hand_claim_audit . --verbose
hand-claim-audit . --ignore 'vendor/*' --fail-on MEDIUM
hand-claim-audit --version
```

The input is one root directory. Documentation includes its README.md and Markdown files beneath any docs path component. Backtick and tilde fences are excluded; inline code counts. Paragraphs are joined across line breaks, lowercased, and normalized for contractions, hyphens, and whitespace. Exact templates use word boundaries and longer matches take priority. Negative spans are removed before positive matching.

For example, these templates are evaluated:

```text
detects hands
does not detect hands
```

Evidence comes from provider-resolved MediaPipe Hands and cvzone HandDetector construction or calls to process and findHands on corresponding bound objects. Imports and aliases are resolved within each module. Assignment, annotated assignment, context-manager bindings, attributes, and chained construction are supported. Local definitions shadow imported names.

Bare imports, image loading, camera capture, supplied landmark drawing, face or pose operations, arbitrary strings, shell commands, and unbound methods do not provide evidence. Source is parsed with ast and never executed. Invalid syntax contributes no evidence. Symlinked files and directories are skipped. Python beneath fixtures, docs, or examples is excluded; files beneath tests or named test_*.py or *_test.py count separately.

Rules (at most one finding per family):

```text
documented-hand-claim-false: HIGH without production evidence; MEDIUM with test evidence only.
documented-no-hand-claim-false: HIGH when production evidence contradicts a negative claim.
```

A project with no matching documentation passes. The default threshold is HIGH; selecting MEDIUM also fails on test-only findings. Exit status is 0 for PASS, 2 for FAIL, and 1 for invalid input, unreadable roots, or usage errors. JSON includes verdict, findings (rule, severity, message), and files_scanned. Human output includes a verdict and findings; verbose mode adds a scanned-file count. Ignore patterns are repeatable fnmatch globs against relative POSIX paths.

This is a static heuristic, not proof that a feature works. Construction alone is sufficient. Dynamic imports, cross-module bindings, runtime control flow, and provider behavior are not evaluated. No model execution, network access, or dependency import is needed.

Development checks:

```sh
python3 -m unittest discover
python3 -m build
python3 -m hand_claim_audit .
```

The source distribution includes tests and fixtures. Licensed under MIT.
