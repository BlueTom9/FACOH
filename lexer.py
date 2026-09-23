class TokenTypes:
    def __init__(self):
        self.structure_types = ["Indent", "Dedent", "Newline"]
        self.value_types = ["String", "Number",
                            "Boolean", "Float", "Identifier"]
        self.arithmetic_types = ["Plus", "Minus",
                                 "Multiply", "Divide", "Power", "Modulo"]
        self.comparison_types = ["Bigger", "Smaller", "Equal",
                                 "NotEqual", "Also", "Or", "Is", "IsNot",
                                 "In", "NotIn", "Not"]
        self.syntax_types = ["Semicolon", "Comma", "LeftParen", "RightParen",
                             "LeftBrace", "RightBrace", "LeftBracket",
                             "RightBracket"]


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

    def tokenize_line(self, line):
        result = []
        current = ""
        current_start_column = None
        paren = ["(", ")", "[", "]", "{", "}", ",", ";", "-"]
        inside_string = False
        opening_quote = None
        current_column = 0
        while current_column < len(line):
            character = line[current_column]
            column = current_column + 1
            try:
                if character == '"':
                    if not inside_string:
                        inside_string = True
                        opening_quote = '"'
                        current_start_column = column
                    else:
                        if character == opening_quote:
                            result.append(
                                (opening_quote + current + opening_quote, current_start_column))
                            current = ""
                            current_start_column = None
                            inside_string = False
                            opening_quote = None
                elif character == "'":
                    if not inside_string:
                        inside_string = True
                        opening_quote = "'"
                        current_start_column = column
                    else:
                        if character == opening_quote:
                            result.append(
                                (opening_quote + current + opening_quote, current_start_column))
                            current = ""
                            current_start_column = None
                            inside_string = False
                            opening_quote = None
                elif inside_string:
                    current += character
                elif character == "!":
                    if current:
                        result.append((current, current_start_column))
                        current = ""
                        current_start_column = None
                    if line[current_column:current_column + 3] == "!is":
                        result.append(("!is", column))
                        current_column += 3
                        continue
                    elif line[current_column:current_column + 3] == "!in":
                        result.append(("!in", column))
                        current_column += 3
                        continue
                    elif line[current_column:current_column + 2] == "!=":
                        result.append(("!=", column))
                        current_column += 2
                        continue
                    else:
                        result.append(("!", column))
                elif character in paren:
                    if current:
                        result.append((current, current_start_column))
                        current = ""
                        current_start_column = None
                    result.append((character, column))
                elif character == " " or character == "\n" or character == "\t":
                    if current:
                        result.append((current, current_start_column))
                        current = ""
                        current_start_column = None
                else:
                    if current == "":
                        current_start_column = column
                    current += character
            except ValueError:
                pass
            current_column += 1
        if current:
            result.append((current, current_start_column))
        if inside_string:
            self.diagnostics.append(Diagnostic(
                "UnclosedStringError", f"Unclosed string found Line {self.line} column {current_start_column}", self.line, current_start_column, 8, len(current) + 1))
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

            valid_indentation = self.spaces % 4 == 0
            if not valid_indentation and source_line.strip():
                self.diagnostics.append(Diagnostic(
                    "IndentationError", f"Invalid indentation found Line {token_line} column {self.spaces + self.tabs + 1}", token_line, self.spaces + self.tabs + 1, 8, 1))

            indentation_level = self.tabs + (self.spaces // 4)
            if valid_indentation and indentation_level > self.indentation_state:
                while self.indentation_state < indentation_level:
                    self.indentation_state += 1
                    if self.indentation_state not in self.indentation_levels:
                        self.indentation_levels.append(
                            self.indentation_state)
                    self.tokens.append(
                        Token("Indent", "\t", token_line, self.spaces + self.tabs + 1))
            elif valid_indentation and indentation_level < self.indentation_state:
                if indentation_level not in self.indentation_levels:
                    self.diagnostics.append(Diagnostic(
                        "IndentationError", f"Invalid indentation found Line {token_line} column {self.spaces + self.tabs + 1}", token_line, self.spaces + self.tabs + 1, 8, 1))
                else:
                    while self.indentation_state > indentation_level:
                        self.indentation_state -= 1
                        self.tokens.append(
                            Token("Dedent", "-\t", token_line, self.spaces + self.tabs + 1))

            self.at_line_start = True
            for character in source_line:
                if character == "\n":
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

            tokenized_line = self.tokenize_line(source_line)
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

                elif value == ",":
                    self.tokens.append(
                        Token("Comma", value, token_line, column))

                elif value == ";":
                    self.tokens.append(
                        Token("Semicolon", value, token_line, column))

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
