#!/usr/bin/env python3
"""claude-warmth: measure how warmly you write to Claude vs your human iMessage contacts.

Subcommands:
  calibrate           Build the personal warmth scale from an iMessage chat.db
  extract-claude-code Extract user messages from local Claude Code session files
  score               Compute the warmth trend and write the HTML report

All processing is local. No network calls. Stdlib only.
"""
import argparse, glob, json, math, os, re, sqlite3, statistics as st, sys
from datetime import datetime

# ---------------- markers ----------------
EMOJI = re.compile('[\U0001F300-\U0001FAFF☀-➿\U0001F000-\U0001F0FF\U0001F900-\U0001F9FF]')
PROF = re.compile(r'\b(fuck\w*|shit\w*|damn|bitch\w*|asshole|bullshit|wtf|af)\b', re.I)
LAUGH = re.compile(r'\b(l+o+l+\w*|lmao\w*|lmfao\w*|ha(ha)+|hehe+)\b', re.I)
POLITE = re.compile(r'\b(please|pls|plz|thank you|thanks|thx|ty|sorry)\b', re.I)
HEDGE = re.compile(r"\b(maybe|i think|i guess|kinda|kind of|sort of|probably|perhaps|i feel like|idk)\b", re.I)
DISCLOSE = re.compile(r"\b(i feel|i'm (so |really |kinda )?(sad|happy|stressed|anxious|excited|tired|scared|worried|nervous|upset|angry|frustrated|overwhelmed)|i miss|i love|i hate|i wish|ngl)\b", re.I)
ABBREV = re.compile(r"\b(u|ur|rn|tbh|idk|omg|wya|wyd|btw|nvm|imo|smth|bc|cuz|tmrw|ofc|fr|lowkey|highkey)\b", re.I)
DELIB = re.compile(r"\b(i'?m thinking|i think|i want to|i wanted to|should i|do you think|what do you think|what would you|how would you|is it worth|advice|recommend|opinion|i'?m trying to figure|i'?m curious|wondering|debating|torn between|does it make sense|am i|would you say|help me decide|pros and cons|i feel like)\b", re.I)

WEIGHTS = {'laughter': 1.5, 'emoji': 1.0, 'profanity': 1.0, 'abbrev': 1.0, 'disclose': 1.5,
           'all_lowercase': 0.75, 'lowercase_start': 0.75, 'hedge': 0.5,
           'ends_period': -1.5, 'polite': -0.5}
CLAMP = 2.5
MIN_CONTACT_MSGS = 100
MAX_CONTACTS = 60


def features(txts):
    n = len(txts)
    if n == 0:
        return None
    def rate(rx):
        return 100 * sum(1 for t in txts if rx.search(t)) / n
    def first_alpha_lower(t):
        for ch in t:
            if ch.isalpha():
                return ch.islower()
        return None
    fal = [x for x in (first_alpha_lower(t) for t in txts) if x is not None]
    return {
        'laughter': rate(LAUGH), 'emoji': rate(EMOJI), 'profanity': rate(PROF),
        'abbrev': rate(ABBREV), 'disclose': rate(DISCLOSE), 'hedge': rate(HEDGE),
        'polite': rate(POLITE),
        'lowercase_start': 100 * sum(fal) / len(fal) if fal else 0,
        'all_lowercase': 100 * sum(1 for t in txts if t.isascii() and t == t.lower()
                                   and any(c.isalpha() for c in t)) / n,
        'ends_period': 100 * sum(1 for t in txts if t.rstrip().endswith('.')
                                 and not t.rstrip().endswith('..')) / n,
    }


def aux_rates(txts):
    """Extra per-contact rates for the clustering chart (not part of the score)."""
    n = len(txts)
    banter = 100 * sum(1 for t in txts if LAUGH.search(t) or EMOJI.search(t)
                       or ABBREV.search(t) or PROF.search(t)) / n
    feelings = 100 * sum(1 for t in txts if DISCLOSE.search(t)) / n
    return round(banter, 2), round(feelings, 2)


class Scale:
    def __init__(self, contacts_feats):
        self.mu = {k: st.mean(f[k] for f in contacts_feats) for k in WEIGHTS}
        self.sd = {k: st.pstdev(f[k] for f in contacts_feats) or 1 for k in WEIGHTS}
        self.floor = (sum(w * self._z(0, k) for k, w in WEIGHTS.items() if w > 0)
                      + sum(w * CLAMP for k, w in WEIGHTS.items() if w < 0))
        self.hi = max(self._raw(f) for f in contacts_feats)

    def _z(self, v, k):
        return max(-CLAMP, min(CLAMP, (v - self.mu[k]) / self.sd[k]))

    def _raw(self, f):
        return sum(w * self._z(f[k], k) for k, w in WEIGHTS.items())

    def score(self, f):
        return round(100 * (self._raw(f) - self.floor) / (self.hi - self.floor), 1)

    def to_dict(self):
        return {'mu': self.mu, 'sd': self.sd, 'floor': self.floor, 'hi': self.hi}

    @classmethod
    def from_dict(cls, d):
        s = cls.__new__(cls)
        s.mu, s.sd, s.floor, s.hi = d['mu'], d['sd'], d['floor'], d['hi']
        return s


