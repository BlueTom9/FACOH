from lexer import Lexer
from parser import Parser


class Interpreter:
    def __init__(self, contents):
        self.lexer = Lexer(contents, "Interpreter")
        self.contents = contents
        self.variables = {}
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
        for node in self.ast:
            if node["type"] == "Assignment":
                value = self.evaluate(node["value"])
                self.variables[node["name"]] = value

            elif node["type"] == "Index":
                pass
            elif node["type"] == "Slice":
                pass
            elif node["type"] == "If":
                pass
            elif node["type"] == "While":
                pass
            elif node["type"] == "For":
                pass
            elif node["type"] == "break":
                pass
            elif node["type"] == "pass":
                pass
            elif node["type"] == "Function":
                pass
            elif node["type"] == "return":
                pass
            elif node["type"] == "try":
                pass
            elif node["type"] == "fileoc":
                pass
            elif node["type"] == "use":
                pass
            elif node["type"] == "delete":
                pass

    def evaluate(self, node):
        if node["type"] == "literal":
            return node["value"]
        elif node["type"] == "Variable":
            return self.variables[node["name"]]
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
            function = self.functions[name]
            for arg in args:
                evaluated_args.append(self.evaluate(arg))
            return function(*evaluated_args)
        
        elif node["type"] == "List":
            elements = node["elements"]
            evaluated_list = []
            for element in elements:
                evaluated_list.append(self.evaluate(element))
            return evaluated_list
