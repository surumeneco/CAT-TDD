#!/usr/bin/env python3
"""Compatibility CLI for the optional marker/style fixture diagnostic profile.

Common Source/fixture identity and provenance are validated independently of
this particular projection. Fixture results are not CAT normative Gate proofs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from catlib.fixture_probe import RelationError, verify_identity
from catlib.diagnostic_profiles import marker_style


def inspect(source_bytes, fixture_bytes, contract):
    fixture,report=verify_identity(source_bytes,fixture_bytes,contract,
                                   expected_relation='marker-style-references/v1')
    return marker_style.inspect(fixture,report)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--contract',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    opts=parser.parse_args(argv)
    try:
        report=inspect(opts.source.read_bytes(),opts.fixture.read_bytes(),
                       json.loads(opts.contract.read_text(encoding='utf-8')))
        opts.output.parent.mkdir(parents=True,exist_ok=True)
        opts.output.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'status':report['status'],
                          'normative_status':report['normative_status'],
                          'path':str(opts.output)}))
        return 2 if report['status']=='failed' else 0
    except (OSError,ValueError,KeyError,TypeError,IndexError) as exc:
        print(json.dumps({'status':'blocked','reason':str(exc)}),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
