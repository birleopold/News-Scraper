"""Spot the same advert published on several sources and show it once.

The copy kept is the one with the strongest evidence (official date first, then a read
advert PDF, then the earliest sighting); the others are listed under "Also listed at".
"""
from .classify import title_tokens

PRIORITY = {'official': 4, 'extracted': 3, 'feed': 2, 'listing': 1, 'discovery': 0}
MIN_WORDS = 4          # vague titles ("PUBLIC NOTICE") are never merged
NEAR = 0.75            # word overlap for near-identical titles with the same closing date


def _similar(a, b):
    return len(a & b) / len(a | b) >= NEAR


def mark_duplicates(records):
    """Set r['duplicate_of'] on extra copies and r['also_at'] on the copy that is kept."""
    parent = {}

    def find(i):
        while parent.setdefault(i, i) != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i

    usable = [r for r in records if r['category'] != 'Job']
    tokens = {r['id']: title_tokens(r['title']) for r in usable}
    exact, by_deadline = {}, {}
    for r in usable:
        words = tokens[r['id']]
        if len(words) < MIN_WORDS: continue
        if words in exact: parent[find(r['id'])] = find(exact[words])
        else: exact[words] = r['id']
        if r.get('effective_deadline'):
            by_deadline.setdefault((r['category'], r['effective_deadline']), []).append(r['id'])
    for ids in by_deadline.values():
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if find(a) != find(b) and _similar(tokens[a], tokens[b]): parent[find(b)] = find(a)

    groups = {}
    for r in usable:
        if r['id'] in parent: groups.setdefault(find(r['id']), []).append(r)
    for group in groups.values():
        if len(group) < 2 or len({r['source_id'] for r in group}) < 2: continue   # one source's own repeats are kept
        keep = max(group, key=lambda r: (PRIORITY.get(r['deadline_origin'], 0), bool(r.get('facts')), [-ord(c) for c in r['first_seen']]))
        keep['also_at'] = [{'source': r['source_name'], 'url': r['url']} for r in group if r is not keep]
        for r in group:
            if r is not keep: r['duplicate_of'] = keep['id']
    return records
