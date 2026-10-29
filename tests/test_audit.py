import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from hand_claim_audit.audit import audit, claims, evidence, main, _pattern
from hand_claim_audit.phrases import HAND, NOHAND

FIXTURES = Path(__file__).parent / 'fixtures'


class ClaimsTests(unittest.TestCase):
    def test_fences(self):
        for marker in ('```', '~~~', '   ````'):
            with self.subTest(marker=marker):
                self.assertEqual(claims(marker + '\ndetects hands\n' + marker), (False, False))
    def test_inline(self):
        self.assertEqual(claims('It `detects hands`.'), (True, False))
    def test_negative_removal(self):
        self.assertEqual(claims('does not detect hands'), (False, True))
    def test_mixed(self):
        self.assertEqual(claims('does not detect hands but tracks hands'), (True, True))
    def test_hyphens(self):
        self.assertEqual(claims('hand-gesture-recognition'), (True, False))
    def test_contractions(self):
        self.assertEqual(claims("doesn't detect hands"), (False, True))
    def test_paragraph_join(self):
        self.assertEqual(claims('detects\nhands'), (True, False))
        self.assertEqual(claims('detects\n\nhands'), (False, False))
    def test_boundaries(self):
        self.assertEqual(claims('redetect handsfree'), (False, False))
    def test_longest_first(self):
        self.assertEqual(_pattern(HAND).search('hand gesture recognition support')[0], 'hand gesture recognition support')
        for values in (HAND, NOHAND):
            self.assertEqual(list(values), sorted(values, key=len, reverse=True))
            self.assertEqual(len(values), len(set(values)))
    def test_readme_prose(self):
        self.assertEqual(claims((Path(__file__).parents[1] / 'README.md').read_text()), (False, False))


POSITIVE = {
'direct': 'import mediapipe\nmediapipe.solutions.hands.Hands()',
'alias': 'import mediapipe as mp\nmp.solutions.hands.Hands()',
'from': 'from mediapipe.solutions.hands import Hands\nHands()',
'from_alias': 'from mediapipe.solutions import hands as h\nh.Hands()',
'with': 'import mediapipe as mp\nwith mp.solutions.hands.Hands() as h:\n h.process(frame)',
'attribute': 'import mediapipe as mp\nself.h = mp.solutions.hands.Hands()\nself.h.process(frame)',
'chained': 'import mediapipe as mp\nmp.solutions.hands.Hands().process(frame)',
'process': 'import mediapipe as mp\nh = mp.solutions.hands.Hands()\nh.process(frame)',
'annotated': 'import mediapipe as mp\nh: object = mp.solutions.hands.Hands()\nh.process(frame)',
'cvzone': 'import cvzone\ncvzone.HandTrackingModule.HandDetector()',
'cvzone_from': 'from cvzone.HandTrackingModule import HandDetector\nHandDetector()',
'findHands': 'from cvzone.HandTrackingModule import HandDetector as HD\nh = HD()\nh.findHands(frame)',
'cvzone_with': 'from cvzone.HandTrackingModule import HandDetector\nwith HandDetector() as h:\n h.findHands(frame)',
'cvzone_attribute': 'from cvzone.HandTrackingModule import HandDetector\nself.h = HandDetector()\nself.h.findHands(frame)',
'cvzone_annotated': 'from cvzone.HandTrackingModule import HandDetector\nh: object = HandDetector()\nh.findHands(frame)',
'cvzone_chained': 'from cvzone.HandTrackingModule import HandDetector\nHandDetector().findHands(frame)',
}
NEGATIVE = {
'import': 'import mediapipe\nfrom cvzone.HandTrackingModule import HandDetector',
'image': 'import cv2\ncv2.imread("hand.png")',
'pil': 'from PIL import Image\nImage.open("hand.png")',
'camera': 'import cv2\nc = cv2.VideoCapture(0)\nc.read()',
'drawing': 'import mediapipe as mp\nmp.solutions.drawing_utils.draw_landmarks(image, landmarks)',
'face': 'import cv2\ncv2.CascadeClassifier("face.xml").detectMultiScale(image)',
'pose': 'import mediapipe as mp\nmp.solutions.pose.Pose().process(image)',
'shadow_class': 'from mediapipe.solutions.hands import Hands\nclass Hands: pass\nHands()',
'shadow_function': 'from cvzone.HandTrackingModule import HandDetector\ndef HandDetector(): pass\nHandDetector()',
'shadow_module': 'import mediapipe as mp\nclass mp: pass\nmp.solutions.hands.Hands()',
'unbound_process': 'unknown.process(frame)',
'unbound_find': 'unknown.findHands(frame)',
'string': 'text = "hand detection mp.solutions.hands.Hands()"',
'subprocess': 'import subprocess\nsubprocess.run(["HandDetector"])',
'syntax': 'import mediapipe\nmediapipe.solutions.hands.Hands((',
'other_provider': 'import fake\nfake.solutions.hands.Hands()',
}


