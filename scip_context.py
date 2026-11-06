"""Inspect a SCIP protobuf symbol index, using the published wire schema."""
from pathlib import Path


def varint(data, offset):
    value = shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, offset
        shift += 7
    raise ValueError("Invalid varint")


def fields(data):
    pos = 0
    while pos < len(data):
        tag, pos = varint(data, pos)
        number, wire = tag >> 3, tag & 7
        if number == 0:
            raise ValueError("Invalid protobuf field")
        if wire == 0:
            value, pos = varint(data, pos)
        elif wire == 2:
            size, pos = varint(data, pos)
            if pos + size > len(data):
                raise ValueError("Truncated protobuf field")
            value, pos = data[pos:pos + size], pos + size
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            if pos + size > len(data):
                raise ValueError("Truncated fixed field")
            value, pos = data[pos:pos + size], pos + size
        else:
            raise ValueError("Unsupported protobuf wire type")
        yield number, wire, value


def line_number(occurrence):
    line = None
    for number, wire, value in fields(occurrence):
        if number == 1 and wire == 2:
            line, _ = varint(value, 0)
        elif number in (8, 9) and wire == 2:
            line = next((v for k, w, v in fields(value) if k == 1 and w == 0), line)
    return line


def occurrences(path):
    index_path = Path(path)
    if index_path.stat().st_size > 100_000_000:
        raise ValueError("SCIP index exceeds size limit")
    for number, wire, document in fields(index_path.read_bytes()):
        if number != 2 or wire != 2:
            continue
        relative, found = "", []
        for n, w, field in fields(document):
            if n == 1 and w == 2:
                relative = field.decode("utf-8", "replace")
            elif n == 2 and w == 2:
                symbol = ""
                role = 0
                for k, t, value in fields(field):
                    if k == 2 and t == 2:
                        symbol = value.decode("utf-8", "replace")
                    elif k == 3 and t == 0:
                        role = value
                line = line_number(field)
                if symbol and line is not None:
                    found.append((symbol, line, bool(role & 1)))
        if relative.endswith(".cs"):
            for symbol, line, definition in found:
                yield relative, symbol, line, definition


def extract_symbol_context(index, root, target="Contributor", limit=9000):
    """Return snippets for exact SCIP symbol matches, preferring definitions."""
    root = Path(root).resolve()
    all_hits = list(occurrences(index))
    target_symbols = {symbol for _, symbol, _, defined in all_hits
                      if defined and symbol.endswith((target + "#", target + "."))}
    matches = [(path, symbol, line, defined) for path, symbol, line, defined in all_hits
               if symbol in target_symbols]
    matches.sort(key=lambda hit: (not hit[3], hit[0], hit[2]))
    parts, remaining = [], limit
    for path, symbol, line, defined in matches:
        file = (root / path).resolve()
        if root not in file.parents or not file.is_file():
            continue
        source = file.read_text(encoding="utf-8", errors="replace").splitlines()
        start, end = max(0, line - 5), min(len(source), line + 7)
        snippet = "\n".join(f"{i + 1}: {source[i]}" for i in range(start, end))
        piece = f"### {path}:{line + 1} ({'definition' if defined else 'reference'})\n{snippet}\n"
        if len(piece) > remaining:
            break
        parts.append(piece)
        remaining -= len(piece)
    return "\n".join(parts), len(matches), len(target_symbols)


def index_diagnostics(index, target="Contributor"):
    """Publish counts and bounded names only, never private source text."""
    hits = list(occurrences(index))
    definitions = [(path, symbol) for path, symbol, _, defined in hits if defined]
    class_defs = [(path, symbol) for path, symbol in definitions if symbol.endswith("#")]
    target_hits = [(path, symbol, defined) for path, symbol, _, defined in hits
                   if target.lower() in symbol.lower()]
    return {"occurrences": len(hits), "definitions": len(definitions),
            "class_definitions": len(class_defs), "documents": len({p for p, _, _, _ in hits}),
            "target_name_occurrences": len(target_hits),
            "example_class_names": sorted({sym.rsplit("/", 1)[-1].rstrip("#")
                                           for _, sym in class_defs})[:20]}