# ---------------- calibrate ----------------
def decode_attributed_body(blob):
    if not blob:
        return None
    i = blob.find(b'NSString')
    if i == -1:
        return None
    i += len(b'NSString') + 5
    b = blob[i]
    if b == 0x81:
        ln = int.from_bytes(blob[i+1:i+3], 'little'); i += 3
    elif b == 0x82:
        ln = int.from_bytes(blob[i+1:i+5], 'little'); i += 5
    else:
        ln = b; i += 1
    t = blob[i:i+ln].decode('utf-8', errors='replace')
    t = t.replace('￼', '').replace('�', '')
    return t.strip() or None


def cmd_calibrate(args):
    con = sqlite3.connect(f'file:{args.db}?mode=ro', uri=True)
    rows = con.execute('''
        SELECT h.id, m.text, m.attributedBody
        FROM message m
        JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        JOIN chat_handle_join chj ON chj.chat_id = cmj.chat_id
        JOIN handle h ON h.ROWID = chj.handle_id
        WHERE m.is_from_me = 1
          AND (m.associated_message_type IS NULL OR m.associated_message_type = 0)
          AND cmj.chat_id IN (SELECT chat_id FROM chat_handle_join
                              GROUP BY chat_id HAVING COUNT(*) = 1)''').fetchall()
    per = {}
    for handle, text, body in rows:
        t = text if text and text.strip() else decode_attributed_body(body)
        if t:
            per.setdefault(handle, []).append(t)
    per = {h: ts for h, ts in per.items() if len(ts) >= MIN_CONTACT_MSGS}
    if len(per) < 6:
        sys.exit(f'ERROR: only {len(per)} contacts with {MIN_CONTACT_MSGS}+ sent messages '
                 f'— need at least 6 to build a personal scale.')
    top = sorted(per.items(), key=lambda kv: -len(kv[1]))[:MAX_CONTACTS]
    cf = [(h, features(ts), len(ts), aux_rates(ts)) for h, ts in top]
    scale = Scale([f for _, f, _, _ in cf])
    scored = sorted(((scale.score(f), h, n, aux) for h, f, n, aux in cf), reverse=True)
    t3 = len(scored) // 3
    contacts, thresholds = [], {}
    # terciles: top third = closest, middle = friends, bottom = acquaintances
    buckets = (['closest'] * (len(scored) - 2 * t3) + ['friends'] * t3 + ['acquaintances'] * t3)
    for (s, h, n, (banter, feelings)), b in zip(scored, buckets):
        masked = h[:5] + '•••' + h[-4:] if len(h) > 9 else h
        contacts.append({'label': masked, 'score': s, 'n': n, 'bucket': b,
                         'banter': banter, 'feelings': feelings})
    for b in ['acquaintances', 'friends', 'closest']:
        thresholds[b] = round(st.median(c['score'] for c in contacts if c['bucket'] == b), 1)
    out = {'scale': scale.to_dict(), 'contacts': contacts, 'thresholds': thresholds,
           'n_contacts': len(contacts)}
    json.dump(out, open(args.out, 'w'), indent=1)
    print(f'Calibrated on {len(contacts)} contacts. Thresholds: {thresholds}')


# ---------------- extract claude code ----------------
JUNK = re.compile(r'^\s*(<|\[Request interrupted|\[Tool|Caveat:|/clear|/help|/login)', re.I)


def cmd_extract_cc(args):
    root = os.path.expanduser(args.root)
    files = glob.glob(os.path.join(root, '*', '*.jsonl'))
    convos = {}
    for fp in files:
        msgs = []
        try:
            with open(fp, encoding='utf-8') as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get('type') != 'user' or rec.get('isMeta'):
                        continue
                    m = rec.get('message', {})
                    if m.get('role') != 'user':
                        continue
                    content = m.get('content')
                    if isinstance(content, list):
                        texts = [c.get('text', '') for c in content
                                 if isinstance(c, dict) and c.get('type') == 'text']
                        content = '\n'.join(texts)
                    if not isinstance(content, str):
                        continue
                    content = content.strip()
                    if not content or JUNK.match(content) or len(content) > 4000:
                        continue
                    msgs.append({'ts': rec.get('timestamp'), 'text': content})
        except OSError:
            continue
        if msgs:
            convos[fp] = msgs
    out = [{'id': os.path.basename(fp), 'first_ts': min(m['ts'] or '' for m in ms),
            'messages': ms} for fp, ms in convos.items()]
    out.sort(key=lambda c: c['first_ts'])
    json.dump(out, open(args.out, 'w'))
    total = sum(len(c['messages']) for c in out)
    print(f'Extracted {total} user messages from {len(out)} Claude Code sessions.')


