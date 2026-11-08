"""Only public aggregate PNGs may be cached in the Binder demo image."""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import struct
import tempfile
import unittest
import zlib

from ci.prepare_binder_demo import GALLERY_TAG, preview_cell, validate_preview


ROOT = Path(__file__).resolve().parents[1]


def tiny_png():
    """A valid one-pixel RGB PNG, independent of the plotting environment."""
    def chunk(kind, payload):
        return (struct.pack('>I', len(payload)) + kind + payload
                + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff))
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\x20\x60\x80'))
            + chunk(b'IEND', b''))


class BinderDemoPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        manifest = b'{"data_included": false, "files": {}}\n'
        (self.root / 'manifest.json').write_bytes(manifest)
        image = base64.b64encode(tiny_png()).decode('ascii')
        self.notebook = {
            'nbformat': 4, 'nbformat_minor': 5,
            'metadata': {'aggregate_preview': {
                'source': 'published_aggregates', 'statistical_reestimation': False,
                'figure_count': 9, 'manifest_sha256': hashlib.sha256(manifest).hexdigest(),
            }},
            'cells': [
                {'cell_type': 'markdown', 'metadata': {}, 'source': '# Aggregate preview'},
                {'cell_type': 'code', 'metadata': {'tags': ['parameters']},
                 'source': 'MODE = "aggregate"\nOUTPUT_DIR = ""',
                 'execution_count': None, 'outputs': []},
                {'cell_type': 'code', 'metadata': {'tags': [GALLERY_TAG]},
                 'source': '# Display the nine public figures', 'execution_count': None,
                 'outputs': [
                     {'output_type': 'display_data', 'metadata': {'image/png': {'width': 1000}},
                      'data': {'image/png': image,
                               'text/plain': f'Published aggregate figure {index}'}}
                     for index in range(1, 10)
                 ]},
            ],
        }

    def test_valid_public_png_preview_is_accepted_without_mutation(self):
        before = deepcopy(self.notebook)
        validate_preview(self.notebook, self.root)
        self.assertEqual(self.notebook, before)
        self.assertIs(preview_cell(self.notebook), self.notebook['cells'][2])

    def test_gallery_must_be_unique_and_a_code_cell(self):
        missing = deepcopy(self.notebook)
        missing['cells'][2]['metadata'] = {}
        duplicate = deepcopy(self.notebook)
        duplicate['cells'].append(deepcopy(duplicate['cells'][2]))
        wrong_type = deepcopy(self.notebook)
        wrong_type['cells'][2]['cell_type'] = 'markdown'
        for notebook in (missing, duplicate, wrong_type):
            with self.subTest(notebook=notebook['cells'][-1]['cell_type']):
                with self.assertRaises(ValueError):
                    preview_cell(notebook)

    def test_only_current_public_aggregate_provenance_is_accepted(self):
        for field, value in [('source', 'uploaded_survey'), ('statistical_reestimation', True),
                             ('figure_count', 8), ('manifest_sha256', '0' * 64)]:
            with self.subTest(field=field):
                notebook = deepcopy(self.notebook)
                notebook['metadata']['aggregate_preview'][field] = value
                with self.assertRaises(ValueError):
                    validate_preview(notebook, self.root)
        notebook = deepcopy(self.notebook)
        notebook['metadata'].pop('aggregate_preview')
        with self.assertRaises(ValueError):
            validate_preview(notebook, self.root)

    def test_missing_extra_or_stream_outputs_are_rejected(self):
        for change in ('missing', 'extra', 'stream'):
            with self.subTest(change=change):
                notebook = deepcopy(self.notebook)
                outputs = preview_cell(notebook)['outputs']
                if change == 'missing':
                    outputs.pop()
                elif change == 'extra':
                    outputs.append(deepcopy(outputs[0]))
                else:
                    outputs[0] = {'output_type': 'stream', 'name': 'stdout',
                                  'text': '/private/input.sav'}
                with self.assertRaises(ValueError):
                    validate_preview(notebook, self.root)

    def test_html_invalid_png_and_personal_text_are_rejected(self):
        for change in ('html', 'invalid-base64', 'non-png', 'personal-path'):
            with self.subTest(change=change):
                notebook = deepcopy(self.notebook)
                data = preview_cell(notebook)['outputs'][0]['data']
                if change == 'html':
                    data['text/html'] = '<script>alert(1)</script>'
                elif change == 'invalid-base64':
                    data['image/png'] = 'not valid base64!'
                elif change == 'non-png':
                    data['image/png'] = base64.b64encode(b'not a PNG').decode('ascii')
                else:
                    data['text/plain'] = 'Input: /Users/someone/private.sav'
                with self.assertRaises(ValueError):
                    validate_preview(notebook, self.root)

    def test_other_cell_outputs_execution_state_and_attachments_are_rejected(self):
        for change in ('other-output', 'gallery-count', 'other-count', 'attachment', 'widgets'):
            with self.subTest(change=change):
                notebook = deepcopy(self.notebook)
                if change == 'other-output':
                    notebook['cells'][1]['outputs'] = [{'output_type': 'stream',
                        'name': 'stdout', 'text': '/private/profile.json'}]
                elif change == 'gallery-count':
                    preview_cell(notebook)['execution_count'] = 1
                elif change == 'other-count':
                    notebook['cells'][1]['execution_count'] = 1
                elif change == 'attachment':
                    notebook['cells'][0]['attachments'] = {'private': {'text/plain': 'hidden'}}
                else:
                    notebook['metadata']['widgets'] = {'private': 'saved state'}
                with self.assertRaises(ValueError):
                    validate_preview(notebook, self.root)


