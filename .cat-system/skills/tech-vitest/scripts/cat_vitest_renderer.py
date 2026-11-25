#!/usr/bin/env python3
"""Vitest source renderer for concrete CAT test cases.

Owned by the tech-vitest Skill. It does not parse CAT specifications or decide test semantics.
"""
from __future__ import annotations

import json


def _ts(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def render_vitest(model, cases, binding):
    if any('observations' in case for case in cases):
        raise ValueError('Vitest renderer cannot transport observed test environment witnesses')
    lines=[
        "// Deterministically generated from a symbolic CAT v2 model and explicit test vectors.",
        "// Draft/evidence oracles are NOT user-confirmed specifications." if model["status"] != "confirmed" else "// Based on confirmed CAT specification; implementation still requires testing.",
        "import {describe,it,expect} from 'vitest'",
        "import {createDriver} from " + _ts(binding["driver"]),
        "import {isDeepStrictEqual} from 'node:util'",
        "",
        "function sameCATSet(observed: unknown, expected: unknown): boolean {",
        "  if (!Array.isArray(observed) || !Array.isArray(expected) || observed.length !== expected.length) return false;",
        "  const hasDuplicate = (items: unknown[]) => items.some((item,index) => items.slice(index+1).some(other => isDeepStrictEqual(item,other)));",
        "  if (hasDuplicate(observed) || hasDuplicate(expected)) return false;",
        "  const used = new Set<number>();",
        "  for (const item of observed) {",
        "    const i = expected.findIndex((candidate,index) => !used.has(index) && isDeepStrictEqual(item, candidate));",
        "    if (i < 0) return false;",
        "    used.add(i);",
        "  }",
        "  return true;",
        "}",
        "function equalCATValue(id: string, observed: unknown, expected: unknown, setFields: string[]): boolean {",
        "  if (setFields.includes(id) && Array.isArray(observed) && Array.isArray(expected)) return sameCATSet(observed,expected);",
        "  return isDeepStrictEqual(observed,expected);",
        "}",
        "function accept(after: Record<string,unknown>, output: Record<string,unknown>, alternatives: Array<{state:Record<string,unknown>,output:Record<string,unknown>}>, declared: string[], stateSetFields: string[], outputSetFields: string[]): boolean {",
        "  return alternatives.some(expected => declared.every(id => Object.prototype.hasOwnProperty.call(after,id) && equalCATValue(id,after[id],expected.state[id],stateSetFields)) && Object.keys(output).length === Object.keys(expected.output).length && Object.keys(output).every(id => Object.prototype.hasOwnProperty.call(expected.output,id) && equalCATValue(id,output[id],expected.output[id],outputSetFields)));",
        "}",
        "",
        "describe(" + _ts(model["process"] + " CAT symbolic contract") + ", () => {",
    ]
    uses_undefined=any(
        any(v=={'$cat_presence':'undefined'} for v in c['input'].values())
        for c in cases)
    if uses_undefined:
        # This helper is injected only for the explicit JS-undefined binding;
        # a JSON sentinel must never be delivered as an ordinary input value.
        lines[-1:-1]=[
            "function decodeUndefinedInput(raw: Record<string,unknown>): Record<string,unknown> {",
            "  const decoded: Record<string,unknown> = {...raw};",
            "  for (const id of Object.keys(decoded)) {",
            "    const marker = decoded[id];",
            "    if (marker !== null && typeof marker === 'object' && !Array.isArray(marker)",
            "        && Object.keys(marker as Record<string,unknown>).length === 1",
            "        && (marker as Record<string,unknown>)[\"$cat_presence\"] === \"undefined\") {",
            "      decoded[id] = undefined;",
            "    }",
            "  }",
            "  return decoded;",
            "}",
            "",
        ]
    multi_transport=binding.get('output_operation_transport')=='js-driver-provides/v1'
    uses_frames=multi_transport and any('output_operation' in c or 'output_operations' in c for c in cases)
    if uses_frames:
        lines[-1:-1]=[
            "function flattenProvidedOperations(observed: unknown, fields: Record<string,string[]>): Record<string,unknown> {",
            "  const isRecord = (value: unknown): value is Record<string,unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);",
            "  const own = (value: Record<string,unknown>, id: string) => Object.prototype.hasOwnProperty.call(value,id);",
            "  if (!isRecord(observed) || Object.keys(observed).length !== Object.keys(fields).length) throw new Error('CAT provider operation set mismatch');",
            "  const entries: Array<[string,unknown]> = [];",
            "  for (const operation of Object.keys(fields)) {",
            "    if (!own(observed,operation)) throw new Error('CAT provider operation missing: '+operation);",
            "    const frame = observed[operation];",
            "    if (!isRecord(frame)) throw new Error('CAT provider frame must be a field record: '+operation);",
            "    for (const [id,value] of Object.entries(frame)) {",
            "      if (!fields[operation].includes(id)) throw new Error('CAT output belongs to a different or undeclared PI: '+id);",
            "      entries.push([id,value]);",
            "    }",
            "  }",
            "  return Object.fromEntries(entries);",
            "}",
            "",
        ]
    declared=[f["id"] for f in model["fields"] if f["role"]=="state"]
    def is_set_domain(domain):
        # A source-bound named alias and nullable wrapper preserve the same
        # underlying set comparison contract. Unproven unions are not guessed.
        while domain.get('type') in ('reference','nullable'):
            if domain['type']=='reference':
                if not domain.get('resolved'):return False
                domain=domain['of']
            else:
                domain=domain['of']
        return domain.get('type')=='set'
    set_fields=[f["id"] for f in model["fields"] if f["role"]=="state" and is_set_domain(f["domain"])]
    output_set_fields=[f["id"] for f in model["fields"] if f["role"]=="output" and is_set_domain(f["domain"])]
    for c in cases:
        alt=[{"state":a["state"],"output":a["output"]} for a in c["allowed"]]
        undefined_fields=sorted(
            id_ for id_,v in c['input'].items() if v=={'$cat_presence':'undefined'})
        if undefined_fields:
            input_lines=[
                "    expect((driver as {undefinedTransport?: string}).undefinedTransport).toBe(\"js-undefined/v1\")",
                "    const rawInput = " + _ts(c["input"]) + " as Record<string,unknown>",
                "    const input = decodeUndefinedInput(rawInput)",
            ]
            for id_ in undefined_fields:
                input_lines += [
                    "    expect(Object.prototype.hasOwnProperty.call(input, " + _ts(id_) + ")).toBe(true)",
                    "    expect(input[" + _ts(id_) + "]).toBeUndefined()",
                ]
        else:
            input_lines=["    const input = " + _ts(c["input"]) + " as Record<string,unknown>"]
        provide_operation=c.get('output_operation')
        provide_operations=c.get('output_operations') or ([provide_operation] if provide_operation is not None else [])
        if provide_operations and multi_transport:
            owners={op['id']:op['source_pi'] for op in model.get('pi_operations',[]) if op['direction']=='provide'}
            fields={operation:sorted(f['id'] for f in model['fields']
                                     if f['role']=='output' and f.get('source_pi')==owners[operation])
                    for operation in provide_operations}
            output_lines=[
                '    expect((driver as {outputOperationTransport?: string}).outputOperationTransport).toBe("js-driver-provides/v1")',
                '    expect(typeof (driver as {triggerProvidedOperations?: unknown}).triggerProvidedOperations).toBe("function")',
                "    const observed = await (driver as {triggerProvidedOperations:(operations: string[], trigger: string, input: Record<string,unknown>) => Promise<unknown>}).triggerProvidedOperations(" +
                _ts(provide_operations) + "," + _ts(c["trigger"]) + ",input)",
                "    const output = flattenProvidedOperations(observed, " + _ts(fields) + ")",
            ]
        elif 'output_operations' in c:
            raise ValueError('multiple provider operations require js-driver-provides/v1')
        elif provide_operation is not None:
            output_lines=[
                '    expect((driver as {outputOperationTransport?: string}).outputOperationTransport).toBe("js-driver-provide/v1")',
                '    expect(typeof (driver as {triggerProvidedOperation?: unknown}).triggerProvidedOperation).toBe("function")',
                "    const output = await (driver as {triggerProvidedOperation:(operation: string, trigger: string, input: Record<string,unknown>) => Promise<Record<string,unknown>>}).triggerProvidedOperation(" +
                _ts(provide_operation) + "," + _ts(c["trigger"]) + ",input)",
            ]
        else:
            output_lines=["    const output = await driver.trigger(" + _ts(c["trigger"]) + ", input)"]
        lines.extend([
            "  it(" + _ts(c["id"]) + ", async () => {",
            "    // TCE: " + c["source_tce"],
            "    const driver = createDriver()",
            "    const pre = " + _ts(c["initial_state"]) + " as Record<string,unknown>",
            *input_lines,
            "    await driver.prepare(pre, input)",
            "    const before = await driver.observeState()",
            "    for (const id of " + _ts(declared) + ") { expect(equalCATValue(id,before[id],pre[id]," + _ts(set_fields) + ")).toBe(true); }",
            *output_lines,
            "    const after = await driver.observeState()",
            "    const allowed = " + _ts(alt) + " as Array<{state:Record<string,unknown>,output:Record<string,unknown>}> ",
            "    expect(accept(after, output, allowed, " + _ts(declared) + ", " + _ts(set_fields) + ", " + _ts(output_set_fields) + ")).toBe(true)",
            "  })",
        ])
    lines.append("})")
    return "\n".join(lines) + "\n"
