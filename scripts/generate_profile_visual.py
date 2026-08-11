#!/usr/bin/env python3
"""
Generate an animated isometric SVG of your GitHub activity and update
your profile README with it. Designed to run in a Codespace or GitHub
Actions using the `GITHUB_TOKEN` env var.

Usage:
  GITHUB_TOKEN=<token> python3 scripts/generate_profile_visual.py

This script:
 - Authenticates with GitHub using `GITHUB_TOKEN`.
 - Scans all repositories owned by the authenticated user.
 - Gathers commits, languages, stars, and contribution frequency.
 - Produces a responsive, animated SVG using only inline CSS keyframes.
 - Commits the SVG to `assets/activity.svg` in the profile repo and
   updates the profile README to display it.
"""
import os
import sys
import time
import math
import base64
import json
from typing import List, Dict

try:
    import requests
except Exception:
    print("Missing dependency 'requests'. Run: pip install -r requirements.txt")
    sys.exit(1)

API = 'https://api.github.com'


def gh_headers(token: str, extra_accept: str = None):
    h = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
    if extra_accept:
        h['Accept'] = extra_accept
    return h


def paginate(url: str, headers: dict, params: dict = None):
    params = params or {}
    items = []
    page = 1
    while True:
        params.update({'per_page': 100, 'page': page})
        r = requests.get(url, headers=headers, params=params)
        if r.status_code != 200:
            print(f'Warning: pagination fetch failed {r.status_code} {r.text}')
            break
        batch = r.json()
        if not batch:
            break
        items.extend(batch)
        if len(batch) < 100:
            break
        page += 1
        time.sleep(0.1)
    return items


def get_user(token: str) -> Dict:
    r = requests.get(f'{API}/user', headers=gh_headers(token))
    r.raise_for_status()
    return r.json()


def list_repos(token: str, username: str) -> List[Dict]:
    url = f'{API}/user/repos'
    headers = gh_headers(token)
    repos = paginate(url, headers, params={'type': 'owner', 'sort': 'pushed'})
    # Filter repos owned by the user
    owned = [r for r in repos if r.get('owner', {}).get('login', '').lower() == username.lower()]
    return owned


def get_repo_languages(token: str, owner: str, repo: str) -> Dict[str, int]:
    r = requests.get(f'{API}/repos/{owner}/{repo}/languages', headers=gh_headers(token))
    if r.status_code != 200:
        return {}
    return r.json()


def get_contributor_stats(token: str, owner: str, repo: str, username: str):
    url = f'{API}/repos/{owner}/{repo}/stats/contributors'
    headers = gh_headers(token)
    # This endpoint may return 202 while GitHub computes stats. retry a few times.
    for attempt in range(6):
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            data = r.json()
            # find contributor
            for c in data:
                author = c.get('author') or {}
                if author.get('login', '').lower() == username.lower():
                    total = c.get('total', 0)
                    weeks = c.get('weeks', [])
                    weekly = [w.get('c', 0) for w in weeks]
                    return {'total': total, 'weekly': weekly}
            return {'total': 0, 'weekly': []}
        if r.status_code == 202:
            time.sleep(1 + attempt)
            continue
        # on other errors, bail
        break
    # fallback: count commits by paging commits list (best-effort, limited)
    commits = 0
    page = 1
    while page <= 10:  # limit iterations to avoid abuse
        rr = requests.get(f'{API}/repos/{owner}/{repo}/commits', headers=gh_headers(token), params={'author': username, 'per_page': 100, 'page': page})
        if rr.status_code != 200:
            break
        batch = rr.json()
        commits += len(batch)
        if len(batch) < 100:
            break
        page += 1
        time.sleep(0.1)
    return {'total': commits, 'weekly': []}


def gather_metrics(token: str, username: str, repos: List[Dict]):
    metrics = []
    total_commits = 0
    language_agg = {}
    for r in repos:
        name = r['name']
        owner = r['owner']['login']
        stars = r.get('stargazers_count', 0)
        langs = get_repo_languages(token, owner, name)
        stats = get_contributor_stats(token, owner, name, username)
        commits = stats.get('total', 0)
        weekly = stats.get('weekly', [])
        total_commits += commits
        # accumulate languages
        for l, b in (langs or {}).items():
            language_agg[l] = language_agg.get(l, 0) + b
        metrics.append({'name': name, 'owner': owner, 'stars': stars, 'commits': commits, 'weekly': weekly, 'langs': langs})
        print(f"Scanned {name}: commits={commits} stars={stars} langs={list((langs or {}).keys())}")
    return {'repos': metrics, 'total_commits': total_commits, 'languages': language_agg}


