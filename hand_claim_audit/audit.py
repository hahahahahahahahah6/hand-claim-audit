"""Offline documentation and Python evidence inspection."""
import argparse
import ast
import fnmatch
import json
import os
from pathlib import Path
import re

from . import __version__
from .phrases import HAND, NOHAND


def _pattern(phrases):
    return re.compile(r'\b(?:' + '|'.join(re.escape(p) for p in sorted(phrases, key=len, reverse=True)) + r')\b')


def claims(text):
    """Return positive and negative claims after excluding fenced blocks."""
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                fence = None
            continue
        if match:
            fence = match[1]
        else:
            lines.append(line)
    positive = negative = False
    for paragraph in re.split(r'\n\s*\n', '\n'.join(lines)):
        normalized = ' '.join(paragraph.lower().replace("n't", ' not').replace('-', ' ').split())
        negative = negative or bool(_pattern(NOHAND).search(normalized))
        normalized = _pattern(NOHAND).sub(' ', normalized)
        positive = positive or bool(_pattern(HAND).search(normalized))
    return positive, negative


def evidence(source):
    """Resolve provider aliases and bindings within a single module, never execute."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    aliases = {}
    bound = {}
    shadowed = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split('.')[0]] = item.name if item.asname else item.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom) and node.module:
            for item in node.names:
                aliases[item.asname or item.name] = node.module + '.' + item.name
    for name in shadowed:
        aliases.pop(name, None)

    def key(node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = key(node.value)
            return base + '.' + node.attr if base else None
        return None

    def resolve(node):
        value = key(node)
        if not value:
            return ''
        first, *rest = value.split('.')
        return '.'.join([aliases.get(first, ''), *rest]) if first in aliases else ''

    def constructor(node):
        if not isinstance(node, ast.Call):
            return None
        path = resolve(node.func)
        if path.startswith('mediapipe.') and path.endswith('.hands.Hands'):
            return 'process'
        if path == 'cvzone.HandTrackingModule.HandDetector':
            return 'findHands'
        return None

    # Iterate to support aliases of constructed objects irrespective of traversal order.
    nodes = list(ast.walk(tree))
    for _ in range(len(nodes) + 1):
        changed = False
        for node in nodes:
            pairs = []
            if isinstance(node, ast.Assign):
                pairs = [(target, node.value) for target in node.targets]
            elif isinstance(node, ast.AnnAssign):
                pairs = [(node.target, node.value)]
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                pairs = [(item.optional_vars, item.context_expr) for item in node.items]
            for target, value in pairs:
                name = key(target)
                operation = constructor(value) or bound.get(key(value))
                if name and operation and bound.get(name) != operation:
                    bound[name] = operation
                    changed = True
        if not changed:
            break
    for node in nodes:
        if constructor(node):
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            operation = constructor(node.func.value) or bound.get(key(node.func.value))
            if operation == node.func.attr:
                return True
    return False


def audit(root, ignores=()):
    root = Path(root)
    if not root.is_dir():
        raise ValueError('Root must be a readable directory')
    positive = negative = production = testing = False
    scanned = 0
    def walk_error(error):
        raise error
    for directory, dirs, files in os.walk(root, onerror=walk_error, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink() and not any(fnmatch.fnmatch((Path(directory) / d).relative_to(root).as_posix(), pat) for pat in ignores))
        for filename in sorted(files):
            path = Path(directory) / filename
            relative = path.relative_to(root)
            if path.is_symlink() or any(fnmatch.fnmatch(relative.as_posix(), pat) for pat in ignores):
                continue
            parts = relative.parts[:-1]
            doc = relative.as_posix() == 'README.md' or (path.suffix == '.md' and 'docs' in parts)
            excluded = any(p in ('fixtures', 'docs', 'examples') for p in parts)
            source = path.suffix == '.py' and not excluded
            if not (doc or source):
                continue
            text = path.read_text(encoding='utf-8')
            scanned += 1
            if doc:
                p, n = claims(text)
                positive |= p
                negative |= n
            if source and evidence(text):
                test = 'tests' in parts or filename.startswith('test_') or filename.endswith('_test.py')
                testing |= test
                production |= not test
    findings = []
    if positive and not production:
        findings.append(dict(rule='documented-hand-claim-false', severity='MEDIUM' if testing else 'HIGH', message='Documentation promises a capability without production source evidence.'))
    if negative and production:
        findings.append(dict(rule='documented-no-hand-claim-false', severity='HIGH', message='Documentation denies a capability present in production source.'))
    return dict(verdict='FAIL' if findings else 'PASS', findings=findings, files_scanned=scanned)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(__import__('sys').stderr)
        self.exit(1, self.prog + ': error: ' + message + '\n')


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument('root')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--ignore', action='append', default=[])
    parser.add_argument('--fail-on', choices=('HIGH', 'MEDIUM'), default='HIGH')
    parser.add_argument('--version', action='version', version=__version__)
    args = parser.parse_args(argv)
    try:
        result = audit(args.root, args.ignore)
    except (OSError, ValueError, UnicodeError) as error:
        parser.exit(1, str(error) + '\n')
    failed = any(f['severity'] == 'HIGH' or args.fail_on == 'MEDIUM' for f in result['findings'])
    result['verdict'] = 'FAIL' if failed else 'PASS'
    if args.json:
        print(json.dumps(result))
    else:
        print(result['verdict'])
        for finding in result['findings']:
            print('{severity} {rule}: {message}'.format(**finding))
        if args.verbose:
            print('Files scanned: {}'.format(result['files_scanned']))
    return 2 if failed else 0
