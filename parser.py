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
            return ["EOF", "", 0, 0]

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
            return self.parse_if()
        elif current_token[1] == "while":
            return self.parse_while()
        elif current_token[1] == "for":
            return self.parse_for()
        elif current_token[1] == "func":
            return self.parse_func()
        elif current_token[1] == "try":
            return self.parse_try()
        elif current_token[1] == "fileoc":
            return self.parse_fileoc()
        elif current_token[1] == "use" or current_token[1] == "from":
            return self.parse_use_from_var()
        elif current_token[1] in ["break", "del", "pass", "return"]:
            return self.parse_simple_statement()
        elif current_token[0] in [
            "String", "Number", "Boolean", "Float", "Identifier",
            "LeftParen", "LeftBracket", "LeftBrace", "Minus", "Not"
        ]:
            return self.parse_expression(True)
        else:
            self.advance()

    def parse_if(self):
        self.advance()
        else_block = None
        condition = self.parse_expression()
        self.expect("Semicolon", "MissingSemicolonError")
        block = self.parse_block()
        self.match("Newline")
        current_token = self.peek()
        if current_token and current_token[1] == "else":
            self.advance()
            self.expect("Semicolon", "MissingSemicolonError")
            else_block = self.parse_block()
        return {
            "type": "If",
            "condition": condition,
            "block": block,
            "else_block": else_block
        }

    def parse_while(self):
        self.advance()
        condition = self.parse_expression()
        self.expect("Semicolon", "MissingSemicolonError")
        block = self.parse_block()
        return {
            "type": "While",
            "condition": condition,
            "block": block
        }

    def parse_for(self):
        self.advance()
        else_block = None
        variable = self.peek()[1]
        iterable = None
        block = []
        if self.expect("Identifier", "MissingIdentifier") and self.expect("In", "MissingParameterError"):
            iterable = self.parse_expression()
            if self.expect("Semicolon", "MissingSemicolonError"):
                block = self.parse_block()
            current_token = self.peek()
            if current_token and current_token[1] == "else":
                self.advance()
                self.expect("Semicolon", "MissingSemicolonError")
                else_block = self.parse_block()
        return {
            "type": "For",
            "variable": variable,
            "iterable": iterable,
            "block": block,
            "else_block": else_block
        }

    def parse_func(self):
        self.advance()
        func_name = self.parse_function_name()
        parameters = self.parse_function_parameters(func_name)
        self.expect("Semicolon", "MissingSemicolonError")
        block = self.parse_block()
        return {
            "type": "Function",
            "name": func_name,
            "parameters": parameters,
            "block": block
        }

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
            return parameters

    def parse_try(self):
        self.advance()
        else_block = None
        finally_block = None
        block = []
        caughts = {}
        if self.expect("Semicolon", "MissingSemicolonError"):
            block = self.parse_block()
            self.match("Newline")
            current_token = self.peek()
            caught_number = 0
            while current_token[1] == "caught":
                self.advance()
                caught_type = None
                caught_var = None
                current_token = self.peek()
                if current_token[0] == "Identifier":
                    caught_type = current_token[1]
                    self.advance()
                    current_token = self.peek()

                if current_token[1] == "var":
                    self.advance()
                    current_token = self.peek()
                    caught_var = current_token[1]
                    self.expect("Identifier", "MissingIdentifier")

                self.expect("Semicolon", "MissingSemicolonError")
                caught_block = self.parse_block()
                caughts[caught_number] = {
                    "type": caught_type,
                    "block": caught_block,
                    "var": caught_var
                }
                caught_number += 1
                current_token = self.peek()
            if current_token[1] == "else":
                self.advance()
                self.expect("Semicolon", "MissingSemicolonError")
                else_block = self.parse_block()
                current_token = self.peek()

            if current_token[1] == "finally":
                self.advance()
                self.expect("Semicolon", "MissingSemicolonError")
                finally_block = self.parse_block()

        return {
            "type": "try",
            "block": block,
            "caughts": caughts,
            "else_block": else_block,
            "finally_block": finally_block
        }

    def parse_fileoc(self):
        var = None
        self.advance()
        expression = self.parse_expression()
        current_token = self.peek()
        if current_token[1] == "var":
            self.advance()
            var = self.peek()[1]
            self.expect("Identifier", "MissingIdentifier")
        self.expect("Semicolon", "MissingSemicolonError")
        block = self.parse_block()
        return {
            "type": "fileoc",
            "var": var,
            "block": block,
            "expression": expression
        }

    def parse_simple_statement(self):
        current_token = self.peek()
        if current_token[1] in ["break", "pass"]:
            self.advance()
            return {
                "type": current_token[1]
            }
        elif current_token[1] == "del":
            self.advance()
            target = self.parse_expression()
            return {
                "type": "delete",
                "target": target
            }
        elif current_token[1] == "return":
            value = None
            self.advance()
            current_token = self.peek()
            if current_token[0] not in ["Newline", "Indent", "Dedent", "EOF"]:
                value = self.parse_expression()
            return {
                "type": "return",
                "value": value
            }

    def parse_use_from_var(self):
        from_tab = None
        var_tab = None
        current_token = self.peek()
        if current_token[1] == "use":
            self.advance()
            name = self.peek()[1]
            self.expect("Identifier", "MissingIdentifier")
            current_token = self.peek()
            if current_token[1] == "var":
                self.advance()
                var_tab = self.peek()[1]
                self.expect("Identifier", "MissingIdentifier")
            self.expect("Semicolon", "MissingSemicolonError")

        elif current_token[1] == "from":
            self.advance()
            from_tab = self.peek()[1]
            self.expect("Identifier", "MissingIdentifier")
            name = self.peek()[1]
            self.expect("Identifier", "MissingIdentifier")
            current_token = self.peek()
            if current_token[1] == "var":
                self.advance()
                var_tab = self.peek()[1]
                self.expect("Identifier", "MissingIdentifier")
            self.expect("Semicolon", "MissingSemicolonError")

        return {
            "type": "use",
            "from": from_tab,
            "name": name,
            "var": var_tab
        }

    def parse_key(self):
        current_token = self.peek()
        if current_token[0] in ["String", "Number", "Boolean", "Float", "Identifier"]:
            self.advance()
            return current_token[1]
        self.diagnostics.append(Diagnostic(
            "MissingExpression",
            f"Invalid dictionary key in line {current_token[2]} column {current_token[3]}",
            current_token[2],
            current_token[3],
            7,
            len(current_token[1])
        ))
        return None

    def parse_value(self):
        return self.parse_expression()

    def parse_primary(self, allow_assignment=False):
        current_token = self.peek()
        if current_token[0] in ["String", "Number", "Float", "Boolean"]:
            self.advance()
            return {
                "type": "literal",
                "value": current_token[1]
            }
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
                return {
                    "type": "List",
                    "elements": elements
                }
            elements.append(self.parse_expression())
            current_token = self.peek()

            while current_token[0] == "Comma":
                self.advance()
                elements.append(self.parse_expression())
                current_token = self.peek()
            if self.expect("RightBracket", "MissingClosingBracket"):
                return {
                    "type": "List",
                    "elements": elements
                }

        elif current_token[0] == "LeftBrace":
            self.advance()
            current_token = self.peek()
            dictionary = {}
            if current_token[0] == "RightBrace":
                self.advance()
                return {
                    "type": "Dictionary",
                    "contents": dictionary
                }
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
                return {
                    "type": "Dictionary",
                    "contents": dictionary
                }

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
            return {
                "type": "UnaryOperation",
                "operator": current_token[1],
                "operand": expression
            }
        return self.parse_primary(allow_assignment)

    def parse_power(self, allow_assignment=False):
        left = self.parse_unary(allow_assignment)
        current_token = self.peek()
        if current_token[0] == "Power":
            operator = current_token[1]
            self.advance()
            right = self.parse_power(allow_assignment)
            return {
                "type": "BinaryOperation",
                "operator": operator,
                "left": left,
                "right": right
            }

        return left

    def parse_multiplication(self, allow_assignment=False):
        left = self.parse_power(allow_assignment)
        current_token = self.peek()
        while current_token[0] in ["Multiply", "Divide", "Modulo"]:
            operator = current_token[1]
            self.advance()
            right = self.parse_power(allow_assignment)
            left = {
                "type": "BinaryOperation",
                "operator": operator,
                "left": left,
                "right": right
            }
            current_token = self.peek()
        return left

    def parse_addition(self, allow_assignment=False):
        left = self.parse_multiplication(allow_assignment)
        current_token = self.peek()
        while current_token[0] in ["Plus", "Minus"]:
            operator = current_token[1]
            self.advance()
            right = self.parse_multiplication(allow_assignment)
            left = {
                "type": "BinaryOperation",
                "operator": operator,
                "left": left,
                "right": right
            }
            current_token = self.peek()
        return left

    def parse_comparison(self, allow_assignment=False):
        left = self.parse_addition(allow_assignment)
        current_token = self.peek()
        if current_token[0] in ["Equal", "NotEqual", "Smaller", "Bigger", "In", "NotIn", "Is", "IsNot"]:
            operator = current_token[1]
            self.advance()
            right = self.parse_addition(allow_assignment)
            left = {
                "type": "BinaryOperation",
                "operator": operator,
                "left": left,
                "right": right
            }
            return left

        return left

    def parse_also(self, allow_assignment=False):
        left = self.parse_comparison(allow_assignment)
        current_token = self.peek()
        while current_token[0] == "Also":
            operator = current_token[1]
            self.advance()
            right = self.parse_comparison(allow_assignment)
            current_token = self.peek()
            left = {
                "type": "BinaryOperation",
                "operator": operator,
                "left": left,
                "right": right
            }
        return left

    def parse_or(self, allow_assignment=False):
        left = self.parse_also(allow_assignment)
        current_token = self.peek()
        while current_token[0] == "Or":
            operator = current_token[1]
            self.advance()
            right = self.parse_also(allow_assignment)
            current_token = self.peek()
            left = {
                "type": "BinaryOperation",
                "operator": operator,
                "left": left,
                "right": right
            }
        return left

    def parse_expression(self, allow_assignment=False):
        return self.parse_or(allow_assignment)

    def parse_block(self):
        if self.expect("Indent", "IndentationError"):
            statements = []
            current_token = self.peek()
            while current_token[0] not in ["Dedent", "EOF"]:
                if current_token[0] != "Newline":
                    statements.append(self.parse_statement())
                    current_token = self.peek()
                else:
                    self.advance()
                    current_token = self.peek()
            if current_token[0] == "Dedent":
                self.advance()
            return statements
        return []

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
                "name": identifier[1],
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
                    "object": identifier[1],
                    "start": index,
                    "end": end
                }
            self.expect("RightBracket", "MissingClosingBracket")
            return {
                "type": "Index",
                "object": identifier[1],
                "index": index
            }
        elif current_token[0] == "Equal" and allow_assignment:
            self.advance()
            expression = self.parse_expression()

            return {
                "type": "Assignment",
                "name": identifier[1],
                "value": expression
            }

        return {
            "type": "Variable",
            "name": identifier[1]
        }

    def parse_program(self):
        result = []
        while not self.eof_reached:
            if not self.match("Newline"):
                statement = self.parse_statement()
                if statement is not None:
                    result.append(statement)

        if self.mode == "Diagnostics + Output":
            return [result, self.diagnostics]
        else:
            return self.diagnostics