def normalize(values, max_height=200, min_height=10):
    if not values:
        return []
    mx = max(values)
    if mx == 0:
        return [min_height for _ in values]
    out = [int(min_height + (v / mx) * (max_height - min_height)) for v in values]
    return out


def color_for_language(lang: str) -> str:
    # Basic deterministic color mapping for a handful of languages
    palette = {
        'Python': '#3572A5', 'JavaScript': '#f1e05a', 'TypeScript': '#2b7489',
        'Go': '#00ADD8', 'Rust': '#dea584', 'Java': '#b07219', 'C++': '#f34b7d',
        'C#': '#178600', 'Shell': '#89e051', 'HTML': '#e34c26', 'CSS': '#563d7c'
    }
    return palette.get(lang, '#6c757d')


def generate_svg(metrics: Dict, username: str, title='Coding Activity') -> str:
    repos = metrics['repos']
    names = [r['name'] for r in repos]
    commits = [r['commits'] for r in repos]
    heights = normalize(commits, max_height=220, min_height=20)

    width_per = 160
    svg_width = max(800, width_per * max(1, len(repos)))
    svg_height = 360

    # prepare blocks
    blocks = []
    for i, r in enumerate(repos):
        x = 60 + i * width_per
        h = heights[i]
        dominant = None
        if r['langs']:
            dominant = max(r['langs'].items(), key=lambda kv: kv[1])[0]
        color = color_for_language(dominant) if dominant else '#6c757d'
        # building footprint in isometric-like projection using simple polygons
        base_w = 60
        base_h = 40
        # polygon points for faux-isometric building
        points = {
            'front': [(x, svg_height-60), (x+base_w, svg_height-60), (x+base_w, svg_height-60-h), (x, svg_height-60-h)],
            'top': [(x, svg_height-60-h), (x+base_w, svg_height-60-h), (x+base_w/2, svg_height-60-h-base_h/2), (x-base_w/2, svg_height-60-h-base_h/2)]
        }
        blocks.append({'x': x, 'h': h, 'color': color, 'name': r['name'], 'stars': r['stars'], 'points': points})

    # inline CSS animations inside SVG
    css = f"""
    .bg{{fill:#0b1220}}
    .label{{fill:#c9d1d9;font-family:Segoe UI,Helvetica,Arial; font-size:12px;}}
    .title{{fill:#fffb; font-family:Segoe UI,Helvetica,Arial; font-weight:700; font-size:20px;}}
    .building{{filter:url(#glow); transform-origin: center bottom;}}
    @keyframes pulse {{
      0% {{ filter: drop-shadow(0 0 0px rgba(255,255,255,0)); transform: translateY(0); }}
      50% {{ filter: drop-shadow(0 10px 12px rgba(0,0,0,0.35)); transform: translateY(-6px); }}
      100% {{ filter: drop-shadow(0 0 0px rgba(255,255,255,0)); transform: translateY(0); }}
    }}
    .spin{{animation: spin 6s linear infinite; transform-origin:center center}}
    @keyframes spin {{ from {{ transform: rotate(0deg) }} to {{ transform: rotate(360deg) }} }}
    .pulse-fast{{animation: pulse 2.8s ease-in-out infinite}}
    .typing {{overflow:hidden; white-space:nowrap; border-right:3px solid rgba(255,255,255,0.15); animation: typing 4s steps(28,end) infinite, blink .8s steps(1,end) infinite;}}
    @keyframes typing {{ from {{ width: 0 }} to {{ width: 14em }} }}
    @keyframes blink {{ 50% {{ border-color: transparent }} }}
    .star{{fill:gold; opacity:0.95}}
    """

    # build svg content
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_width} {svg_height}" width="100%" height="auto">']
    svg.append(f'<style>{css}</style>')
    svg.append('<defs>')
    svg.append('<filter id="glow"><feGaussianBlur stdDeviation="4" result="coloredBlur"/><feMerge><feMergeNode in="coloredBlur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    svg.append('</defs>')
    svg.append(f'<rect width="100%" height="100%" class="bg"/>')
    svg.append(f'<text x="28" y="40" class="title">{title}</text>')
    svg.append(f'<text x="28" y="70" class="label typing">{username} — Live activity overview</text>')

    # draw each block
    for i, b in enumerate(blocks):
        # front
        pts = ' '.join([f'{int(px)},{int(py)}' for px,py in b['points']['front']])
        svg.append(f'<g class="building pulse-fast" style="animation-duration:{2.5 + (i%3)}s">')
        svg.append(f'<polygon points="{pts}" fill="{b["color"]}" opacity="0.95"/>')
        # top highlight
        tpts = ' '.join([f'{int(px)},{int(py)}' for px,py in b['points']['top']])
        svg.append(f'<polygon points="{tpts}" fill="#ffffff" opacity="0.06"/>')
        # label
        svg.append(f'<text x="{b["x"]}" y="{svg_height-30}" class="label">{b["name"][:18]}</text>')
        svg.append(f'<text x="{b["x"]}" y="{svg_height-14}" class="label">★ {b["stars"]}</text>')
        svg.append('</g>')

    # footer stats
    lang_count = len(metrics.get('languages', {}))
    total_commits = metrics.get('total_commits', 0)
    svg.append(f'<text x="28" y="{svg_height-10}" class="label">Languages: {lang_count} · Total commits: {total_commits}</text>')

    svg.append('</svg>')
    return '\n'.join(svg)


def get_file_sha(token: str, owner: str, repo: str, path: str):
    r = requests.get(f'{API}/repos/{owner}/{repo}/contents/{path}', headers=gh_headers(token))
    if r.status_code == 200:
        return r.json().get('sha')
    return None


def put_file(token: str, owner: str, repo: str, path: str, content_bytes: bytes, message: str, sha: str = None, branch: str = None):
    url = f'{API}/repos/{owner}/{repo}/contents/{path}'
    payload = {'message': message, 'content': base64.b64encode(content_bytes).decode('utf-8')}
    if sha:
        payload['sha'] = sha
    if branch:
        payload['branch'] = branch
    r = requests.put(url, headers=gh_headers(token), data=json.dumps(payload))
    if r.status_code not in (200, 201):
        print('Failed to create/update', path, r.status_code, r.text)
        return False
    return True


def update_profile_readme(token: str, owner: str, repo: str, branch: str, image_path: str):
    # fetch README
    r = requests.get(f'{API}/repos/{owner}/{repo}/readme', headers=gh_headers(token))
    readme_sha = None
    content = ''
    if r.status_code == 200:
        data = r.json()
        readme_sha = data.get('sha')
        content = base64.b64decode(data.get('content', '')).decode('utf-8')
    marker_start = '<!-- ACTIVITY:START -->'
    marker_end = '<!-- ACTIVITY:END -->'
    image_url = f'https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{image_path}'
    snippet = f"{marker_start}\n![Coding activity]({image_url})\n{marker_end}\n"
    if marker_start in content and marker_end in content:
        pre, rest = content.split(marker_start, 1)
        _, post = rest.split(marker_end, 1)
        new_content = pre + snippet + post
    else:
        new_content = snippet + '\n' + content
    return put_file(token, owner, repo, 'README.md', new_content.encode('utf-8'), 'chore: update profile activity SVG', sha=readme_sha, branch=branch)


def main():
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if not token:
        print('Error: set GITHUB_TOKEN environment variable')
        sys.exit(1)
    username = None
    try:
        user = get_user(token)
        username = user.get('login')
    except Exception:
        # In Actions the token may not allow /user; fall back to repo owner or actor
        gh_repo = os.environ.get('GITHUB_REPOSITORY')
        if gh_repo and '/' in gh_repo:
            username = gh_repo.split('/')[0]
            print(f'Using GITHUB_REPOSITORY owner as username fallback: {username}')
        else:
            actor = os.environ.get('GITHUB_ACTOR')
            if actor:
                username = actor
                print(f'Using GITHUB_ACTOR as username fallback: {username}')
    if not username:
        print('Failed to detect username; ensure token or set GITHUB_REPOSITORY/GITHUB_ACTOR env vars')
        sys.exit(1)

    print('Gathering repositories for', username)
    repos = list_repos(token, username)
    if not repos:
        print('No repos found for user')
        sys.exit(0)

    metrics = gather_metrics(token, username, repos)
    svg = generate_svg(metrics, username)

    # commit SVG into profile repo (repo with same name as username)
    profile_repo = username
    # find the profile repo object to get default branch
    profile = None
    for r in repos:
        if r['name'].lower() == profile_repo.lower():
            profile = r
            break
    if not profile:
        print(f'Profile repository {profile_repo} not found in owned repos. Creating assets locally instead.')
        out_path = os.path.join(os.getcwd(), 'assets_activity.svg')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(svg)
        print('Wrote', out_path)
        return

    branch = profile.get('default_branch', 'main')
    svg_path = 'assets/activity.svg'
    print('Uploading SVG to', f'{profile_repo}/{svg_path}')
    sha = get_file_sha(token, username, profile_repo, svg_path)
    ok = put_file(token, username, profile_repo, svg_path, svg.encode('utf-8'), 'chore: update animated activity SVG', sha=sha, branch=branch)
    if not ok:
        print('Failed to upload SVG')
        sys.exit(1)

    print('Updating README to reference the SVG')
    ok2 = update_profile_readme(token, username, profile_repo, branch, svg_path)
    if ok2:
        print('Profile README updated successfully.')
    else:
        print('Failed to update README.')


if __name__ == '__main__':
    main()
