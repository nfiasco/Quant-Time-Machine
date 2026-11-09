"""Maintain repository metadata using trusted default-branch code only."""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AREAS = {'data', 'engine', 'api', 'web', 'ai', 'infra', 'research'}
PRIORITIES = {'P0', 'P1', 'P2'}
CONTEXT = 'PR metadata'


def clean(text):
    return re.sub(r'<!--[\s\S]*?-->', '', text or '').strip()


def sections(body):
    result = {}
    heading = None
    for line in clean(body).splitlines():
        match = re.match(r'^#{2,3}\s+(.+?)\s*$', line)
        if match:
            heading = match[1].lower()
            result[heading] = ''
        elif heading:
            result[heading] += line + '\n'
    return {key: value.strip() for key, value in result.items()}


def issue_numbers(body, repo):
    text = re.sub(r'```[\s\S]*?```', '', clean(body))
    found = set()
    for line in text.splitlines():
        if not re.match(r'^\s*(?:refs?|related to|part of|close[sd]?|fix(?:es|ed)?|resolve[sd]?)\b', line, re.I):
            continue
        # Only local references count; external URLs never become API destinations.
        line = re.sub(r'https://github\.com/' + re.escape(repo) + r'/issues/(\d+)', r'#\1', line)
        found.update(int(n) for n in re.findall(r'(?<![\w/])#(\d+)\b', line))
    return sorted(found)


def meaningful(value, minimum=20):
    value = clean(value).strip()
    return len(value) >= minimum and value.lower() not in {'n/a', 'none', 'todo', 'tbd'} and not re.search(r'<[^>]+>', value)


def infer_area(paths):
    areas = set()
    for path in paths:
        if path.startswith('frontend/'):
            areas.add('web')
        elif path.startswith(('backend/app/data/', 'backend/spikes/')):
            areas.add('data')
        elif path.startswith('backend/app/engine/'):
            areas.add('engine')
        elif path.startswith('backend/app/api/'):
            areas.add('api')
        elif path.startswith(('.github/', 'backend/scripts/')) or path == 'backend/Dockerfile':
            areas.add('infra')
    return next(iter(areas)) if len(areas) == 1 else None


def desired_metadata(pr, linked, paths):
    labels = {label['name'] for label in pr['labels']}
    for prefix, allowed in [('area: ', AREAS), ('priority: ', PRIORITIES)]:
        if not any(label.startswith(prefix) for label in labels):
            candidates = {label['name'] for issue in linked for label in issue['labels']
                          if label['name'] in {prefix + value for value in allowed}}
            if len(candidates) == 1:
                labels.update(candidates)
            elif prefix == 'area: ' and not candidates and (area := infer_area(paths)):
                labels.add(prefix + area)
    if any(path.startswith('doc/') or path.endswith('.md') for path in paths):
        labels.add('documentation')
    if any('/tests/' in path or path.startswith('.github/scripts/test_') for path in paths):
        labels.add('testing')
    if pr['state'] == 'closed' and not pr.get('merged_at'):
        labels.add('not merged')
    else:
        labels.discard('not merged')
    patch = {}
    if labels != {label['name'] for label in pr['labels']}:
        patch['labels'] = sorted(labels)
    milestones = {issue['milestone']['number'] for issue in linked if issue.get('milestone')}
    if not pr.get('milestone') and len(milestones) == 1:
        patch['milestone'] = next(iter(milestones))
    return patch


def validate(pr, linked, invalid_links):
    errors = []
    body = clean(pr.get('body'))
    parts = sections(body)
    if not meaningful(pr['title'], 12) or re.match(r'^(?:feature|fix|chore|docs)/', pr['title'], re.I):
        errors.append('Use a descriptive title, not a branch name or placeholder.')
    if not meaningful(parts.get('summary', parts.get('what and why', ''))):
        errors.append('Add a Summary (or What and why) section explaining the change.')
    if not meaningful(parts.get('validation', parts.get('how to test or demo', parts.get('how to test', '')))):
        errors.append('Add a Validation section with results, or explain why a check is not applicable.')
    exception = re.search(r'^No issue:\s*(.+)$', body, re.M | re.I)
    if invalid_links:
        errors.append('References must identify existing issues in this repository, not pull requests.')
    if not linked and not (exception and meaningful(exception[1])):
        errors.append('Use Refs #123 for related work, Closes #123 for complete delivery, or No issue: with a reason.')
    if not pr['assignees']:
        errors.append('Assign a responsible teammate.')
    labels = [label['name'] for label in pr['labels']]
    for prefix, allowed in [('area: ', AREAS), ('priority: ', PRIORITIES)]:
        selected = [label for label in labels if label.startswith(prefix)]
        if len(selected) != 1 or selected[0] not in {prefix + value for value in allowed}:
            errors.append(f'Select exactly one supported {prefix.strip()} label.')
    if not pr.get('milestone'):
        errors.append('Select the primary delivery milestone.')
    return errors


