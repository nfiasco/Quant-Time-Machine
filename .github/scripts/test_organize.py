import copy
import os
import unittest
from unittest.mock import patch

from organize import desired_metadata, issue_numbers, organize_pr, sections, validate

REPO = 'nfiasco/Quant-Time-Machine'


def pull():
    return {'title': 'Document the delivery workflow', 'body': '## Summary\nExplain how the team organizes work and verifies completion.\n## Linked work\nRefs #109\n## Validation\nReviewed committed evidence and ran the metadata policy tests.',
            'labels': [{'name': 'area: infra'}, {'name': 'priority: P0'}], 'assignees': [{'login': 'nfiasco'}],
            'milestone': {'number': 14}, 'state': 'open', 'user': {'login': 'nfiasco'},
            'head': {'sha': 'a' * 40}, 'merged_at': None}


def issue(number=109, milestone=14, area='infra'):
    return {'number': number, 'labels': [{'name': 'area: ' + area}, {'name': 'priority: P0'}], 'milestone': {'number': milestone}}


class PolicyTests(unittest.TestCase):
    def test_references_ignore_examples_comments_and_foreign_numbers(self):
        body = '<!-- Closes #12 -->\n```\nRefs #13\n```\nRefs #109, #111\nPart of other/repo#99\nFixes https://github.com/' + REPO + '/issues/64'
        self.assertEqual(issue_numbers(body, REPO), [64, 109, 111])

    def test_comment_only_template_is_incomplete(self):
        pr = pull()
        pr['body'] = '## Summary\n<!-- Write a long explanation here. -->\n## Validation\n<!-- Record checks. -->'
        self.assertEqual(len(validate(pr, [], [])), 3)

    def test_valid_linked_work_and_small_maintenance_exception(self):
        self.assertEqual(validate(pull(), [issue()], []), [])
        pr = pull()
        pr['body'] = pr['body'].replace('Refs #109', 'No issue: Fix a spelling error in the existing deployment guide.')
        self.assertEqual(validate(pr, [], []), [])
        self.assertTrue(validate(pr, [], [99]))

    def test_inherit_only_unambiguous_missing_metadata(self):
        pr = pull()
        pr.update(labels=[], milestone=None)
        self.assertEqual(desired_metadata(pr, [issue()], []), {'labels': ['area: infra', 'priority: P0'], 'milestone': 14})
        result = desired_metadata(pr, [issue(), issue(24, 4, 'api')], [])
        self.assertNotIn('milestone', result)
        self.assertEqual(result['labels'], ['priority: P0'])

    def test_preserve_explicit_metadata_and_idempotency(self):
        pr = pull()
        self.assertEqual(desired_metadata(pr, [issue(24, 4, 'api')], []), {})
        patch_ = desired_metadata(pr, [], ['doc/project/github-workflow.md'])
        pr['labels'] = [{'name': name} for name in patch_['labels']]
        self.assertEqual(desired_metadata(pr, [], ['doc/project/github-workflow.md']), {})

    def test_invalid_duplicate_labels_and_missing_owner_milestone_fail(self):
        pr = pull()
        pr['labels'].append({'name': 'area: api'})
        pr.update(assignees=[], milestone=None)
        self.assertEqual(len(validate(pr, [issue()], [])), 3)

    def test_lifecycle_distinguishes_closed_unmerged_and_reopened(self):
        pr = pull()
        pr['state'] = 'closed'
        self.assertIn('not merged', desired_metadata(pr, [], [])['labels'])
        pr['labels'].append({'name': 'not merged'})
        pr['merged_at'] = '2026-11-09T00:00:00Z'
        self.assertNotIn('not merged', desired_metadata(pr, [], [])['labels'])
        pr.update(state='open', merged_at=None)
        self.assertNotIn('not merged', desired_metadata(pr, [], [])['labels'])

    def test_form_sections(self):
        self.assertEqual(sections('### Priority\n\nP1\n\n### Area\n\nweb'), {'priority': 'P1', 'area': 'web'})

    def test_closed_history_does_not_change_assignment_body_or_milestone(self):
        pr = pull()
        pr.update(state='closed', merged_at='2026-11-09T00:00:00Z')
        class Fake:
            repo = REPO
            def request(self, path, method='GET', data=None):
                if method != 'GET':
                    raise AssertionError('Closed merged history must remain untouched')
                return pr
        self.assertEqual(organize_pr(Fake(), 1), [])

    @patch.dict(os.environ, {'GITHUB_RUN_ID': '1'})
    def test_live_sequence_autofills_and_posts_status_without_reading_pr_code(self):
        class Fake:
            repo = REPO
            def __init__(self):
                self.pr = pull()
                self.pr.update(labels=[], milestone=None, assignees=[])
                self.calls = []
            def request(self, path, method='GET', data=None):
                self.calls.append((path, method, data))
                if path == 'pulls/1':
                    return copy.deepcopy(self.pr)
                if path == 'issues/109':
                    return issue()
                if path == 'issues/1':
                    for key, value in data.items():
                        self.pr[key] = ([{'name': x} for x in value] if key == 'labels' else
                                        [{'login': x} for x in value] if key == 'assignees' else
                                        {'number': value} if key == 'milestone' else value)
                return None
            def pages(self, path):
                assert path == 'pulls/1/files'
                return [{'filename': '.github/scripts/organize.py'}]
        fake = Fake()
        self.assertEqual(organize_pr(fake, 1), [])
        statuses = [data for path, method, data in fake.calls if path.startswith('statuses/')]
        self.assertEqual(statuses[-1]['state'], 'success')
        self.assertEqual(statuses[0]['state'], 'pending')
        self.assertFalse(any('contents/' in path for path, _, _ in fake.calls))

class WorkflowRoutingTests(unittest.TestCase):
    def run_event(self, event, fallback=None):
        import tempfile
        from pathlib import Path
        from organize import main
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'event.json'
            import json
            path.write_text(json.dumps(event))
            class Fake:
                repo = REPO
                def pages(self, endpoint):
                    self.endpoint = endpoint
                    return fallback or []
            with patch.dict(os.environ, {'GITHUB_EVENT_PATH': str(path), 'GITHUB_STEP_SUMMARY': str(Path(folder) / 'summary')}), patch('organize.GitHub', return_value=Fake()), patch('organize.organize_pr', return_value=[]) as organize:
                result = main()
                return result, [call.args[1] for call in organize.call_args_list]

    def test_run_uses_only_matching_repository_and_commit(self):
        candidate = lambda number, repo, sha: {'number': number, 'base': {'repo': {'id': repo}}, 'head': {'sha': sha}}
        event = {'repository': {'id': 1}, 'workflow_run': {'event': 'pull_request', 'head_sha': 'a' * 40,
                 'pull_requests': [candidate(7, 1, 'a' * 40), candidate(8, 2, 'a' * 40), candidate(9, 1, 'b' * 40)]}}
        self.assertEqual(self.run_event(event), (False, [7]))

    def test_fork_run_falls_back_to_commit_associations(self):
        event = {'repository': {'id': 1}, 'workflow_run': {'event': 'pull_request', 'head_sha': 'a' * 40, 'pull_requests': []}}
        candidates = [{'number': 7, 'base': {'repo': {'id': 1}}, 'head': {'sha': 'a' * 40}}]
        self.assertEqual(self.run_event(event, candidates), (False, [7]))

    def test_non_pr_run_is_rejected(self):
        with self.assertRaises(ValueError):
            self.run_event({'repository': {'id': 1}, 'workflow_run': {'event': 'push'}})


if __name__ == '__main__':
    unittest.main()
