"""Parse a deliberately small shell grammar without losing quoted operators."""
from dataclasses import dataclass, field


@dataclass
class Command:
    argv: list[str] = field(default_factory=list)
    redirects: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Pipeline:
    commands: list[Command]
    background: bool
    source: str


def tokenize(line):
    tokens, word = [], []
    started, quote, i = False, None, 0
    while i < len(line):
        char = line[i]
        if char == "\x00":
            raise ValueError("NUL bytes are not allowed")
        if quote == "'":
            if char == "'":
                quote = None
            else:
                word.append(char)
        elif char == "\\":
            i += 1
            if i == len(line):
                raise ValueError("trailing escape")
            following = line[i]
            if following == "\x00":
                raise ValueError("NUL bytes are not allowed")
            if quote == '"' and following not in '\\"$`':
                word.append("\\")
            word.append(following)
            started = True
        elif quote == '"':
            if char == '"':
                quote = None
            else:
                word.append(char)
        elif char in "'\"":
            quote, started = char, True
        elif char == "#" and not started:
            break
        elif char.isspace() or char in "|&<>;" or (not started and line.startswith("2>", i)):
            if started:
                tokens.append(("word", "".join(word)))
                word, started = [], False
            if not char.isspace():
                op = char
                if line.startswith("2>", i):
                    op, i = "2>", i + 1
                if i + 1 < len(line) and line[i + 1] == op[-1] and op in (">", "2>", "|", "&", "<"):
                    op, i = op + op[-1], i + 1
                if op not in ("|", "&", "<", ">", ">>", "2>", "2>>"):
                    raise ValueError(f"unsupported operator: {op}")
                tokens.append(("operator", op))
        else:
            word.append(char)
            started = True
        i += 1
    if quote:
        raise ValueError("unclosed quote")
    if started:
        tokens.append(("word", "".join(word)))
    return tokens


def parse(line):
    tokens = tokenize(line)
    if not tokens:
        return None
    background = tokens[-1] == ("operator", "&")
    if background:
        tokens.pop()
    commands, command, i = [], Command(), 0
    while i < len(tokens):
        kind, value = tokens[i]
        if kind == "word":
            command.argv.append(value)
        elif value == "|":
            if not command.argv:
                raise ValueError("missing command before pipe")
            commands.append(command)
            command = Command()
        elif value == "&":
            raise ValueError("& is only allowed at the end of a pipeline")
        else:
            i += 1
            if i == len(tokens) or tokens[i][0] != "word" or not tokens[i][1]:
                raise ValueError(f"{value} requires a filename")
            command.redirects.append((value, tokens[i][1]))
        i += 1
    if not command.argv or not command.argv[0]:
        raise ValueError("missing command")
    if any(not item.argv[0] for item in commands):
        raise ValueError("empty command name")
    commands.append(command)
    return Pipeline(commands, background, line.strip())
