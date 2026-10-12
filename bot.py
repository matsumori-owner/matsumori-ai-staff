"""麺処 松もり / daily automated post scheduler.

A GitHub Actions job runs around 02:13 JST, generates today's JPEG, commits it
into a PUBLIC repository, then schedules one post per Buffer channel at 09:00 JST.
API keys are supplied ONLY as GitHub Actions Secrets.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, date, time as dtime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from render import render, JP_DAYS

JST = ZoneInfo('Asia/Tokyo')
URL = 'https://api.buffer.com'
CHANNELS = {'twitter': 'X', 'instagram': 'Instagram', 'googlebusiness': 'Google Business Profile'}
HASHTAGS = ('#麵処松もり\n#ラーメン\n#らーめん\n#ラーメン好きな人と繋がりたい')


def target_day(forced: str | None = None) -> date:
    return date.fromisoformat(forced) if forced else datetime.now(JST).date()


def status_for(day: date) -> str:
    changes = json.loads(Path('overrides.json').read_text(encoding='utf-8'))
    status = changes.get(day.isoformat(), {}).get('status')
    if status is None:
        status = 'open' if day.weekday() in (2, 5) else 'closed'
    if status not in ('open', 'closed'):
        raise ValueError('Invalid override status. Use open or closed.')
    return status


def menu_for(day: date) -> tuple[list[str], list[str]]:
    """Regular menu plus dated seasonal additions; unknown entries fail safely."""
    conf = json.loads(Path('menu.json').read_text(encoding='utf-8'))
    noodles = conf['regular_noodles']
    rice = conf['regular_rice']
    if not isinstance(noodles, list) or not isinstance(rice, list):
        raise ValueError('Menu must contain lists of items')
    if any(not isinstance(x, str) or not x.strip() for x in noodles + rice):
        raise ValueError('Menu items must be nonempty strings')
    seasonal = conf.get('seasonal', [])
    for item in seasonal:
        if not isinstance(item, dict) or not all(k in item for k in ('name','start','end')):
            raise ValueError('Seasonal menu requires name, start, end')
        start, end = date.fromisoformat(item['start']), date.fromisoformat(item['end'])
        if end < start:
            raise ValueError('Seasonal menu end before start')
        if start <= day <= end:
            noodles.append(item['name'] + '【季節限定】')
    return noodles, rice


def caption(day: date, status: str, service: str) -> str:
    heading = f'{day.month}月{day.day}日（{JP_DAYS[day.weekday()]}）'
    if status == 'open':
        noodles, rice = menu_for(day)
        menu_text = '\\n'.join(noodles) + '\\n\\n' + '\\n'.join(rice)
        if service == 'twitter':
            text = (f'{heading} 本日営業！\\n'
                    '11:00〜15:00（L.O.14:30）\\n\\n'
                    + '／'.join(noodles) + '\\n'
                    + '／'.join(rice) + '\\n\\n'
                    '混雑・受付状況はInstagramストーリーズで確認できます。')
        elif service == 'googlebusiness':
            text = (f'本日は{heading}、\\n11:00〜15:00で営業いたします。\\n'
                    '（L.O.14:30）\\n\\n【本日の提供メニュー】\\n\\n'
                    + menu_text + '\\n\\n'
                    '営業中の混雑状況・受付状況は、公式Instagram（@md_matsumori）の'
                    'ストーリーズで随時お知らせしています。\\n\\n'
                    '山までお越しいただく前に、ぜひご確認ください。')
        else:
            text = (f'本日は{heading}、\\n11:00〜15:00で営業いたします。\\n'
                    '（L.O.14:30）\\n\\n本日のメニューは\\n\\n'
                    + menu_text + '\\n\\nです。\\n\\n'
                    '営業中の混雑状況・受付状況は、\\n'
                    'Instagramストーリーズで\\n随時お知らせしています。\\n\\n'
                    '山までお越しいただく前に、\\nぜひご確認ください。')
    else:
        text = (f'【{heading}】\\n\\n本日、麺処 松もりは定休日です。\\n\\n'
                '次回営業日に、また皆さまにお会いできることを楽しみにしております。')
    if service != 'googlebusiness':
        text += '\\n\\n' + HASHTAGS
    if service == 'twitter' and len(text) > 280:
        raise ValueError('X caption exceeds 280 characters; adjust menu rather than truncating')
    return text

def graphql(api_key: str, query: str, variables: dict | None = None) -> dict:
    response = requests.post(URL, json={'query':query, 'variables':variables or {}},
                             headers={'Authorization': f'Bearer {api_key}',
                                      'Content-Type':'application/json'}, timeout=35)
    response.raise_for_status()
    obj = response.json()
    if obj.get('errors'):
        raise RuntimeError('Buffer GraphQL error: ' + '; '.join(e['message'] for e in obj['errors']))
    return obj.get('data') or {}


def find_channels(key: str) -> tuple[str, dict]:
    data = graphql(key, '''query { account { organizations { id name } } }''')
    orgs = data['account']['organizations']
    if len(orgs) != 1:
        raise RuntimeError(f'Expected 1 Buffer organization, found {len(orgs)}. Stop for safety.')
    org_id = orgs[0]['id']
    data = graphql(key, '''query ($org: OrganizationId!) {
      channels(input:{organizationId:$org}) {
        id name displayName service isDisconnected isLocked isQueuePaused
      }
    }''', {'org': org_id})
    result = {}
    for c in data['channels']:
        service = c['service']
        if service not in CHANNELS:
            continue
        if service in result:
            raise RuntimeError(f'Multiple {service} accounts connected. Stop to avoid misposting.')
        if c['isDisconnected'] or c['isLocked'] or c['isQueuePaused']:
            raise RuntimeError(f'Channel {service} not ready: reconnect/unlock/unpause in Buffer.')
        result[service] = c
    if set(result) != set(CHANNELS):
        raise RuntimeError(f'Expected 3 channels {list(CHANNELS)}; found {list(result)}')
    return org_id, result


def previously_scheduled(key: str, org_id: str, channel_id: str, message: str,
                         due_at: str) -> bool:
    # Query Buffer itself, so retry after a workflow failure does not double-post.
    q = '''query ($org: OrganizationId!) {
      posts(first:100, input: {organizationId:$org}) {
        edges { node { id channelId text dueAt status } }
      }
    }'''
    data = graphql(key, q, {'org':org_id})
    for edge in data['posts']['edges']:
        post = edge['node']
        if (post['channelId'] == channel_id and post['text'] == message
            and post.get('dueAt') and post['dueAt'][:16] == due_at[:16]):
            # In an error state the post exists: manual review rather than duplicate it.
            print('Existing Buffer post:', post['id'], post.get('status'))
            return True
    return False


def publish_one(key: str, channel_id: str, service: str, text: str,
                due_at: str, image_url: str) -> dict:
    metadata = {}
    if service == 'instagram':
        metadata = {'instagram': {'type':'post', 'shouldShareToFeed':True}}
    elif service == 'googlebusiness':
        metadata = {'google': {'type':'whats_new'}}
    post_input = {
        'channelId':channel_id,
        'text':text,
        'schedulingType':'automatic',
        'mode':'customScheduled',
        'dueAt':due_at,
        'assets':[{'image': {'url':image_url}}],
        'aiAssisted':False,
        'needsApproval':False,
    }
    if metadata:
        post_input['metadata'] = metadata
    q = '''mutation ($input: CreatePostInput!) {
      createPost(input:$input) {
        ... on PostActionSuccess { post { id dueAt status } }
        ... on MutationError { message }
      }
    }'''
    result = graphql(key, q, {'input':post_input})['createPost']
    if result.get('message'):
        raise RuntimeError(f'Buffer rejected {service} post: {result["message"]}')
    if not result.get('post',{}).get('id'):
        raise RuntimeError(f'Unexpected response from Buffer for {service}: {result}')
    return result['post']


def check_media_available(url: str):
    for i in range(10):
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200 and resp.headers.get('Content-Type','').startswith('image/'):
                return
        except requests.RequestException:
            pass
        time.sleep(7)
    raise RuntimeError('Image is not publicly available at GitHub raw URL yet: ' + url)


def asset_path(day: date) -> Path:
    return Path('public/posts') / f'{day.isoformat()}.jpg'


def make_image(day: date) -> Path:
    status = status_for(day)
    path = asset_path(day)
    render(day, status, path)
    print('Rendered:', path, '| status:', status)
    return path


def schedule(day: date, dry_run: bool = False) -> None:
    if Path('PAUSE').exists():
        print('PAUSE file found. No posts will be sent to Buffer.')
        return
    status = status_for(day)
    due = datetime.combine(day, dtime(9, 0), tzinfo=JST).astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if due < now:
        raise RuntimeError('09:00 JST has already passed. Never schedule outdated daily notice.')
    due_at = due.isoformat(timespec='milliseconds').replace('+00:00','Z')
    repo = os.environ.get('GITHUB_REPOSITORY','')
    if not repo or '/' not in repo:
        raise RuntimeError('GITHUB_REPOSITORY missing; run from GitHub Actions.')
    branch = os.environ.get('GITHUB_REF_NAME', 'main')
    from urllib.parse import quote
    image_url = f'https://raw.githubusercontent.com/{repo}/{quote(branch, safe="")}/{asset_path(day).as_posix()}'
    if dry_run:
        print('DRY RUN (nothing posted):', due_at, image_url)
        for service in CHANNELS:
            print(f'[{CHANNELS[service]}]\n{caption(day,status,service)}\n')
        return
    api_key = os.environ.get('BUFFER_API_KEY','')
    if not api_key:
        raise RuntimeError('BUFFER_API_KEY is missing in GitHub Actions Secrets.')
    check_media_available(image_url)
    org_id, channels = find_channels(api_key)
    logs = Path('logs') / f'{day.isoformat()}.json'
    logs.parent.mkdir(exist_ok=True)
    results = {}
    failures = []
    for service, c in channels.items():
        message = caption(day,status,service)
        try:
            if previously_scheduled(api_key,org_id,c['id'],message,due_at):
                results[service] = {'result':'already_exists', 'channel':c['name'], 'at':due_at}
                continue
            post = publish_one(api_key,c['id'],service,message,due_at,image_url)
            results[service] = {'result':'scheduled', 'id':post['id'], 'channel':c['name'], 'at':post['dueAt']}
        except Exception as exc:
            failures.append(service)
            results[service] = {'result':'failed', 'error':str(exc)}
        print(service, results[service])
        logs.write_text(json.dumps({'date':day.isoformat(),'status':status,'results':results},
                                   ensure_ascii=False, indent=2) + '\n',encoding='utf-8')
    if failures:
        raise RuntimeError('Failed channels: ' + ', '.join(failures) + '. Check Actions logs / Buffer dashboard.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('command', choices=['prepare','schedule','preview'])
    ap.add_argument('--date', help='YYYY-MM-DD (otherwise today in Japan)')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    os.chdir(Path(__file__).resolve().parent)
    day = target_day(args.date)
    if args.command == 'prepare':
        make_image(day)
    elif args.command == 'preview':
        path = Path('preview') / f'{day.isoformat()}.jpg'
        render(day,status_for(day),path)
        print('Preview image:',path)
        for svc in CHANNELS:
            print(CHANNELS[svc], '\n',caption(day,status_for(day),svc))
    else:
        schedule(day, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
