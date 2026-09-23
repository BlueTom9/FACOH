from lexer import Lexer
from parser import Parser


class FACOHError(Exception):
    pass


class FACOHSyntaxError(FACOHError):
    pass


class FACOHIndexError(FACOHError):
    pass


class FACOHValueError(FACOHError):
    pass


class FACOHNonExistantError(FACOHError):
    pass


class FACOHZeroDivisionError(FACOHError):
    pass


class FACOHFileNotFoundError(FACOHError):
    pass


class FACOHIndentationError(FACOHError):
    pass


class FACOHTypeError(FACOHError):
    pass


class FACOHKeyError(FACOHError):
    pass


class BreakSignal(Exception):
    pass


class ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value


class Interpreter:
    def __init__(self, contents):
        self.lexer = Lexer(contents, "Interpreter")
        self.contents = contents
        self.variables = {}
        self.user_functions = {}
        self.functions = {
            "openfile": open,
            "dis": print,
            "takein": input,
            "num": int,
            "dec": float,
            "str": str,
            "bool": bool,
            "numste": range,
            "length": len,
            "type": type,
            "lis": list,
            "tup": tuple,
            "dic": dict,
            "set": set,
            "ind": enumerate,
            "sorted": sorted,
            "reversed": reversed,
            "sum": sum,
            "min": min,
            "max": max,
            "abs": abs,
            "round": round,
            "any": any,
            "all": all,
        }

    def run(self):
        self.tokens = self.lexer.lex()
        self.parser = Parser(self.tokens, "Interpreter")
        self.parser_output = self.parser.parse_program()
        self.ast = self.parser_output[0]
        self.diagnostics = self.parser_output[1]

        for diagnostic in self.diagnostics:
            if diagnostic.type == "IndentationError":
                raise FACOHIndentationError(diagnostic.message)
            else:
                raise FACOHSyntaxError(diagnostic.message)

        self.execute(self.ast)

    def evaluate(self, node):
        if node["type"] == "literal":
            if node["value"][0] in ["'", '"']:
                return node["value"][1:-1]
            elif node["value"] == "true":
                return True
            elif node["value"] == "false":
                return False
            elif "." in node["value"]:
                return float(node["value"])
            else:
                return int(node["value"])

        elif node["type"] == "Variable":
            var = node["name"]
            if var in self.variables:
                return self.variables[var]
            else:
                raise FACOHNonExistantError(
                    f"Variable '{var}' does not exist"
                )

        elif node["type"] == "BinaryOperation":
            left = self.evaluate(node["left"])
            operator = node["operator"]
            right = self.evaluate(node["right"])

            try:
                if operator == "+":
                    return left + right
                elif operator == "-":
                    return left - right
                elif operator == "*":
                    return left * right
                elif operator == "/":
                    return left / right
                elif operator == "%":
                    return left % right
                elif operator == "**":
                    return left ** right
                elif operator == "=":
                    return left == right
                elif operator == "<":
                    return left < right
                elif operator == ">":
                    return left > right
                elif operator == "!=":
                    return left != right
                elif operator == "also":
                    return left and right
                elif operator == "or":
                    return left or right
                elif operator == "in":
                    return left in right
                elif operator == "!in":
                    return not left in right
                elif operator == "is":
                    return left is right
                elif operator == "!is":
                    return not left is right
            except ZeroDivisionError:
                raise FACOHZeroDivisionError(
                    "Cannot divide by zero"
                )
            except TypeError:
                raise FACOHTypeError(
                    "Invalid operation between types"
                )

        elif node["type"] == "UnaryOperation":
            operand = self.evaluate(node["operand"])
            operator = node["operator"]
            try:
                if operator == "-":
                    return -operand
                elif operator == "!":
                    return not operand
            except TypeError:
                raise FACOHTypeError(
                    "Invalid unary operation"
                )

        elif node["type"] == "Call":
            args = node["arguments"]
            name = node["name"]
            evaluated_args = []
            for arg in args:
                evaluated_args.append(self.evaluate(arg))
            if name in self.functions:
                function = self.functions[name]

                try:
                    return function(*evaluated_args)

                except ValueError:
                    raise FACOHValueError(
                        f"Invalid value passed to '{name}'"
                    )

                except TypeError:
                    raise FACOHTypeError(
                        f"Invalid arguments passed to '{name}'"
                    )

                except FileNotFoundError:
                    raise FACOHFileNotFoundError(
                        "File not found"
                    )

            if name in self.user_functions:
                function = self.user_functions[name]
                parameters = function["parameters"]
                block = function["block"]
                if len(evaluated_args) != len(parameters):
                    raise FACOHValueError(
                        f"Function '{name}' expected "
                        f"{len(parameters)} argument(s), "
                        f"got {len(evaluated_args)}"
                    )
                old_variables = self.variables
                self.variables = {}

                for parameter, argument in zip(
                    parameters, evaluated_args
                ):
                    self.variables[parameter] = argument
                try:
                    self.execute(block)
                except ReturnSignal as signal:
                    self.variables = old_variables
                    return signal.value
                self.variables = old_variables
                return None
            else:
                raise FACOHNonExistantError(
                    f"Function '{name}' does not exist"
                )

        elif node["type"] == "List":
            elements = node["elements"]
            evaluated_list = []
            for element in elements:
                evaluated_list.append(self.evaluate(element))
            return evaluated_list

        elif node["type"] == "Dictionary":
            contents = node["contents"]
            evaluated_dic = {}
            for key, value in contents.items():
                key = key[1:-1]
                evaluated_dic[key] = self.evaluate(value)
            return evaluated_dic

        elif node["type"] == "Index":
            if node["object"] not in self.variables:
                raise FACOHNonExistantError(
                    f"Variable '{node['object']}' does not exist"
                )
            indexed_object = self.variables[node["object"]]
            index = self.evaluate(node["index"])
            try:
                return indexed_object[index]

            except IndexError:
                raise FACOHIndexError(
                    "Index is out of range"
                )
            except KeyError:
                raise FACOHKeyError(
                    f"Key '{index}' does not exist"
                )

            except TypeError:
                raise FACOHTypeError(
                    "Invalid index type"
                )

        elif node["type"] == "Slice":
            if node["object"] not in self.variables:
                raise FACOHNonExistantError(
                    f"Variable '{node['object']}' does not exist"
                )
            indexed_object = self.variables[node["object"]]
            start = self.evaluate(node["start"])
            end = self.evaluate(node["end"])

            try:
                return indexed_object[start:end]

            except TypeError:
                raise FACOHTypeError(
                    "Invalid slice"
                )
    def execute(self, nodes):
        for node in nodes:
            if node["type"] == "Assignment":
                value = self.evaluate(node["value"])
                self.variables[node["name"]] = value

            elif node["type"] == "Call":
                self.evaluate(node)

            elif node["type"] == "If":
                condition = self.evaluate(node["condition"])
                if condition:
                    self.execute(node["block"])
                else:
                    if node["else_block"]:
                        self.execute(node["else_block"])

            elif node["type"] == "While":
                block = node["block"]
                condition = node["condition"]
                try:
                    while self.evaluate(condition):
                        self.execute(block)
                except BreakSignal:
                    pass

            elif node["type"] == "For":
                break_appeared = False
                iterable = self.evaluate(node["iterable"])
                block = node["block"]
                try:
                    for value in iterable:
                        self.variables[node["variable"]] = value
                        self.execute(block)
                except BreakSignal:
                    break_appeared = True
                if not break_appeared and node["else_block"]:
                    self.execute(node["else_block"])

            elif node["type"] == "break":
                raise BreakSignal()

            elif node["type"] == "pass":
                pass

            elif node["type"] == "Function":
                name = node["name"]
                parameters = node["parameters"]
                block = node["block"]
                self.user_functions[name] = {
                    "parameters": parameters,
                    "block": block
                }

            elif node["type"] == "return":
                value = self.evaluate(node["value"])
                raise ReturnSignal(value)

            elif node["type"] == "try":
                try:
                    self.execute(node["block"])
                except FACOHError as error:
                    handled = False
                    for caught in node["caughts"].values():
                        if caught["type"] == type(error).__name__:
                            if caught["var"] is not None:
                                self.variables[caught["var"]] = error
                            self.execute(caught["block"])
                            handled = True
                            break
                    if not handled:
                        raise
                else:
                    if node["else_block"]:
                        self.execute(node["else_block"])
                finally:
                    if node["finally_block"]:
                        self.execute(node["finally_block"])

            elif node["type"] == "fileoc":
                try:
                    expression = self.evaluate(node["expression"])
                    var = node["var"]
                    block = node["block"]
                    value = expression.__enter__()

                except FileNotFoundError:
                    raise FACOHFileNotFoundError(
                        "File not found"
                    )

                if var:
                    self.variables[var] = value
                try:
                    self.execute(block)
                except BaseException as error:
                    if not expression.__exit__(
                        type(error),
                        error,
                        error.__traceback__
                    ):
                        raise
                else:
                    expression.__exit__(
                        None,
                        None,
                        None
                    )

            elif node["type"] == "use":
                pass 

            elif node["type"] == "delete":
                var = node["target"]["name"]
                if var not in self.variables:
                    raise FACOHNonExistantError(
                        f"Variable '{var}' does not exist"
                    )
                del self.variables[var]