class BinderDemoSourceTests(unittest.TestCase):
    def test_git_demo_source_has_no_outputs_and_uses_fresh_aggregate_settings(self):
        notebook = json.loads((ROOT / 'notebooks/demo.ipynb').read_text())
        for cell in notebook['cells']:
            self.assertFalse(cell.get('attachments'))
            if cell['cell_type'] == 'code':
                self.assertEqual(cell['outputs'], [])
                self.assertIsNone(cell['execution_count'])
        self.assertFalse(notebook['metadata'].get('widgets'))
        parameters = next(cell for cell in notebook['cells']
                          if 'parameters' in cell.get('metadata', {}).get('tags', []))
        source = parameters['source']
        namespace = {}
        exec(source if isinstance(source, str) else ''.join(source), namespace)
        self.assertEqual(namespace['MODE'], 'aggregate')
        self.assertEqual(namespace['OUTPUT_DIR'], '')
        self.assertNotIn('/Users/', json.dumps(notebook))
        preview_cell(notebook)

    def test_docker_prepares_demo_as_user_and_ci_keeps_public_only_gates(self):
        dockerfile = (ROOT / '.binder/Dockerfile').read_text()
        self.assertRegex(dockerfile, r'RUN python(?:3)? ci/prepare_binder_demo\.py')
        self.assertLess(dockerfile.index('USER 1000'),
                        dockerfile.index('ci/prepare_binder_demo.py'))
        workflow = (ROOT / '.github/workflows/public-reproducibility.yml').read_text()
        self.assertIn('--notebook demo', workflow)
        jobs = re.split(r'^  ([a-z][a-z-]+):\s*$', workflow.split('jobs:\n', 1)[1], flags=re.M)
        for name, block in zip(jobs[1::2], jobs[2::2], strict=True):
            with self.subTest(job=name):
                condition = re.search(r'^    if: (.*)$', block, re.M).group(1)
                self.assertTrue(condition.startswith('${{ github.event.repository.private == false'))
                self.assertNotIn('||', condition)
                self.assertLess(block.index('if:'), block.index('runs-on:'))


if __name__ == '__main__':
    unittest.main()