class EvidenceTests(unittest.TestCase):
    pass


def evidence_test(source, expected):
    def test(self):
        self.assertEqual(evidence(source), expected)
    return test


for name, source in POSITIVE.items():
    setattr(EvidenceTests, 'test_positive_' + name, evidence_test(source, True))
for name, source in NEGATIVE.items():
    setattr(EvidenceTests, 'test_negative_' + name, evidence_test(source, False))
for family, phrases in (('hand', HAND), ('nohand', NOHAND)):
    for index, phrase in enumerate(phrases):
        def test(self, phrase=phrase, family=family):
            self.assertEqual(claims(phrase), (family == 'hand', family == 'nohand'))
        setattr(ClaimsTests, 'test_template_{}_{}'.format(family, index), test)


class IntegrationTests(unittest.TestCase):
    def run_cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(list(map(str, args)))
        return code, output.getvalue()
    def test_good(self):
        self.assertEqual(audit(FIXTURES / 'good')['findings'], [])
        self.assertEqual(self.run_cli(FIXTURES / 'good')[0], 0)
    def test_bad(self):
        code, output = self.run_cli(FIXTURES / 'bad', '--json')
        self.assertEqual(code, 2)
        self.assert_finding(json.loads(output), 'documented-hand-claim-false', 'HIGH')
    def assert_finding(self, result, rule, severity):
        self.assertEqual(len(result['findings']), 1)
        self.assertEqual(result['findings'][0]['rule'], rule)
        self.assertEqual(result['findings'][0]['severity'], severity)
    def test_testonly(self):
        self.assert_finding(audit(FIXTURES / 'testonly'), 'documented-hand-claim-false', 'MEDIUM')
        self.assertEqual(self.run_cli(FIXTURES / 'testonly')[0], 0)
        self.assertEqual(self.run_cli(FIXTURES / 'testonly', '--fail-on', 'MEDIUM')[0], 2)
    def test_nohand(self):
        code, output = self.run_cli(FIXTURES / 'nohand', '--json')
        self.assertEqual(code, 2)
        self.assert_finding(json.loads(output), 'documented-no-hand-claim-false', 'HIGH')
    def test_noclaim(self):
        self.assertEqual(audit(FIXTURES / 'noclaim')['verdict'], 'PASS')
    def test_ignore(self):
        self.assertEqual(self.run_cli(FIXTURES / 'bad', '--ignore', 'README.md')[0], 0)
        self.assertEqual(self.run_cli(FIXTURES / 'good', '--ignore', '*.py')[0], 2)
    def test_json(self):
        _, output = self.run_cli(FIXTURES / 'good', '--json')
        self.assertEqual(set(json.loads(output)), {'verdict', 'findings', 'files_scanned'})
    def test_verbose(self):
        self.assertIn('Files scanned: 2', self.run_cli(FIXTURES / 'good', '--verbose')[1])
    def test_version(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as caught:
            main(['--version'])
        self.assertEqual(caught.exception.code, 0)
        self.assertEqual(out.getvalue().strip(), '0.1.0')
    def test_invalid_root(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            main(['/nonexistent-hand-audit-root'])
        self.assertEqual(caught.exception.code, 1)
    def test_usage(self):
        for args in ([], ['--unknown'], ['.', '--fail-on', 'LOW']):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                main(args)
            self.assertEqual(caught.exception.code, 1)
    def test_exclusions_and_test_names(self):
        for location in ('fixtures/a.py', 'docs/a.py', 'examples/a.py', 'tests/a.py', 'test_a.py', 'a_test.py'):
            with self.subTest(location=location), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / 'README.md').write_text('detects hands')
                source = root / location
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text(POSITIVE['direct'])
                result = audit(root)
                self.assert_finding(result, 'documented-hand-claim-false', 'HIGH' if location.split('/')[0] in ('fixtures', 'docs', 'examples') else 'MEDIUM')
    def test_docs_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'nested/docs').mkdir(parents=True)
            (root / 'nested/docs/guide.md').write_text('detects hands')
            (root / 'target').mkdir()
            (root / 'target/a.txt').write_text(POSITIVE['direct'])
            (root / 'link.py').symlink_to(root / 'target/a.txt')
            (root / 'linked').symlink_to(FIXTURES / 'good', target_is_directory=True)
            self.assert_finding(audit(root), 'documented-hand-claim-false', 'HIGH')
    def test_one_per_family(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'README.md').write_text('detects hands\n\ntracks hands\n\nfinds hands')
            self.assertEqual(len(audit(root)['findings']), 1)
    def test_self_audit(self):
        self.assertEqual(audit(Path(__file__).parents[1])['findings'], [])


if __name__ == '__main__':
    unittest.main()
