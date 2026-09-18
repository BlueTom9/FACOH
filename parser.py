class Diagnostic:
    def __init__(self, diagnostic_type, message, line, column, severity, length):
        self.type = diagnostic_type
        self.message = message
        self.line = line
        self.column = column
        self.severity = severity
        self.length = length


class Parser:
    def __init__(self, lexer_output, sender):
        self.tokens = lexer_output[0]
        self.diagnostics = lexer_output[1]
        if sender == "Interpreter":
            self.mode = "Diagnostics + Output"
        else:
            self.mode = "Diagnostic"
        self.position = 0
        self.eof_reached = False
        self.token_types = ["Indent", "Dedent", "Newline", "String", "Number", "Boolean", "Float", "Identifier", "Plus", "Minus", "Multiply", "Divide", "Power", "Modulo", "Bigger", "Smaller",
                            "Equal", "NotEqual", "Also", "Or", "Is", "IsNot", "In", "NotIn", "Not", "Semicolon", "Comma", "LeftParen", "RightParen", "LeftBrace", "RightBrace", "LeftBracket", "RightBracket"]
        self.function_names = []
        self.function_parameters = []
        self.errors = ["MissingSemicolonError", "IndentationError", "MissingIdentifier", "MissingParameterError", "NamingError", "MissingParamaters",
                       "MissingParamater", "MissingClosingParenthesis", "MissingClosingParen", "MissingExpression", "MissingClosingBracket", "MissingEquals", "MissingClosingBrace"]

    def peek(self):
        try:
            token = self.tokens[self.position]
            return [token.type, token.value, token.line, token.column]
        except IndexError:
            self.eof_reached = True

    def advance(self):
        current_token = self.peek()
        self.position += 1
        return current_token

    def match(self, token_type):
        current_token = self.peek()
        if current_token[0] == token_type:
            self.advance()
            return True
        return False

    def expect(self, expection, error_type):
        current_token = self.peek()
        if current_token[0] == expection:
            self.advance()
            return True
        else:
            self.diagnostics.append(Diagnostic(
                error_type, f"missing {expection} Line {current_token[2]}, {current_token[3]}", current_token[2], current_token[3], 8, 1))
            return False

    def parse_statement(self):
        current_token = self.peek()
        if current_token[1] == "if":
            self.parse_if()
        elif current_token[1] == "while":
            self.parse_while()
        elif current_token[1] == "for":
            self.parse_for()
        elif current_token[1] == "func":
            self.parse_func()
        elif current_token[1] == "try":
            self.parse_try()
        elif current_token[1] == "fileoc":
            self.parse_fileoc()
        elif current_token[1] == "use" or current_token[1] == "from" or current_token[1] == "var":
            self.parse_use_from_var()
        elif current_token[1] in ["break", "del", "pass", "return"]:
            self.parse_simple_statement()
        elif current_token[0] in [
            "String", "Number", "Boolean", "Float", "Identifier",
            "LeftParen", "LeftBracket", "LeftBrace", "Minus", "Not"
        ]:
            self.parse_expression(True)

    def parse_if(self):
        self.advance()
        self.parse_expression()
        self.expect("Semicolon", "MissingSemicolonError")
        self.parse_block()

        current_token = self.peek()
        if current_token and current_token[1] == "else":
            self.advance()
            self.expect("Semicolon", "MissingSemicolonError")
            self.parse_block()

    def parse_while(self):
        self.advance()
        self.parse_expression()
        self.expect("Semicolon", "MissingSemicolonError")
        self.parse_block()

    def parse_for(self):
        self.advance()
        if self.expect("Identifier", "MissingIdentifier") and self.expect("In", "MissingParameterError"):
            self.parse_expression()
            if self.expect("Semicolon", "MissingSemicolonError"):
                self.parse_block()
            current_token = self.peek()
            if current_token and current_token[1] == "else":
                self.advance()
                self.expect("Semicolon", "MissingSemicolonError")
                self.parse_block()

    def parse_func(self):
        self.advance()
        func_name = self.parse_function_name()
        self.parse_function_parameters(func_name)
        self.expect("Semicolon", "MissingSemicolonError")
        self.parse_block()

    def parse_function_name(self):
        func_name_token = self.peek()
        if func_name_token[0] == "Identifier":
            self.function_names.append(func_name_token[1])
            self.advance()
            return func_name_token[1]
        else:
            self.diagnostics.append(Diagnostic(
                "NamingError", f"Function in {func_name_token[2]} column {func_name_token[3]}, has an invalid name", func_name_token[2], func_name_token[3], 7, len(func_name_token[1])))
            return None

    def parse_function_parameters(self, func_name):
        current_token = self.peek()
        if current_token[0] == "LeftParen":
            self.advance()
            current_token = self.peek()
            parameters = []
            if current_token[0] == "RightParen":
                self.advance()
            else:
                current_token = self.peek()
                self.expect("Identifier", "MissingParamaters")
                parameters.append(current_token[1])
                current_token = self.peek()
                while current_token[0] == "Comma":
                    self.advance()
                    current_token = self.peek()
                    self.expect("Identifier", "MissingParamater")
                    parameters.append(current_token[1])
                    current_token = self.peek()
                self.expect("RightParen", "MissingClosingParenthesis")
            self.function_parameters.append({
                "name": func_name,
                "parameters": parameters
            })

    def parse_try(self):
        self.advance()
        if self.expect("Semicolon", "MissingSemicolonError"):
            self.parse_block()
            current_token = self.peek()
            while current_token[1] == "caught":
                self.advance()
                current_token = self.peek()
                if current_token[0] == "Identifier":
                    self.advance()
                    current_token = self.peek()

                if current_token[1] == "var":
                    self.advance()
                    self.expect("Identifier", "MissingIdentifier")
                self.expect("Semicolon", "MissingSemicolonError")
                self.parse_block()
                current_token = self.peek()
            if current_token[1] == "else":
                self.advance()
                self.expect("Semicolon", "MissingSemicolonError")
                self.parse_block()
                current_token = self.peek()

            if current_token[1] == "finally":
                self.advance()
                self.expect("Semicolon", "MissingSemicolonError")
                self.parse_block()

    def parse_fileoc(self):
        self.advance()
        self.parse_expression()

        current_token = self.peek()
        if current_token[1] == "var":
            self.advance()
            self.expect("Identifier", "MissingIdentifier")

        self.expect("Semicolon", "MissingSemicolonError")
        self.parse_block()

    def parse_simple_statement(self):
        current_token = self.peek()
        if current_token[1] in ["break", "pass"]:
            self.advance()
        elif current_token[1] == "del":
            self.advance()
            self.parse_expression()
        elif current_token[1] == "return":
            self.advance()
            current_token = self.peek()
            if current_token[0] not in ["Newline", "Indent", "Dedent"]:
                self.parse_expression()

    def parse_use_from_var(self):
        current_token = self.peek()

        if current_token[1] == "use":
            self.advance()
            self.expect("Identifier", "MissingIdentifier")

            current_token = self.peek()
            if current_token[1] == "var":
                self.advance()
                self.expect("Identifier", "MissingIdentifier")

            self.expect("Semicolon", "MissingSemicolonError")

        elif current_token[1] == "from":
            self.advance()
            self.expect("Identifier", "MissingIdentifier")
            self.expect("Identifier", "MissingIdentifier")

            current_token = self.peek()
            if current_token[1] == "var":
                self.advance()
                self.expect("Identifier", "MissingIdentifier")

            self.expect("Semicolon", "MissingSemicolonError")

        elif current_token[1] == "var":
            self.advance()
            self.expect("Identifier", "MissingIdentifier")
            self.expect("Equal", "MissingEquals")
            self.parse_expression()

    def parse_primary(self, allow_assignment=False):
        current_token = self.peek()
        if current_token[0] in ["String", "Number", "Float", "Boolean"]:
            self.advance()
            return current_token
        elif current_token[0] == "Identifier":
            return self.parse_identifier(current_token, allow_assignment)
        elif current_token[0] == "LeftParen":
            self.advance()
            expression = self.parse_expression()
            if self.expect("RightParen", "MissingClosingParen"):
                return expression

        elif current_token[0] == "LeftBracket":
            self.advance()
            current_token = self.peek()
            elements = []
            if current_token[0] == "RightBracket":
                self.advance()
                return elements
            elements.append(self.parse_expression())
            current_token = self.peek()

            while current_token[0] == "Comma":
                self.advance()
                elements.append(self.parse_expression())
                current_token = self.peek()
            if self.expect("RightBracket", "MissingClosingBracket"):
                return elements

        elif current_token[0] == "LeftBrace":
            self.advance()
            current_token = self.peek()
            dictionary = {}
            if current_token[0] == "RightBrace":
                self.advance()
                return dictionary
            key = self.parse_key()
            self.expect("Equal", "MissingEquals")
            value = self.parse_value()
            dictionary[key] = value
            current_token = self.peek()

            while current_token[0] == "Comma":
                self.advance()
                key = self.parse_key()
                self.expect("Equal", "MissingEquals")
                value = self.parse_value()
                dictionary[key] = value
                current_token = self.peek()

            if self.expect("RightBrace", "MissingClosingBrace"):
                return dictionary

        else:
            self.diagnostics.append(Diagnostic(
                "MissingExpression",
                f"Missing expression in line {current_token[2]} column {current_token[3]}",
                current_token[2],
                current_token[3],
                7,
                len(current_token[1])
            ))

    def parse_unary(self, allow_assignment=False):
        current_token = self.peek()
        if current_token[0] in ["Minus", "Not"]:
            self.advance()
            expression = self.parse_unary(allow_assignment)
            return current_token[1] + expression
        else:
            result = self.parse_primary(allow_assignment)
            return result

    def parse_power(self, allow_assignment=False):
        left = self.parse_unary(allow_assignment)
        current_token = self.peek()
        if current_token[0] == "Power":
            self.advance()
            right = self.parse_power(allow_assignment)
            return left + "**" + right
        else:
            return left

    def parse_multiplication(self, allow_assignment=False):
        left = self.parse_power(allow_assignment)
        current_token = self.peek()
        while current_token[0] in ["Multiply", "Divide", "Modulo"]:
            self.advance()
            right = self.parse_power(allow_assignment)
            left = left + current_token[1] + right
            current_token = self.peek()
        return left

    def parse_addition(self, allow_assignment=False):
        left = self.parse_multiplication(allow_assignment)
        current_token = self.peek()
        while current_token[0] in ["Plus", "Minus"]:
            self.advance()
            right = self.parse_multiplication(allow_assignment)
            left = left + current_token[1] + right
            current_token = self.peek()
        return left

    def parse_comparison(self, allow_assignment=False):
        left = self.parse_addition(allow_assignment)
        current_token = self.peek()
        if current_token[0] in ["Equal", "NotEqual", "Smaller", "Bigger", "In", "NotIn", "Is", "IsNot"]:
            self.advance()
            right = self.parse_addition(allow_assignment)
            return left + current_token[1] + right
        else:
            return left

    def parse_also(self, allow_assignment=False):
        left = self.parse_comparison(allow_assignment)
        current_token = self.peek()
        while current_token[0] == "Also":
            self.advance()
            right = self.parse_comparison(allow_assignment)
            left = left + current_token[1] + right
            current_token = self.peek()
        return left

    def parse_or(self, allow_assignment=False):
        left = self.parse_also(allow_assignment)
        current_token = self.peek()
        while current_token[0] == "Or":
            self.advance()
            right = self.parse_also(allow_assignment)
            left = left + current_token[1] + right
            current_token = self.peek()
        return left

    def parse_expression(self, allow_assignment=False):
        return self.parse_or(allow_assignment)

    def parse_block(self):
        if self.expect("Indent", "IndentationError"):
            current_token = self.peek()
            while current_token[0] != "Dedent":
                if current_token[0] != "Newline":
                    self.parse_statement()
                    current_token = self.peek()
                else:
                    self.advance()
            self.advance()

    def parse_identifier(self, identifier, allow_assignment=False):
        self.advance()
        current_token = self.peek()
        if current_token[0] == "LeftParen":
            self.advance()
            arguments = []
            current_token = self.peek()
            if current_token[0] == "RightParen":
                self.advance()
            else:
                arguments.append(self.parse_expression())
                current_token = self.peek()
                while current_token[0] == "Comma":
                    self.advance()
                    arguments.append(self.parse_expression())
                    current_token = self.peek()
                self.expect("RightParen", "MissingClosingParen")
            return {
                "type": "Call",
                "name": identifier,
                "arguments": arguments
            }

        elif current_token[0] == "LeftBracket":
            self.advance()
            index = self.parse_expression()
            if self.match("Semicolon"):
                end = self.parse_expression()
                self.expect("RightBracket", "MissingClosingBracket")
                return {
                    "type": "Slice",
                    "object": identifier,
                    "start": index,
                    "end": end
                }
            self.expect("RightBracket", "MissingClosingBracket")
            return {
                "type": "Index",
                "object": identifier,
                "index": index
            }
        elif current_token[0] == "Equal" and allow_assignment:
            self.advance()
            expression = self.parse_expression()
            return {"type": "Assignment",
                    "name": identifier,
                    "value": expression
                    }
        else:
            return identifier

    def parse_program(self):
        while not self.eof_reached:
            if not self.match("Newline"):
                self.parse_statement()
            else:
                pass