# ---------------- score ----------------
def cmd_score(args):
    state = json.load(open(args.state))
    scale = Scale.from_dict(state['scale'])
    convos = []
    if args.claude_code and os.path.exists(args.claude_code):
        for c in json.load(open(args.claude_code)):
            convos.append({'source': 'claude-code', 'first_ts': c.get('first_ts', ''),
                           'messages': [m['text'] for m in c['messages']]})
    if args.cowork and os.path.exists(args.cowork):
        for c in json.load(open(args.cowork)):
            convos.append({'source': 'cowork', 'first_ts': c.get('first_ts', ''),
                           'messages': [m for m in c['messages'] if isinstance(m, str)]})
    if not convos:
        sys.exit('ERROR: no Claude conversations found. Provide --claude-code and/or --cowork JSON.')
    dated = [c for c in convos if c['first_ts']]
    undated = [c for c in convos if not c['first_ts']]
    dated.sort(key=lambda c: c['first_ts'])
    convos = dated + undated  # undated (cowork) assumed already oldest-first
    delib = []
    for ci, c in enumerate(convos, 1):
        for m in c['messages']:
            if m.strip() and DELIB.search(m):
                delib.append((ci, m))
    n = len(delib)
    if n < 16:
        sys.exit(f'NOT_ENOUGH_DATA: only {n} deliberative messages found (need 16+). '
                 f'Use Claude more and re-run later.')
    win = 15 if n >= 60 else max(8, n // 4)
    pts = {}
    for end in range(win, n + 1):
        window = [m for _, m in delib[end-win:end]]
        pts[delib[end-1][0]] = scale.score(features(window))
    points = sorted(pts.items())
    all_claude = [m for c in convos for m in c['messages'] if m.strip()]
    overall = scale.score(features(all_claude))
    result = {'points': points, 'window': win, 'n_delib': n,
              'n_conversations': len(convos), 'n_messages': len(all_claude),
              'overall_score': overall, 'thresholds': state['thresholds'],
              'n_contacts': state['n_contacts'],
              'sources': sorted({c['source'] for c in convos})}
    json.dump(result, open(args.out, 'w'), indent=1)
    html = build_report(result, state)
    with open(args.report, 'w') as f:
        f.write(html)
    inline = _template('inline_chart_template.html').replace(
        '__DATA__', json.dumps({'points': points, 'thresholds': state['thresholds']}))
    with open(args.inline, 'w') as f:
        f.write(inline)
    print(json.dumps(result))


def cmd_merge_cowork(args):
    """Append newly extracted sessions to the cache; never touch existing entries."""
    cache = json.load(open(args.cache)) if os.path.exists(args.cache) else []
    seen = {c['id'] for c in cache}
    new = [c for c in json.load(open(args.new)) if c['id'] not in seen]
    cache += new
    json.dump(cache, open(args.cache, 'w'))
    print(f'{len(new)} new session(s) appended; cache now holds {len(cache)} sessions.')


def _template(name):
    return open(os.path.join(os.path.dirname(os.path.abspath(__file__)), name),
                encoding='utf-8').read()


def build_report(result, state):
    tpl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'report_template.html')
    tpl = open(tpl_path, encoding='utf-8').read()
    payload = {'result': result, 'contacts': state['contacts'],
               'thresholds': state['thresholds'],
               'weights': WEIGHTS, 'clamp': CLAMP,
               'min_contact_msgs': MIN_CONTACT_MSGS,
               'generated': datetime.now().strftime('%Y-%m-%d %H:%M')}
    return tpl.replace('__DATA__', json.dumps(payload))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('calibrate')
    c.add_argument('--db', required=True)
    c.add_argument('--out', default='warmth_state.json')
    c.set_defaults(fn=cmd_calibrate)
    e = sub.add_parser('extract-claude-code')
    e.add_argument('--root', default='~/.claude/projects')
    e.add_argument('--out', default='claude_messages.json')
    e.set_defaults(fn=cmd_extract_cc)
    s = sub.add_parser('score')
    s.add_argument('--state', default='warmth_state.json')
    s.add_argument('--claude-code', default='claude_messages.json')
    s.add_argument('--cowork', default='cowork_messages.json')
    s.add_argument('--out', default='warmth_result.json')
    s.add_argument('--report', default='claude-warmth-report.html')
    s.add_argument('--inline', default='warmth_inline.html')
    s.set_defaults(fn=cmd_score)
    m = sub.add_parser('merge-cowork')
    m.add_argument('--cache', default='cowork_messages.json')
    m.add_argument('--new', required=True)
    m.set_defaults(fn=cmd_merge_cowork)
    args = p.parse_args()
    args.fn(args)


if __name__ == '__main__':
    main()
