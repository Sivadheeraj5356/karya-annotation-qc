#!/usr/bin/env python3
"""Independent annotation-QC demo inspired by Karya's evaluation internship.

No Karya affiliation, production data, network calls, or model calls.
Run demo: python annotation_qc.py
Check a JSON array: python annotation_qc.py input.json
Run tests: python annotation_qc.py --test

Input rows: {task_id, reviewer_id, language, label}; label is pass or fail.
Reports pairwise raw agreement (not chance-adjusted), missing reviewers,
conflicting duplicate annotations, invalid rows and language-level coverage.
Disagreement is routed for human review, never treated as proof of error.
For production: add privacy controls, domain rubrics, sampling and validated
chance-adjusted statistics. Synthetic fixture below is not a benchmark.
"""
import json
import sys
from collections import Counter, defaultdict
from itertools import combinations


def audit(rows, minimum_reviewers=2):
    if not isinstance(rows, list):
        raise ValueError('Expected a JSON array')
    if not isinstance(minimum_reviewers, int) or minimum_reviewers < 2:
        raise ValueError('minimum_reviewers must be an integer >= 2')
    invalid, duplicate, conflicts = [], [], set()
    annotations, task_languages = {}, defaultdict(set)
    for index, row in enumerate(rows):
        if (not isinstance(row, dict)
            or any(not isinstance(row.get(k), str) or not row[k].strip()
                   for k in ('task_id', 'reviewer_id', 'language', 'label'))
            or row['label'] not in ('pass', 'fail')):
            invalid.append(index)
            continue
        task, reviewer = row['task_id'].strip(), row['reviewer_id'].strip()
        key = (task, reviewer)
        task_languages[task].add(row['language'].strip())
        if key in annotations:
            duplicate.append(index)
            if annotations[key] != row['label']:
                conflicts.add(key)
        else:
            annotations[key] = row['label']
    tasks = defaultdict(list)
    for key, label in annotations.items():
        task, reviewer = key
        if key not in conflicts:
            tasks[task].append((reviewer, label))
    review, languages = [], defaultdict(Counter)
    for task in sorted(task_languages):
        values = tasks[task]
        pairs = list(combinations(values, 2))
        agreeing = sum(a[1] == b[1] for a, b in pairs)
        reasons = []
        if len(values) < minimum_reviewers:
            reasons.append('insufficient independent reviewers')
        if any(key[0] == task for key in conflicts):
            reasons.append('conflicting duplicate excluded')
        if len(task_languages[task]) != 1:
            reasons.append('inconsistent task language')
        if pairs and agreeing < len(pairs):
            reasons.append('reviewer disagreement')
        # Mixed-language tasks are not silently assigned to one language.
        language = next(iter(task_languages[task])) if len(task_languages[task]) == 1 else 'MIXED'
        group = languages[language]
        group.update(tasks=1, valid_annotations=len(values), pairs=len(pairs), agreeing=agreeing,
                     needs_review=int(bool(reasons)))
        if reasons:
            review.append({'task_id': task, 'reasons': reasons})
    by_language = {}
    for language, counts in sorted(languages.items()):
        by_language[language] = dict(counts, raw_pairwise_agreement=(
            counts['agreeing'] / counts['pairs'] if counts['pairs'] else None))
    return {'input_rows': len(rows), 'invalid_row_indices': invalid,
            'duplicate_row_indices': duplicate,
            'conflicting_keys': [list(k) for k in sorted(conflicts)],
            'by_language': by_language, 'human_review': review,
            'note': 'Raw agreement is not accuracy. No automatic adjudication.'}


def fixture():
    return [dict(task_id=t, reviewer_id=r, language=l, label=v) for t, r, l, v in [
        ('te-01', 'a', 'Telugu', 'pass'), ('te-01', 'b', 'Telugu', 'fail'),
        ('hi-01', 'a', 'Hindi', 'pass'), ('hi-01', 'b', 'Hindi', 'pass'),
        ('te-02', 'a', 'Telugu', 'pass'), ('te-02', 'a', 'Telugu', 'fail'),
        ('te-02', 'b', 'Telugu', 'pass')]]


def tests():
    import unittest
    class QC(unittest.TestCase):
        def test_empty(self): self.assertEqual(audit([])['by_language'], {})
        def test_agreement(self): self.assertEqual(audit(fixture())['by_language']['Hindi']['raw_pairwise_agreement'], 1)
        def test_disagreement(self): self.assertEqual(audit(fixture())['by_language']['Telugu']['raw_pairwise_agreement'], 0)
        def test_conflict(self): self.assertEqual(audit(fixture())['conflicting_keys'], [['te-02', 'a']])
        def test_invalid(self): self.assertEqual(audit([{}, None, {'task_id': 1}])['invalid_row_indices'], [0, 1, 2])
        def test_duplicate_not_independent(self):
            row = fixture()[0]
            report = audit([row, row])
            self.assertEqual(report['by_language']['Telugu']['pairs'], 0)
            self.assertEqual(report['duplicate_row_indices'], [1])
        def test_no_singleton_agreement(self): self.assertIsNone(audit([fixture()[0]])['by_language']['Telugu']['raw_pairwise_agreement'])
        def test_mixed_language(self):
            a, b = fixture()[:2]; b['language'] = 'Hindi'
            self.assertIn('MIXED', audit([a, b])['by_language'])
        def test_bad_root(self):
            with self.assertRaises(ValueError): audit({})
        def test_bad_minimum(self):
            with self.assertRaises(ValueError): audit([], 1)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(QC)
    result = unittest.TextTestRunner().run(suite)
    if not result.wasSuccessful(): raise SystemExit(1)


if __name__ == '__main__':
    if sys.argv[1:] == ['--test']:
        tests()
    else:
        if len(sys.argv) > 1:
            with open(sys.argv[1], encoding='utf-8') as stream: rows = json.load(stream)
        else: rows = fixture()
        print(json.dumps(audit(rows), indent=2, ensure_ascii=False))
