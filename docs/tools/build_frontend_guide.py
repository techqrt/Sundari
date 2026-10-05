#!/usr/bin/env python3
"""Builds the Sunndari frontend API guide.

    venv/bin/python docs/tools/build_frontend_guide.py

Outputs
  docs/sundari-frontend-api-guide.html   complete static page (open it in any browser, or host it anywhere)
  docs/tools/_artifact_fragment.html     the same page without <html>/<head>/<body>, for publishing as an Artifact

The API reference is generated from the live OpenAPI schema (drf-spectacular) so it cannot drift from the code;
"NEW" badges come from diffing routes against the previous release commit. Narrative text lives in guide_content.py.
"""
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import date

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.dirname(__file__))
import guide_content as C                                          # noqa: E402

PY = os.path.join(ROOT, 'venv', 'bin', 'python')
esc = html.escape


# ───────────────────────── schema + route diff ─────────────────────────
def load_schema():
    out = os.path.join(tempfile.mkdtemp(), 'schema.json')
    subprocess.run([PY, 'manage.py', 'spectacular', '--file', out, '--format', 'openapi-json'], cwd=ROOT, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return json.load(open(out))


def routes_at(commit):
    def show(path):
        r = subprocess.run(['git', 'show', f'{commit}:{path}'], cwd=ROOT, capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else ''
    root = show('sunndari/urls.py')
    routes = set()
    for prefix, module in re.findall(r"path\('([^']*)',\s*include\('([^']+)'\)\)", root):
        for sub in re.findall(r"path\('([^']*)'", show(module.replace('.', '/') + '.py')):
            routes.add('/' + prefix + sub)
    return routes


class Schema:
    def __init__(self, doc):
        self.doc, self.components = doc, doc['components']['schemas']

    def resolve(self, node):
        while node and '$ref' in node:
            node = self.components[node['$ref'].split('/')[-1]]
        return node or {}

    def flatten(self, node):
        node = self.resolve(node)
        if 'allOf' in node:
            merged = {'type': 'object', 'properties': {}, 'required': []}
            for part in node['allOf']:
                part = self.flatten(part)
                merged['properties'].update(part.get('properties', {}))
                merged['required'] += part.get('required', [])
            return merged
        return node

    def example(self, node, depth=0):
        node = self.flatten(node)
        if depth > 6:
            return {}
        if 'example' in node:
            return node['example']
        if 'enum' in node:
            return next((e for e in node['enum'] if e not in (None, '')), node['enum'][0])
        t, fmt = node.get('type'), node.get('format', '')
        if t == 'object' or 'properties' in node:
            return {k: self.example(v, depth + 1) for k, v in node.get('properties', {}).items()}
        if t == 'array':
            return [self.example(node.get('items', {}), depth + 1)]
        if t == 'integer':
            return node.get('default', node.get('minimum') or 1)
        if t == 'number':
            return 100.0
        if t == 'boolean':
            return True
        if fmt == 'date':
            return '2026-10-12'
        if fmt == 'date-time':
            return '2026-10-12T10:00:00+00:00'
        if fmt == 'time':
            return '10:00:00'
        if fmt == 'email':
            return 'name@example.com'
        if fmt == 'decimal' or node.get('pattern', '').startswith('^-?\\d'):
            return '100.00'
        if t == 'string':
            return node.get('default') or 'string'
        return None

    def fields(self, node):
        node = self.flatten(node)
        required = set(node.get('required', []))
        rows = []
        for name, prop in node.get('properties', {}).items():
            pr = self.flatten(prop)
            kind = pr.get('type', 'object')
            if kind == 'array':
                kind = f"array of {self.flatten(pr.get('items', {})).get('type', 'object')}"
            if pr.get('format'):
                kind += f" ({pr['format']})"
            notes = []
            if 'enum' in pr:
                notes.append('one of ' + ', '.join(f'<code>{esc(str(e))}</code>' for e in pr['enum'] if e not in (None, '')))
            for key, label in (('minLength', 'min length'), ('maxLength', 'max length'), ('minimum', 'min'), ('maximum', 'max'), ('maxItems', 'max items')):
                if key in pr:
                    notes.append(f'{label} {pr[key]}')
            if pr.get('nullable'):
                notes.append('may be null')
            if 'default' in pr and pr['default'] not in ('', None):
                notes.append(f"default <code>{esc(json.dumps(pr['default']))}</code>")
            if pr.get('description'):
                notes.append(esc(pr['description']))
            rows.append((name, kind, name in required, '; '.join(notes)))
        return rows


# ───────────────────────── small renderers ─────────────────────────
def slug(method, path):
    return method.lower() + '-' + re.sub(r'[^a-z0-9]+', '-', path.lower()).strip('-')


def role_of(path):
    if path in C.ROLE_OVERRIDES:
        return C.ROLE_OVERRIDES[path]
    for prefix, role in C.ROLE_PREFIXES:
        if path.startswith(prefix):
            return role
    return 'Any logged-in user'


def role_chip(role):
    plain = re.sub(r'<[^>]+>', '', role)
    if plain.startswith('Public'):
        return 'Public', 'any'
    if plain.startswith('Admin'):
        return 'Admin', 'admin'
    if plain.startswith('Customer or artist'):
        return 'Customer · Artist', 'any'
    if plain.startswith('Artist (own data)'):
        return 'Artist · public via artist_id', 'artist'
    if plain.startswith('Artist'):
        return 'Artist', 'artist'
    if plain.startswith('Customer'):
        return 'Customer', 'customer'
    if plain.startswith('The owning artist'):
        return 'Owner · Admin', 'artist'
    return 'Any signed-in', 'any'


_TOKEN = re.compile(r'("(?:\\.|[^"\\])*")(\s*:)?')


def hl_json(text):
    def repl(m):
        if m.group(2):
            return f'<span class="k">{m.group(1)}</span>{m.group(2)}'
        return f'<span class="s">{m.group(1)}</span>'
    return _TOKEN.sub(repl, esc(text, quote=False))


def sample(summary, text, open_=False, jsonish=True):
    body = hl_json(text) if jsonish else esc(text, quote=False)
    return f'<details class="sample"{" open" if open_ else ""}><summary>{summary}</summary><pre class="code">{body}</pre></details>'


def fields_table(rows, first='Field', flag='Required'):
    body = ''.join(f'<tr><td class="fname">{esc(n) if not n.startswith("<") else n}</td><td class="ftype">{t}</td><td class="freq">{"required" if r is True else ("optional" if r is False else r)}</td><td class="fdesc">{nt}</td></tr>' for n, t, r, nt in rows)
    return f'<div class="tw"><table class="fields"><tr><th>{first}</th><th>Type</th><th>{flag}</th><th>Notes</th></tr>{body}</table></div>'


STD_LIST_PARAMS = {'value', 'values', 'page_num', 'limit', 'sort_by', 'sort_order', 'filter_key', 'filter_value', 'search_key', 'from_date', 'to_date', 'artist_id'}


def render_card(sch, method, path, op, new_routes, anchors):
    m = method.upper()
    is_new = path in new_routes
    change = C.CHANGED.get(path)
    changed_badge = bool(change) and not is_new
    role_text = role_of(path)
    label, cls = role_chip(role_text)
    params = op.get('parameters', [])
    paginated = 'page_num' in {p['name'] for p in params}
    own_params = [p for p in params if not (paginated and p['name'] in STD_LIST_PARAMS)]
    content = (op.get('requestBody') or {}).get('content', {})
    file_spec = C.FILE_FIELDS.get(path)
    multipart = bool(file_spec) or bool(content and 'application/json' not in content)
    body_schema = next(iter(content.values()))['schema'] if content else None
    summary = (op.get('description') or '').strip()

    tags = [f'<span class="chip chip-{cls}">{esc(label)}</span>']
    if is_new:
        tags.append('<span class="badge badge-new">new</span>')
    if changed_badge:
        tags.append('<span class="badge badge-chg">changed</span>')
    if changed_badge and change[0] == 'breaking':
        tags.append('<span class="badge badge-brk">breaking</span>')
    if multipart:
        tags.append('<span class="badge badge-mp">multipart</span>')
    out = [f'<div class="endpoint{" is-new" if is_new else ""}" id="{slug(method, path)}" data-search="{esc((m + " " + path + " " + summary).lower())}">',
           f'<div class="ep-head"><span class="verb v-{m.lower()}">{m}</span><span class="ep-path">{esc(path)}</span><span class="ep-tags">{"".join(tags)}</span></div>',
           '<div class="ep-body">']
    if summary:
        out.append(f'<p class="ep-summary">{esc(summary)}</p>')
    out.append(f'<p class="ep-who"><b>Who:</b> {role_text}' + ('' if label == 'Public' else ' · <b>Header:</b> <code>Authorization: Bearer &lt;access_token&gt;</code>') + '</p>')
    if path in C.ENDPOINT_NOTES:
        out.append(f'<div class="callout"><b class="h">Note</b><p>{C.ENDPOINT_NOTES[path]}</p></div>')
    if change:
        head = 'What changed' if changed_badge else 'Contract notes (differs from older drafts)'
        out.append(f'<div class="callout warn"><b class="h">{head}</b><p>{C.link_endpoints(change[1], anchors)}</p></div>')
    if paginated:
        out.append('<p class="ep-who">Paginated list. Supports the <a href="#std-list">standard list parameters</a>.</p>')
    if own_params:
        rows = []
        for p in own_params:
            s = sch.flatten(p.get('schema', {}))
            kind = s.get('type', 'string') + (f" ({s['format']})" if s.get('format') else '')
            note = esc(p.get('description', ''))
            if 'enum' in s:
                note += ' one of ' + ', '.join(f'<code>{e}</code>' for e in s['enum'])
            rows.append((f'<span>{esc(p["name"])}</span>', kind, bool(p.get('required')), note))
        out.append('<h4 class="sub">Query parameters</h4>' + fields_table(rows))
    if body_schema or file_spec:
        rows = [(f'<span>{esc(n)}</span>', t, r, nt) for n, t, r, nt in (sch.fields(body_schema) if body_schema else [])]
        for fname, ftype, freq, fnote in (file_spec or []):
            rows.append((f'<span>{esc(fname)}</span>', f'file · {ftype}', freq if freq != 'yes' else True, fnote))
        if rows:
            out.append(f'<h4 class="sub">Request body <small>{"multipart/form-data" if multipart else "application/json"}</small></h4>' + fields_table(rows))
            if not multipart and body_schema:
                req = f'{m} {path}\nAuthorization: Bearer <access_token>\nContent-Type: application/json\n\n{json.dumps(sch.example(body_schema), indent=2)}'
                out.append(sample('Request sample', req, jsonish=False))
    ok = next((r for c, r in op.get('responses', {}).items() if c.startswith('2')), {})
    resp_schema = next(iter(ok['content'].values())).get('schema') if 'content' in ok else None
    returns = C.RETURNS.get(path)
    message = ok.get('description', 'Success')
    if returns is not None:
        env = {'status': True, 'message': C.MESSAGES.get(path, message if message != 'Success' else 'Data fetched successfully'), 'data': returns}
        out.append(sample('Response sample', json.dumps(env, indent=2, ensure_ascii=False)))
    elif resp_schema:
        env = sch.example(resp_schema)
        if isinstance(env, dict) and set(env) == {'data'}:
            env = {'status': True, 'message': 'Data fetched successfully', **env}
        out.append(sample('Response sample', json.dumps(env, indent=2, ensure_ascii=False)))
        flat = sch.flatten(resp_schema)
        data_node = sch.flatten(flat.get('properties', {}).get('data', {})) if flat.get('properties') else {}
        rows = sch.fields(data_node)
        if rows and not any(n == 'data' for n, *_ in rows):
            out.append('<h4 class="sub">Fields of <code>data</code></h4>' + fields_table([(f'<span>{esc(n)}</span>', t, ('always' if r else 'may be absent'), nt) for n, t, r, nt in rows], flag='Present'))
    else:
        out.append(sample('Response sample', json.dumps({'status': True, 'message': message}, indent=2)))
    for key, text in C.FIELD_NOTES.get(path, []):
        out.append(f'<p class="ep-who"><code>{esc(key)}</code> · {text}</p>')
    out.append('</div></div>')
    return '\n'.join(out)


# ───────────────────────── narrative transforms ─────────────────────────
_LI = re.compile(r'^\s*<b>(.*?)</b>\s*(?:—|-|:)?\s*(.*)$', re.S)


def ol_to_steps(match):
    items = re.findall(r'<li>(.*?)</li>', match.group(1), re.S)
    steps = []
    for n, item in enumerate(items, 1):
        m = _LI.match(item)
        title, text = (m.group(1), m.group(2)) if m else ('', item)
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
        head = f'<h4>{title}</h4>' if title else ''
        steps.append(f'<div class="walk-step"><div class="walk-num">{n}</div><div class="walk-body">{head}<div class="walk-text">{text}</div></div></div>')
    return ''.join(steps)


def tidy(h):
    h = h.replace('class="tablewrap"', 'class="tw"')
    h = re.sub(r'(?<!<div class="tw">)(<table class="kv">.*?</table>)', r'<div class="tw">\1</div>', h, flags=re.S)
    h = h.replace('<pre class="plain">', '<pre class="code">')
    h = re.sub(r'<div class="callout">', '<div class="callout">', h)
    return h


def split_flows(flows_html, anchors_linker):
    """FLOWS -> (intro html, [(id, title, body html)]) with each flow as its own section."""
    pattern = re.compile(r'<section class="flow" id="(flow-[a-z-]+)"><h3>(.*?)</h3>(.*?)</section>', re.S)
    intro = pattern.sub('', flows_html)
    flows = []
    for fid, title, body in pattern.findall(flows_html):
        body = re.sub(r'<ol(?: class="[^"]*")?>(.*?)</ol>', ol_to_steps, body, flags=re.S)
        diagram = C.FLOW_DIAGRAMS.get(fid)
        if diagram:
            body = f'<div class="pipeline-wrap"><pre class="mermaid">{diagram}</pre></div>' + body
        flows.append((fid, re.sub(r'^\d+\s*·\s*', '', title), tidy(anchors_linker(body))))
    return tidy(anchors_linker(intro)), flows


CSS = open(os.path.join(os.path.dirname(__file__), 'guide_style.css'), encoding='utf-8').read()
JS = open(os.path.join(os.path.dirname(__file__), 'guide_script.js'), encoding='utf-8').read()


def build():
    sch = Schema(load_schema())
    paths = sch.doc['paths']
    new_routes = set(paths) - routes_at(C.BASE_COMMIT)
    ops = [(p, m, o) for p, v in paths.items() for m, o in v.items() if m in ('get', 'post', 'put', 'delete', 'patch') and 'api' not in o.get('tags', ['api'])]
    by_tag = {}
    for p, m, o in ops:
        by_tag.setdefault(o['tags'][0], []).append((p, m, o))
    anchors = {(m.upper(), p): slug(m, p) for p, m, _ in ops}
    missing = [r for r in C.referenced_endpoints() if r not in anchors]
    if missing:
        raise SystemExit(f'Narrative references endpoints that do not exist: {missing}')
    leftover = sorted(set(by_tag) - {t for _, tags in C.TAG_GROUPS for t in tags})
    if leftover:
        raise SystemExit(f'Tags missing from TAG_GROUPS: {leftover}')
    bad = [p for p in C.CHANGED if p not in paths]
    if bad:
        raise SystemExit(f'CHANGED lists unknown paths: {bad}')
    link = lambda t: C.link_endpoints(t, anchors)
    n_new = sum(1 for p, m, o in ops if p in new_routes)
    n_changed = sum(1 for p, m, o in ops if p in C.CHANGED and p not in new_routes)

    # ---- API sections
    api_sections, toc_api = [], []
    for title, tags in C.TAG_GROUPS:
        gid = 'api-' + re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
        blocks, group_new = [], False
        for tag in tags:
            if tag not in by_tag:
                continue
            cards = '\n'.join(render_card(sch, m, p, o, new_routes, anchors) for p, m, o in sorted(by_tag[tag], key=lambda x: (x[0], x[1])))
            tid = re.sub(r'[^a-z0-9]+', '-', tag.lower()).strip('-')
            has_new = any(p in new_routes for p, _, _ in by_tag[tag])
            group_new = group_new or has_new
            blocks.append(f'<h3 id="{tid}">{esc(tag)} <span class="count">{len(by_tag[tag])}</span></h3>{cards}')
            toc_api.append((tid, tag, has_new))
        api_sections.append(f'<section id="{gid}" class="apisec"><h2>{esc(title)}</h2>{"".join(blocks)}</section>')

    # ---- narrative
    changes_html = tidy(link(C.changes_html(ops, new_routes, sch)))
    flows_intro, flows = split_flows(C.FLOWS, link)
    flow_sections = ''.join(f'<section id="{fid}"><h2>{esc(title)}</h2>{body}</section>' for fid, title, body in flows)

    toc = ['<a href="#overview">What\'s new</a>', '<a href="#start">Start here: checklist</a>', '<a href="#changes">Changes in detail</a>', '<a href="#conventions">Conventions</a>',
           '<div class="grp">Flows</div>'] + [f'<a href="#{fid}"><span class="dot"></span>{esc(t)}</a>' for fid, t, _ in flows]
    for title, tags in C.TAG_GROUPS:
        toc.append(f'<div class="grp">API · {esc(title)}</div>')
        toc += [f'<a href="#{tid}">{"<span class=dot></span>" if nw else ""}{esc(tag)}</a>' for tid, tag, nw in toc_api if tag in tags]
    toc += ['<div class="grp">Reference</div>', '<a href="#enums">Values &amp; limits</a>', '<a href="#errors">Errors</a>']

    body = f"""
<div class="shell">
  <aside class="toc">
    <div class="toc-brand"><span class="mark"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M4 12h10M4 17h16"/></svg></span><span>SUNNDARI API</span></div>
    <input id="q" type="search" placeholder="Search endpoints…" autocomplete="off" aria-label="Search endpoints">
    <div id="count" class="qcount"></div>
    <nav>{"".join(toc)}</nav>
  </aside>
  <main class="main">
    <div class="masthead">
      <span class="eyebrow">Frontend integration guide · security and feature release</span>
      <h1>Sunndari API</h1>
      <p class="sub">What is new, what changed, how each flow works and every endpoint with its fields and limits. Written for the artist app, the customer app and the admin screens.</p>
      <div class="meta-row">
        <div class="meta-chip"><span class="k">Base URL</span><span class="v">{{BASE_URL}}</span></div>
        <div class="meta-chip"><span class="k">Auth</span><span class="v">Bearer JWT · one session per user</span></div>
        <div class="meta-chip"><span class="k">Format</span><span class="v">JSON · multipart · camelCase out, snake_case in</span></div>
        <div class="meta-chip"><span class="k">Roles</span><span class="v">customer · artist · admin</span></div>
        <div class="meta-chip"><span class="k">This release</span><span class="v">{n_new} new · {n_changed} changed · {len(ops)} total</span></div>
      </div>
    </div>

    <section id="overview">
      <h2>What's new in this release</h2>
      <p class="section-dek">Everything below is measured against the previous release (commit <code>{C.BASE_COMMIT[:7]}</code>). New features arrive together with a security hardening pass, so a few existing calls behave differently. The API reference is generated from the live OpenAPI schema, so request fields, limits and response shapes always match the code.</p>
      <div class="tw"><table class="flow-table">
        <tr><th>New</th><th>Changed or tightened</th></tr>
        <tr><td>
          <span class="badge badge-new">new</span> Artist onboarding: registration fields, photos, specialities, work samples, ID-proof KYC, bank account, review feedback<br>
          <span class="badge badge-new">new</span> Add-ons, service areas and travel charges, package extras and photos, brands<br>
          <span class="badge badge-new">new</span> Reschedule requests (artist proposes, customer answers)<br>
          <span class="badge badge-new">new</span> Reviews with replies, customer ratings, My Clients with notes, insights, share link and public page<br>
          <span class="badge badge-new">new</span> Support tickets with attachments, forgot/reset password, OTP-verified email/phone change, Terms/Privacy/Contact info
        </td><td>
          <span class="badge badge-brk">breaking</span> profile of other users, email/phone editing, KYC documents<br>
          <span class="badge badge-chg">changed</span> booking totals are server-computed (add-ons, travel), buffers block neighbouring time<br>
          <span class="badge badge-chg">changed</span> payments are idempotent and can never overpay; cancelling a paid booking requests a real refund<br>
          <span class="badge badge-chg">changed</span> stricter approval, stricter passwords, inactive accounts get a 403
        </td></tr>
      </table></div>
      <div class="callout new"><b class="h">Why this matters for the UI</b><p>Several screens need work before this release can ship: sign-in recovery, the KYC form, the artist registration checklist, the booking time picker, payment retry handling and every place that read another user's profile. The <a href="#start">checklist</a> lists them in priority order.</p></div>
      {tidy(link(C.OVERVIEW))}
    </section>

    <section id="start"><h2>Start here: checklist</h2><p class="section-dek">In priority order. Items 1 to 4 can break screens you already have.</p>{tidy(link(C.START_HERE))}</section>

    <section id="changes"><h2>Changes in detail</h2><p class="section-dek">Breaking changes first, then behaviour changes, then the complete lists of new and changed endpoints.</p>{changes_html}</section>

    <section id="conventions"><h2>Conventions</h2><p class="section-dek">The same rules apply to every endpoint: trailing slashes, the response envelope, naming, dates and pagination.</p>{tidy(C.CONVENTIONS)}</section>

    <section id="flows"><h2>Flows, step by step</h2>{flows_intro}</section>
    {flow_sections}

    {"".join(api_sections)}

    <section id="enums"><h2>Values and limits</h2><p class="section-dek">The exact strings and limits the server uses.</p>{tidy(C.ENUMS)}</section>
    <section id="errors"><h2>Errors</h2><p class="section-dek">Every failure uses one of these shapes.</p>{tidy(C.ERRORS)}</section>
    <footer>Generated {date.today().isoformat()} from the live OpenAPI schema · NEW is measured against commit {C.BASE_COMMIT[:7]} · regenerate with <code>python docs/tools/build_frontend_guide.py</code></footer>
  </main>
</div>
"""
    body = body.replace('{BASE_URL}', '&#123;BASE_URL&#125;')
    head = ('<title>Sunndari API Guide</title>\n'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Public+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&family=JetBrains+Mono:wght@400;500;600&display=swap">\n'
            f'<style>\n{CSS}\n</style>\n')
    fragment = head + body + f'\n<script>\n{JS}\n</script>\n'
    open(os.path.join(os.path.dirname(__file__), '_artifact_fragment.html'), 'w', encoding='utf-8').write(fragment)
    full = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n'
            + head + '</head><body>\n' + body + f'\n<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>\n<script>\n{JS}\ntry{{mermaid.initialize({{startOnLoad:true,theme:window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"default"}})}}catch(e){{}}\n</script>\n</body></html>\n')
    out = os.path.join(ROOT, 'docs', 'sundari-frontend-api-guide.html')
    open(out, 'w', encoding='utf-8').write(full)
    print(f'wrote {out} ({len(full) // 1024} KB) and the artifact fragment ({len(fragment) // 1024} KB): endpoints={len(ops)} new={n_new} changed={n_changed}')


if __name__ == '__main__':
    build()
