from lexer import Lexer
from parser import Parser


class Interpreter:
    def __init__(self, contents):
        self.lexer = Lexer(contents, "Interpreter")
        self.contents = contents

    def run(self):
        self.parser = Parser()
        self.tokens = self.lexer.lex(self.contents)
        self.parser = Parser(self.tokens, "Interpreter")
        self.parser.parse_program()
