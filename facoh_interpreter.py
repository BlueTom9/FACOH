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
            "dis": print,
            "takein": input,
            "num": int,
            "dec": float,
            "str": str,
            "bool": bool,
            "numste": range,
            "length": len,
            "openfile": open,
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
        self.tokens = self.lexer.lex(self.contents)
        self.parser = Parser(self.tokens, "Interpreter")
        self.ast = self.parser.parse_program()
        self.execute(self.ast)

    def evaluate(self, node):
        if node["type"] == "literal":
            return node["value"]

        elif node["type"] == "Variable":
            var = node["name"]
            if var in self.variables:
                return self.variables[var]
            else:
                raise FACOHNonExistantError

        elif node["type"] == "BinaryOperation":
            left = self.evaluate(node["left"])
            operator = node["operator"]
            right = self.evaluate(node["right"])
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

        elif node["type"] == "UnaryOperation":
            operand = self.evaluate(node["operand"])
            operator = node["operator"]
            if operator == "-":
                return -operand
            elif operator == "!":
                return not operand

        elif node["type"] == "Call":
            args = node["arguments"]
            name = node["name"]
            evaluated_args = []
            for arg in args:
                evaluated_args.append(self.evaluate(arg))
            if name in self.functions:
                function = self.functions[name]
                return function(*evaluated_args)
            elif name in self.user_functions:
                function = self.user_functions[name]
                parameters = function["parameters"]
                block = function["block"]
                old_variables = self.variables
                self.variables = {}

                for parameter, argument in zip(parameters, evaluated_args):
                    self.variables[parameter] = argument
                try:
                    self.execute(block)
                except ReturnSignal as signal:
                    self.variables = old_variables
                    return signal.value
                self.variables = old_variables
                return None
            else:
                raise FACOHNonExistantError

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
                evaluated_dic[key] = self.evaluate(value)
            return evaluated_dic

        elif node["type"] == "Index":
            indexed_object = self.variables[node["object"]]
            index = self.evaluate(node["index"])
            return indexed_object[index]

        elif node["type"] == "Slice":
            indexed_object = self.variables[node["object"]]
            start = self.evaluate(node["start"])
            end = self.evaluate(node["end"])
            return indexed_object[start:end]

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
                pass

            elif node["type"] == "fileoc":
                expression = self.evaluate(node["expression"])
                var = node["var"]
                block = node["block"]

                value = expression.__enter__()
                if var:
                    self.variables[var] = value
                try:
                    self.execute(block)
                except BaseException as error:
                    if not expression.__exit__(type(error), error, error.__traceback__):
                        raise
                else:
                    expression.__exit__(None, None, None)

            elif node["type"] == "use":
                pass

            elif node["type"] == "delete":
                var = node["target"]
                del self.variables[var]
