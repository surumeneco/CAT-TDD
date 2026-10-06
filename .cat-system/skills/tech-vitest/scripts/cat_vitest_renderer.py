#!/usr/bin/env python3
"""Vitest source renderer for concrete CAT test cases.

Owned by the tech-vitest Skill. It does not parse CAT specifications or decide test semantics.
"""
from __future__ import annotations

import json


def _ts(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def render_vitest(model, cases, binding):
    lines=[
        "// Deterministically generated from a symbolic CAT v2 model and explicit test vectors.",
        "// Draft/evidence oracles are NOT user-confirmed specifications." if model["status"] != "confirmed" else "// Based on confirmed CAT specification; implementation still requires testing.",
        "import {describe,it,expect} from 'vitest'",
        "import {createDriver} from " + _ts(binding["driver"]),
        "import {isDeepStrictEqual} from 'node:util'",
        "",
        "function accept(after: Record<string,unknown>, output: Record<string,unknown>, alternatives: Array<{state:Record<string,unknown>,output:Record<string,unknown>}>, declared: string[], setFields: string[]): boolean {",
        "  const canonical = (id: string, value: unknown) => setFields.includes(id) && Array.isArray(value) ? [...value].sort() : value;",
        "  return alternatives.some(expected => declared.every(id => Object.prototype.hasOwnProperty.call(after,id) && isDeepStrictEqual(canonical(id,after[id]),canonical(id,expected.state[id]))) && isDeepStrictEqual(output,expected.output));",
        "}",
        "",
        "describe(" + _ts(model["process"] + " CAT symbolic contract") + ", () => {",
    ]
    declared=[f["id"] for f in model["fields"] if f["role"]=="state"]
    set_fields=[f["id"] for f in model["fields"] if f["role"]=="state" and f["domain"]["type"]=="set"]
    for c in cases:
        alt=[{"state":a["state"],"output":a["output"]} for a in c["allowed"]]
        lines.extend([
            "  it(" + _ts(c["id"]) + ", async () => {",
            "    // TCE: " + c["source_tce"],
            "    const driver = createDriver()",
            "    const pre = " + _ts(c["initial_state"]) + " as Record<string,unknown>",
            "    const input = " + _ts(c["input"]) + " as Record<string,unknown>",
            "    await driver.prepare(pre, input)",
            "    const before = await driver.observeState()",
            "    for (const id of " + _ts(declared) + ") { const normalized = (v: unknown) => (" + _ts(set_fields) + " as string[]).includes(id) && Array.isArray(v) ? [...v].sort() : v; expect(normalized(before[id])).toEqual(normalized(pre[id])); }",
            "    const output = await driver.trigger(" + _ts(c["trigger"]) + ", input)",
            "    const after = await driver.observeState()",
            "    const allowed = " + _ts(alt) + " as Array<{state:Record<string,unknown>,output:Record<string,unknown>}> ",
            "    expect(accept(after, output, allowed, " + _ts(declared) + ", " + _ts(set_fields) + ")).toBe(true)",
            "  })",
        ])
    lines.append("})")
    return "\n".join(lines) + "\n"
