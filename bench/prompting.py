"""Edict prompting controls for a small, explicitly non-conclusive A/B/C study."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .edict import EdictSession, decode_tool_result


COMPACT_GUIDE = (
    "Edict is a JSON AST, not Python. A module has kind,id,name,imports,definitions. "
    "A function has kind=fn,id,name,params,effects,returnType,contracts,body. "
    "main has params=[], effects=['io'], returnType={kind:'basic',name:'Int'}. "
    "Each occurrence of every AST node needs its own unique id, even ident nodes. "
    "Expression shapes: literal={kind:'literal',id,value}, "
    "binop={kind:'binop',id,op,left,right}, ident={kind:'ident',id,name}, "
    "call={kind:'call',id,fn, args}. Use op '+'/'-'/'*' for integer arithmetic. "
    "To print an Int, use call print(call toString(intExpression)); print requires io. "
    "After printing, main's last body element is literal Int 0. "
    "if nodes require condition and then/else ARRAYS. "
    "A block evaluates its body once; it is NOT a loop. "
    "let introduces a binding; repeating let is NOT a mutable update. "
    "Never invent a loop, floor-as-loop, while/for/assign node. "
    "For a fixed small range, prefer an explicit sum of arithmetic expressions. "
    "Return only the complete JSON AST."
)


@dataclass(frozen=True)
class PromptContext:
    text: str
    source_sha256: str
    source_chars: int
    included_chars: int


def serialized(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def bounded_excerpt(value: Any, length: int) -> str:
    if length <= 0:
        return ""
    source = serialized(value)
    if len(source) <= length:
        return source
    suffix = "...[documentation excerpt truncated]"
    return source[:max(0, length - len(suffix))] + suffix


def official_context(edict: EdictSession, char_budget: int = 8000) -> PromptContext:
    """Fetch actual installed Edict MCP schema/examples once per benchmark run.

    A deterministic character budget prevents accidentally exhausting the
    context window of small local models. Full-source hashes are logged.
    """
    if char_budget < 1000:
        raise ValueError("--edict-doc-chars must be at least 1000")
    schema = decode_tool_result(edict.call("edict_schema", {}))
    examples = decode_tool_result(edict.call("edict_examples", {}))
    complete = serialized({"schema": schema, "examples": examples})
    # Include portions from both official sources even when the schema is huge.
    schema_budget = char_budget * 5 // 8
    examples_budget = char_budget - schema_budget
    material = (
        "Official Edict MCP schema (excerpt):\n" + bounded_excerpt(schema, schema_budget)
        + "\nOfficial Edict MCP examples (excerpt):\n"
        + bounded_excerpt(examples, examples_budget)
    )
    return PromptContext(
        text=material,
        source_sha256=hashlib.sha256(complete.encode("utf-8")).hexdigest(),
        source_chars=len(complete),
        included_chars=len(material),
    )
