import difflib
import io
import sys

def diff(expected, actual):
    green = '\x1b[32m'
    red = '\x1b[31m'
    blue = '\x1b[95m'
    gray = '\x1b[90m'
    end = '\x1b[0m'
    output = []
    unified_diff = "".join(difflib.unified_diff(expected.splitlines(keepends=True), actual.splitlines(keepends=True), "Expected content", "  Actual content", n=1)).splitlines(keepends=False)

    for line in unified_diff:
        if line[0] == '-':
            output += [f"{green}{line}{end}"]
        elif line[0] == '+':
            output += [f"{red}{line}{end}"]
        elif line[0] == '@':
            output += [f"\n{blue}at line {line[line.index('+')+1:line.rindex(',')]} in actual{end}"]
        else:
            output += [f"{gray}{line}{end}"]
    output = "\n".join(output)
    return output

def old_diff(expected, actual):
    green = '\x1b[38;5;16;48;5;2m'
    red = '\x1b[38;5;16;48;5;1m'
    end = '\x1b[0m'
    output = []
    matcher = difflib.SequenceMatcher(None, expected, actual)
    for opcode, a0, a1, b0, b1 in matcher.get_opcodes():
        if opcode == "equal":
            output += [expected[a0:a1]]
        elif opcode == "insert":
            output += [green + actual[b0:b1] + end]
        elif opcode == "delete":
            output += [red + expected[a0:a1] + end]
        elif opcode == "replace":
            output += [green + actual[b0:b1] + end]
            output += [red + expected[a0:a1] + end]
    output = "".join(output)
    return output

def remove_trailing_whitespaces(string):
    return '\n'.join(s.rstrip() for s in string.split('\n'))

def cleanup_indent(string):
    min_indent = None
    for line in string.split('\n'):
        line = line.replace('\t','  ').rstrip()
        if len(line) == 0:
            continue
        count = 0
        for c in line:
            if c == ' ':
                count += 1
            else:
                break
        if min_indent is None or min_indent > count:
            min_indent = count

    if min_indent is None:
        min_indent = 0
    out = ""    
    for line in string.split('\n'):
        line = line.replace('\t','  ').rstrip()
        if len(line) == 0:
            out += '\n'
            continue
        out += line[min_indent:] + "\n"

    return out.rstrip()
