class Token:
    def __init__(self, token_type, value, line, column):
        self.type = token_type
        self.value = value
        self.line = line
        self.column = column


class Diagnostic:
    def __init__(self, diagnostic_type, message, line, column, severity, length):
        self.type = diagnostic_type
        self.message = message
        self.line = line
        self.column = column
        self.severity = severity
        self.length = length


class Lexer:
    def __init__(self, source, sender):
        self.source = source
        if sender == "Interpreter":
            self.mode = "Tokens + Diagnostics"
        else:
            self.mode = "Diagnostics"

        self.tokens = []
        self.diagnostics = []
        self.position = 0
        self.line = 1
        self.column = 1
        self.indentation_state = 0
        self.at_line_start = True
        self.tabs = 0
        self.current_line_source = ""
        self.delimiter_stack = []
        self.spaces = 0
        self.indentation_levels = [0]
        self.valid_syntax_chars = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r",
                                   "s", "t", "u", "v", "w", "x", "y", "z", 1, 2, 3, 4, 5, 6, 7, 8, 9, "#", "'", '"', "*", "/", "-", "+", "%"]

    def tokenize_line(self, line, line_number=None):
        """Tokenize one physical source line, stopping at an unquoted # comment."""
        result = []
        line_number = self.line if line_number is None else line_number
        i = 0
        n = len(line)
        operators = ("!is", "!in", "!=", "==", "<=", ">=", "**")
        single_tokens = set("()[]{} ,;.+-*/%=<>!")

        while i < n:
            ch = line[i]
            column = i + 1
            if ch in " \t\r\n":
                i += 1
                continue
            if ch == "#":
                # A comment consumes the rest of this line, but not the newline token.
                break

            # f/F-prefixed strings and ordinary quoted strings.
            prefix = ""
            quote_index = i
            if ch in "fF" and i + 1 < n and line[i + 1] in "\"'":
                prefix = ch
                quote_index = i + 1
            if line[quote_index] in "\"'":
                quote = line[quote_index]
                start_column = column
                j = quote_index + 1
                value_chars = []
                closed = False
                while j < n:
                    current = line[j]
                    if current == "\\" and j + 1 < n:
                        value_chars.append(current)
                        value_chars.append(line[j + 1])
                        j += 2
                        continue
                    if current == quote:
                        closed = True
                        j += 1
                        break
                    if current in "\r\n":
                        break
                    value_chars.append(current)
                    j += 1
                token_value = prefix + quote + "".join(value_chars)
                if closed:
                    token_value += quote
                else:
                    self.diagnostics.append(Diagnostic(
                        "UnclosedStringError",
                        f"Unclosed string found Line {line_number} column {start_column}",
                        line_number, start_column, 8, max(1, j - i)
                    ))
                result.append((token_value, start_column))
                i = j
                continue

            # Longest operators first so x!=y and x**2 work without spaces.
            matched = next((op for op in operators if line.startswith(op, i)), None)
            if matched:
                result.append((matched, column))
                i += len(matched)
                continue

            if ch in single_tokens:
                if ch != " ":
                    result.append((ch, column))
                i += 1
                continue

            # Keep decimal numbers intact while treating other dots as path/member separators.
            if ch.isdigit():
                j = i + 1
                while j < n and line[j].isdigit():
                    j += 1
                if j + 1 < n and line[j] == "." and line[j + 1].isdigit():
                    j += 1
                    while j < n and line[j].isdigit():
                        j += 1
                result.append((line[i:j], column))
                i = j
                continue

            # Identifiers and keywords. Slash/dot are separate tokens for import paths.
            j = i + 1
            while j < n and line[j] not in " \t\r\n#()[]{} ,;.+-*/%=<>!\"'":
                j += 1
            result.append((line[i:j], column))
            i = j

        return result

    def lex(self):
        self.source_lines = self.source.splitlines(keepends=True)
        for source_line in self.source_lines:
            token_line = self.line
            self.tabs = 0
            self.spaces = 0
            for character in source_line:
                if character == "\t" and self.at_line_start:
                    self.tabs += 1
                elif character == " " and self.at_line_start:
                    self.spaces += 1
                else:
                    break

            # Empty and comment-only lines do not open or close indentation blocks.
            stripped = source_line.strip()
            is_ignored_line = not stripped or stripped.startswith("#")
            valid_indentation = self.spaces % 4 == 0
            # Newlines inside (), [] and {} continue the current expression;
            # their leading whitespace is formatting, not FACOH block indentation.
            inside_delimited_expression = bool(self.delimiter_stack)
            if not is_ignored_line and not inside_delimited_expression:
                if not valid_indentation:
                    self.diagnostics.append(Diagnostic(
                        "IndentationError", f"Invalid indentation found Line {token_line} column {self.spaces + self.tabs + 1}", token_line, self.spaces + self.tabs + 1, 8, 1))

                indentation_level = self.tabs + (self.spaces // 4)
                if valid_indentation and indentation_level > self.indentation_state:
                    while self.indentation_state < indentation_level:
                        self.indentation_state += 1
                        if self.indentation_state not in self.indentation_levels:
                            self.indentation_levels.append(self.indentation_state)
                        self.tokens.append(Token("Indent", "\t", token_line, self.spaces + self.tabs + 1))
                elif valid_indentation and indentation_level < self.indentation_state:
                    if indentation_level not in self.indentation_levels:
                        self.diagnostics.append(Diagnostic(
                            "IndentationError", f"Invalid indentation found Line {token_line} column {self.spaces + self.tabs + 1}", token_line, self.spaces + self.tabs + 1, 8, 1))
                    else:
                        while self.indentation_state > indentation_level:
                            self.indentation_state -= 1
                            self.tokens.append(Token("Dedent", "-\t", token_line, self.spaces + self.tabs + 1))

            self.at_line_start = True
            for character in source_line:
                if character == "\n":
                    if not is_ignored_line and not self.delimiter_stack:
                        self.tokens.append(
                            Token("Newline", "\n", token_line, self.column))
                    self.line += 1
                    self.column = 1
                    self.at_line_start = True
                    self.tabs = 0
                    self.spaces = 0
                elif character == "\t" or character == " ":
                    self.column += 1
                else:
                    self.at_line_start = False
                    self.column += 1
                self.position += 1

            tokenized_line = self.tokenize_line(source_line, token_line)
            for value, column in tokenized_line:
                if value in ["==", "<=", ">="]:
                    self.diagnostics.append(Diagnostic(
                        "InvalidOperatorError", f"Invalid operator found Line {token_line} column {column}", token_line, column, 8, len(value)))
                    continue

                if value == "(":
                    self.delimiter_stack.append(("(", ")", token_line, column))
                    self.tokens.append(
                        Token("LeftParen", value, token_line, column))

                elif value == ")":
                    if not self.delimiter_stack:
                        self.diagnostics.append(Diagnostic(
                            "UnexpectedDelimiterError", f"Unexpected ')' found Line {token_line} column {column}", token_line, column, 8, 1))
                    elif self.delimiter_stack[-1][1] != ")":
                        self.diagnostics.append(Diagnostic(
                            "MismatchedDelimiterError", f"Mismatched ')' found Line {token_line} column {column}", token_line, column, 8, 1))
                    else:
                        self.delimiter_stack.pop()
                        self.tokens.append(
                            Token("RightParen", value, token_line, column))

                elif value == "{":
                    self.delimiter_stack.append(("{", "}", token_line, column))
                    self.tokens.append(
                        Token("LeftBrace", value, token_line, column))

                elif value == "}":
                    if not self.delimiter_stack:
                        self.diagnostics.append(Diagnostic(
                            "UnexpectedDelimiterError", "Unexpected '}'" f"found on Line {token_line} column {column}", token_line, column, 8, 1))
                    elif self.delimiter_stack[-1][1] != "}":
                        self.diagnostics.append(Diagnostic(
                            "MismatchedDelimiterError", "Mismatched '}'" f"found on Line {token_line} column {column}", token_line, column, 8, 1))
                    else:
                        self.delimiter_stack.pop()
                        self.tokens.append(
                            Token("RightBrace", value, token_line, column))

                elif value == "[":
                    self.delimiter_stack.append(("[", "]", token_line, column))
                    self.tokens.append(
                        Token("LeftBracket", value, token_line, column))

                elif value == "]":
                    if not self.delimiter_stack:
                        self.diagnostics.append(Diagnostic(
                            "UnexpectedDelimiterError", f"Unexpected ']' found Line {token_line} column {column}", token_line, column, 8, 1))
                    elif self.delimiter_stack[-1][1] != "]":
                        self.diagnostics.append(Diagnostic(
                            "MismatchedDelimiterError", f"Mismatched ']' found Line {token_line} column {column}", token_line, column, 8, 1))
                    else:
                        self.delimiter_stack.pop()
                        self.tokens.append(
                            Token("RightBracket", value, token_line, column))

                elif value == ".":
                    self.tokens.append(
                        Token("Dot", value, token_line, column))

                elif value == ",":
                    self.tokens.append(
                        Token("Comma", value, token_line, column))

                elif value == ";":
                    self.tokens.append(
                        Token("Semicolon", value, token_line, column))

                elif (
                    len(value) > 1
                    and value[0] in ("f", "F")
                    and value[1] in ("'", '"')
                ):
                    self.tokens.append(
                        Token("FString", value, token_line, column))

                elif "\"" in value or "'" in value:
                    self.tokens.append(
                        Token("String", value, token_line, column))

                elif value == "!=":
                    self.tokens.append(
                        Token("NotEqual", value, token_line, column))

                elif value == "**":
                    self.tokens.append(
                        Token("Power", value, token_line, column))

                elif value == "!is":
                    self.tokens.append(
                        Token("IsNot", value, token_line, column))

                elif value == "!in":
                    self.tokens.append(
                        Token("NotIn", value, token_line, column))

                elif value == "is":
                    self.tokens.append(Token("Is", value, token_line, column))

                elif value == "in":
                    self.tokens.append(Token("In", value, token_line, column))

                elif value == "also":
                    self.tokens.append(
                        Token("Also", value, token_line, column))

                elif value == "or":
                    self.tokens.append(Token("Or", value, token_line, column))

                elif value == "true" or value == "false":
                    self.tokens.append(
                        Token("Boolean", value, token_line, column))

                elif value == "+":
                    self.tokens.append(
                        Token("Plus", value, token_line, column))

                elif value == "-":
                    self.tokens.append(
                        Token("Minus", value, token_line, column))

                elif value == "*":
                    self.tokens.append(
                        Token("Multiply", value, token_line, column))

                elif value == "/":
                    self.tokens.append(
                        Token("Divide", value, token_line, column))

                elif value == "=":
                    self.tokens.append(
                        Token("Equal", value, token_line, column))

                elif value == "%":
                    self.tokens.append(
                        Token("Modulo", value, token_line, column))

                elif value == "<":
                    self.tokens.append(
                        Token("Smaller", value, token_line, column))

                elif value == ">":
                    self.tokens.append(
                        Token("Bigger", value, token_line, column))

                elif value == "!":
                    self.tokens.append(Token("Not", value, token_line, column))

                else:
                    try:
                        int(value)
                        self.tokens.append(
                            Token("Number", value, token_line, column))
                    except ValueError:
                        try:
                            float(value)
                            self.tokens.append(
                                Token("Float", value, token_line, column))
                        except ValueError:
                            self.tokens.append(
                                Token("Identifier", value, token_line, column))

        for opening, closing, line, column in self.delimiter_stack:
            self.diagnostics.append(Diagnostic(
                "UnclosedDelimiterError", f"Unclosed '{opening}' found Line {line} column {column}", line, column, 8, 1))

        if self.indentation_state > 0:
            while self.indentation_state > 0:
                self.indentation_state -= 1
                self.tokens.append(
                    Token("Dedent", "-\t", self.line, self.column)
                )

        if self.mode == "Tokens + Diagnostics":
            return [self.tokens, self.diagnostics]
        else:
            return self.diagnostics


