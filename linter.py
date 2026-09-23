import json
import sys

from lexer import Lexer
from parser import Parser


def lint_source(contents):
    lexer = Lexer(contents, "Interpreter")
    lexer_output = lexer.lex()

    parser = Parser(lexer_output, "Interpreter")
    parser_output = parser.parse_program()

    diagnostics = parser_output[1]

    result = []

    for diagnostic in diagnostics:
        result.append({
            "type": diagnostic.type,
            "message": diagnostic.message,
            "line": diagnostic.line,
            "column": diagnostic.column,
            "severity": diagnostic.severity,
            "length": diagnostic.length
        })

    return result


if __name__ == "__main__":
    contents = sys.stdin.read()
    print(json.dumps(lint_source(contents)))