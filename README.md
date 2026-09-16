# FACOH

FACOH or "Flickz's Advanced Computational Operations Hub" is a personal programming language project made by Flickz.

# Syntax

|   # | Python             | FACOH                                            |
| --: | ------------------ | ------------------------------------------------ |
|   1 | `print()`          | `dis()`                                          |
|   2 | `input()`          | `takein()`                                       |
|   3 | Variables          | same                                             |
|   4 | `x = 2`            | same                                             |
|   5 | `int()`            | `num()`                                          |
|   6 | `float()`          | `dec()`                                          |
|   7 | `str()`            | `str()`                                          |
|   8 | `bool()`           | `bool()`                                         |
|   9 | `[]`               | `[]`                                             |
|  10 | `()`               | `()`                                             |
|  11 | `{}`               | `{}`                                             |
|  12 | `:`                | `=`                                              |
|  13 | List indexing      | same                                             |
|  14 | List slicing       | `[start, end, optional +index]`                  |
|  15 | `+`                | same                                             |
|  16 | `-`                | same                                             |
|  17 | `*`                | same                                             |
|  18 | `/`                | same                                             |
|  19 | `//`               | same                                             |
|  20 | `%`                | same                                             |
|  21 | `**`               | same                                             |
|  22 | `=`                | same                                             |
|  23 | `==`               | same                                             |
|  24 | `!=`               | same                                             |
|  25 | `<`                | same                                             |
|  26 | `>`                | same                                             |
|  27 | `and`              | `also`                                           |
|  28 | `or`               | `or`                                             |
|  29 | `not`              | `!`                                              |
|  30 | `in`               | `in`                                             |
|  31 | `not in`           | `!in`                                            |
|  32 | `is`               | `is`                                             |
|  33 | `is not`           | `!is`                                            |
|  34 | `if`               | `if operation =`                                 |
|  35 | `else`             | same                                             |
|  36 | `while`            | same                                             |
|  37 | `for`              | same                                             |
|  38 | `range()`          | `numste()`                                       |
|  39 | `numste(1, 3)`     | `1, 2, 3`                                        |
|  40 | `break`            | same                                             |
|  41 | `continue`         | same                                             |
|  42 | `pass`             | same                                             |
|  43 | `for ... else`     | same                                             |
|  44 | `while ... else`   | same                                             |
|  45 | `def`              | `func`                                           |
|  46 | Parameters         | same                                             |
|  47 | Arguments          | same                                             |
|  48 | Default arguments  | same                                             |
|  49 | Keyword arguments  | same                                             |
|  50 | `lambda`           | doesn't exist, reference a function without `()` |
|  51 | Recursion          | same                                             |
|  52 | Local scope        | same                                             |
|  53 | `class`            | same                                             |
|  54 | `self`             | handled by FACOH's class system                  |
|  55 | `__init__`         | doesn't exist, replaced by FACOH initialization  |
|  56 | Attributes         | same                                             |
|  57 | Methods            | same                                             |
|  58 | Inheritance        | same                                             |
|  59 | Method overriding  | same                                             |
|  60 | `try`              | same                                             |
|  61 | `except`           | `caught`                                         |
|  62 | `else`             | same                                             |
|  63 | `finally`          | same                                             |
|  64 | `raise`            | same                                             |
|  65 | `assert`           | same                                             |
|  66 | Custom exceptions  | same                                             |
|  67 | `import`           | `use`                                            |
|  68 | `from ... import`  | `from ... use`                                   |
|  69 | `as`               | `var`                                            |
|  70 | `open()`           | `openfile`                                       |
|  71 | `with`             | `fileoc`                                         |
|  72 | File `r`           | same                                             |
|  73 | File `w`           | same                                             |
|  74 | File `c`           | same                                             |
|  75 | File `a`           | same                                             |
|  76 | File `e`           | edit without rewriting everything                |
|  77 | `del`              | same                                             |
|  78 | `len()`            | `length()`                                       |
|  79 | `type()`           | same                                             |
|  80 | `list()`           | `lis()`                                          |
|  81 | `tuple()`          | `tup()`                                          |
|  82 | `dict()`           | `dic()`                                          |
|  83 | `set()`            | same                                             |
|  84 | `enumerate()`      | `ind()`                                          |
|  85 | `sorted()`         | same                                             |
|  86 | `reversed()`       | same                                             |
|  87 | `sum()`            | same                                             |
|  88 | `min()`            | same                                             |
|  89 | `max()`            | same                                             |
|  90 | `abs()`            | same                                             |
|  91 | `round()`          | same                                             |
|  92 | `any()`            | same                                             |
|  93 | `all()`            | same                                             |
|  94 | `match`            | same                                             |
|  95 | `case`             | same                                             |
|  96 | f-strings          | same                                             |
|  97 | Escape sequences   | same                                             |
|  98 | Raw strings        | same                                             |
|  99 | Multiline strings  | same                                             |
| 100 | `#` comments       | same                                             |
| 101 | Multiline comments | another `#` on each line                         |
| 102 | `.py`              | `.fch`                                           |

# Development

FACOH is currently being worked on as an interpreter.

Current parts:

* Lexer
* Parser
* Diagnostics
* Interpreter

The long term plan is to make a compiler for FACOH after the interpreter is finished.

FACOH files use the `.fch` extension.
