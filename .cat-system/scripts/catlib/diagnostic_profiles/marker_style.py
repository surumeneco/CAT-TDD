"""Optional marker/style fixture profile; not a generic CAT obligation.

The field paths here are product-projection-specific. Alternative representations
need their own explicit profile; no profile is a source-bound Rule proof.
"""
from __future__ import annotations

from catlib import semantic_types
from catlib.fixture_probe import require


def _lookup(container, path):
    item=container
    for segment in path.split('.'):
        if not isinstance(item,dict) or segment not in item:
            return None
        item=item[segment]
    return item


def inspect(fixture, result):
    result.update({'external_hocon_status':'not-run',
                   'unverified':['normative-predicate-equivalence','fixture-authenticity',
                                 'effective-hocon-inheritance','approved-color-policy',
                                 'category-semantics','external-effect-and-transport']})
    inspected=_lookup(fixture,'validated')
    if inspected is None:
        result.update({'status':'inconclusive','checks':[],
                       'reason':'validated projection not present in fixture'})
        return result
    require(isinstance(inspected,dict),'validated projection must be an object')
    for field in ('api_markers','api_styles','marker_styles'):
        require(isinstance(inspected.get(field),list),
                'validated '+field+' must be an array')
    markers,styles,links=(inspected[field]
                          for field in ('api_markers','api_styles','marker_styles'))
    errors=[]
    marker_by_id={}
    for index,marker in enumerate(markers):
        require(isinstance(marker,dict),'marker record must be an object')
        marker_id=marker.get('id')
        require(isinstance(marker_id,str) and marker_id,'marker ID missing')
        if marker_id in marker_by_id:
            errors.append({'reason':'duplicate-marker-id','marker_id':marker_id,'index':index})
        else:
            marker_by_id[marker_id]=marker
    link_by_id={}
    for index,link in enumerate(links):
        require(isinstance(link,dict),'marker style link must be an object')
        target=link.get('marker_id')
        require(isinstance(target,str) and target,'marker style link missing marker_id')
        if target in link_by_id:
            errors.append({'reason':'duplicate-marker-style-link','marker_id':target,'index':index})
            continue
        link_by_id[target]=link
        marker=marker_by_id.get(target)
        if marker is None:
            errors.append({'reason':'unknown-marker-reference','marker_id':target})
            continue
        style=link.get('style')
        if not isinstance(style,dict):
            errors.append({'reason':'missing-style-object','marker_id':target})
            continue
        if not any(semantic_types.same(style,candidate) for candidate in styles):
            errors.append({'reason':'style-not-declared-in-api-styles','marker_id':target})
        marker_owner=_lookup(marker,'owner.kind')
        if (not isinstance(marker_owner,str) or not marker_owner
                or style.get('owner_kind')!=marker_owner):
            errors.append({'reason':'owner-kind-mismatch','marker_id':target})
    for target in marker_by_id:
        if target not in link_by_id:
            errors.append({'reason':'marker-without-style-link','marker_id':target})
    result.update({'status':'failed' if errors else 'passed-fixture-only',
                   'errors':errors,
                   'marker_count':len(markers),'style_count':len(styles),
                   'link_count':len(links)})
    return result
