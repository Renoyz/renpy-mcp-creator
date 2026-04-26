"""JSON extraction and repair utilities for LLM output."""


def _extract_json_block(text: str) -> str | None:
    """Extract the outermost JSON object or array from mixed text."""
    text = text.strip()
    start = -1
    for i, ch in enumerate(text):
        if ch in "{[":
            start = i
            break
    if start == -1:
        return None
    stack = []
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch == "}":
            if stack and stack[-1] == "{":
                stack.pop()
            else:
                return None  # mismatched
            if not stack:
                return text[start : i + 1]
        elif ch == "]":
            if stack and stack[-1] == "[":
                stack.pop()
            else:
                return None
            if not stack:
                return text[start : i + 1]
    return None


def _repair_json_text(text: str) -> str:
    """Attempt to repair common LLM JSON output errors.

    Fixes:
    - Extracts JSON from surrounding text
    - Removes trailing commas before ] and }
    - Strips C++-style comments
    - Normalizes stray whitespace around structural commas
    """
    block = _extract_json_block(text)
    if block is None:
        return text

    # Remove single-line comments (// ...)
    lines = []
    for line in block.splitlines():
        # Be careful not to strip // inside strings
        cleaned = []
        in_str = False
        esc = False
        for i, ch in enumerate(line):
            if esc:
                esc = False
                cleaned.append(ch)
                continue
            if ch == "\\":
                esc = True
                cleaned.append(ch)
                continue
            if ch == '"':
                in_str = not in_str
                cleaned.append(ch)
                continue
            if not in_str and ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                break
            cleaned.append(ch)
        lines.append("".join(cleaned))
    block = "\n".join(lines)

    # Remove trailing commas before } or ]
    # Use a stateful pass so we don't affect commas inside strings
    result_chars: list[str] = []
    i = 0
    while i < len(block):
        ch = block[i]
        if ch == '"':
            # Copy whole string literal
            result_chars.append(ch)
            i += 1
            esc = False
            while i < len(block):
                c2 = block[i]
                result_chars.append(c2)
                if esc:
                    esc = False
                elif c2 == "\\":
                    esc = True
                elif c2 == '"':
                    i += 1
                    break
                i += 1
            continue
        if ch == ",":
            # Peek ahead for whitespace then } or ]
            j = i + 1
            while j < len(block) and block[j] in " \t\n\r":
                j += 1
            if j < len(block) and block[j] in "}]":
                # Skip the comma (and whitespace) — just advance i to j
                i = j
                continue
        result_chars.append(ch)
        i += 1

    return "".join(result_chars)