class GitHub:
    def __init__(self):
        self.repo = os.environ['GITHUB_REPOSITORY']
        self.root = os.environ.get('GITHUB_API_URL', 'https://api.github.com').rstrip('/')
        self.token = os.environ['GH_TOKEN']

    def request(self, path, method='GET', data=None):
        request = urllib.request.Request(
            f'{self.root}/repos/{self.repo}/{path}', method=method,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
                     'Content-Type': 'application/json', 'X-GitHub-Api-Version': '2022-11-28'},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            value = response.read()
            return json.loads(value) if value else None

    def pages(self, path):
        output = []
        for page in range(1, 31):
            batch = self.request(f'{path}?per_page=100&page={page}')
            output.extend(batch)
            if len(batch) < 100:
                return output
        raise RuntimeError('Pagination limit reached; inspect the unusually large change manually.')


def organize_pr(api, number):
    pr = api.request(f'pulls/{number}')
    # Closed history gets only the lifecycle label; never rewrite historic ownership or descriptions.
    if pr['state'] == 'closed':
        names = {label['name'] for label in pr['labels']}
        target = names - {'not merged'} if pr.get('merged_at') else names | {'not merged'}
        if target != names:
            api.request(f'issues/{number}', 'PATCH', {'labels': sorted(target)})
        return []
    api.request(f'statuses/{pr["head"]["sha"]}', 'POST', {
        'state': 'pending', 'context': CONTEXT, 'description': 'Checking current PR metadata',
    })
    linked, invalid = [], []
    for item in issue_numbers(pr.get('body'), api.repo):
        try:
            issue = api.request(f'issues/{item}')
            if 'pull_request' in issue:
                invalid.append(item)
            else:
                linked.append(issue)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                invalid.append(item)
            else:
                raise
    paths = [item['filename'] for item in api.pages(f'pulls/{number}/files')]
    patch = desired_metadata(pr, linked, paths)
    if not pr['assignees']:
        author = pr['user']['login']
        try:
            api.request('assignees/' + urllib.parse.quote(author, safe=''))
            patch['assignees'] = [author]
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
    if patch:
        api.request(f'issues/{number}', 'PATCH', patch)
        pr = api.request(f'pulls/{number}')
    errors = validate(pr, linked, invalid)
    api.request(f'statuses/{pr["head"]["sha"]}', 'POST', {
        'state': 'failure' if errors else 'success', 'context': CONTEXT,
        'description': f'{len(errors)} metadata requirement(s) need attention' if errors else 'Links, description, assignee, labels, and milestone are complete',
        'target_url': f'https://github.com/{api.repo}/actions/runs/{os.environ["GITHUB_RUN_ID"]}',
    })
    return errors


def organize_issue(api, number):
    issue = api.request(f'issues/{number}')
    if issue['state'] != 'open' or 'pull_request' in issue:
        return
    parts = sections(issue.get('body'))
    labels = {label['name'] for label in issue['labels']}
    additions = set()
    for heading, prefix, allowed in [('priority', 'priority: ', PRIORITIES), ('area', 'area: ', AREAS)]:
        value = parts.get(heading, '')
        if value in allowed and not any(label.startswith(prefix) for label in labels):
            additions.add(prefix + value)
    if additions:
        api.request(f'issues/{number}/labels', 'POST', {'labels': sorted(additions)})


def main():
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    api = GitHub()
    inputs = event.get('inputs', {})
    pr_number = inputs.get('pr_number')
    issue_number = (event.get('issue') or {}).get('number') or inputs.get('issue_number')
    if 'workflow_run' in event:
        run = event['workflow_run']
        if run['event'] != 'pull_request':
            raise ValueError('Only pull-request metadata requests are accepted.')
        candidates = run.get('pull_requests', [])
        if not candidates:
            # Fork runs may omit pull_requests. Resolve the recorded SHA using GitHub,
            # never a branch name, URL, script, or artifact supplied in the PR body.
            candidates = api.pages(f'commits/{run["head_sha"]}/pulls')
        candidates = [pr for pr in candidates
                      if pr['base']['repo']['id'] == event['repository']['id']
                      and pr['head']['sha'] == run['head_sha']]
        if not candidates:
            print('No current PR matches the recorded run; no metadata changed.')
            return False
        errors = []
        for candidate in candidates:
            errors.extend(organize_pr(api, candidate['number']))
        Path(os.environ['GITHUB_STEP_SUMMARY']).write_text(
            '\n'.join('- ' + error for error in errors) if errors else 'PR metadata is complete.'
        )
        print(f'Metadata audit completed with {len(errors)} unmet requirement(s).')
        return bool(errors)
    if bool(pr_number) == bool(issue_number):
        raise ValueError('Specify exactly one PR or issue number.')
    errors = []
    if pr_number:
        errors = organize_pr(api, int(pr_number))
    else:
        organize_issue(api, int(issue_number))
    report = '\n'.join('- ' + error for error in errors) if errors else 'Metadata is organized. Project intake and lifecycle statuses are maintained by the built-in project workflows.'
    Path(os.environ['GITHUB_STEP_SUMMARY']).write_text(report + '\n')
    print(f'Metadata audit completed with {len(errors)} unmet requirement(s).')
    return bool(errors)


if __name__ == '__main__':
    sys.exit(main())
