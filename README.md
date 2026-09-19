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
|  23 | `!=`               | same                                             |
|  24 | `<`                | same                                             |
|  25 | `>`                | same                                             |
|  26 | `and`              | `also`                                           |
|  27 | `or`               | `or`                                             |
|  28 | `not`              | `!`                                              |
|  29 | `in`               | `in`                                             |
|  30 | `not in`           | `!in`                                            |
|  31 | `is`               | `is`                                             |
|  32 | `is not`           | `!is`                                            |
|  33 | `if`               | `if operation =`                                 |
|  34 | `else`             | same                                             |
|  35 | `while`            | same                                             |
|  36 | `for`              | same                                             |
|  37 | `range()`          | `numste()`                                       |
|  38 | `numste(1, 3)`     | `1, 2, 3`                                        |
|  39 | `break`            | same                                             |
|  40 | `continue`         | same                                             |
|  41 | `pass`             | same                                             |
|  42 | `for ... else`     | same                                             |
|  43 | `while ... else`   | same                                             |
|  44 | `def`              | `func`                                           |
|  45 | Parameters         | same                                             |
|  46 | Arguments          | same                                             |
|  47 | Default arguments  | same                                             |
|  48 | Keyword arguments  | same                                             |
|  49 | `lambda`           | doesn't exist, reference a function without `()` |
|  50 | Recursion          | same                                             |
|  51 | Local scope        | same                                             |
|  52 | `class`            | same                                             |
|  53 | `self`             | handled by FACOH's class system                  |
|  54 | `__init__`         | doesn't exist, replaced by FACOH initialization  |
|  55 | Attributes         | same                                             |
|  56 | Methods            | same                                             |
|  57 | Inheritance        | same                                             |
|  58 | Method overriding  | same                                             |
|  59 | `try`              | same                                             |
|  60 | `except`           | `caught`                                         |
|  61 | `else`             | same                                             |
|  62 | `finally`          | same                                             |
|  63 | `raise`            | same                                             |
|  64 | `assert`           | same                                             |
|  65 | Custom exceptions  | same                                             |
|  66 | `import`           | `use`                                            |
|  67 | `from ... import`  | `from ... use`                                   |
|  68 | `as`               | `var`                                            |
|  69 | `open()`           | `openfile`                                       |
|  70 | `with`             | `fileoc`                                         |
|  71 | File `r`           | same                                             |
|  72 | File `w`           | same                                             |
|  73 | File `x`           | File `c`                                         |
|  74 | File `a`           | same                                             |
|  75 | File `e`           | edit without rewriting everything                |
|  76 | `del`              | same                                             |
|  77 | `len()`            | `length()`                                       |
|  78 | `type()`           | same                                             |
|  79 | `list()`           | `lis()`                                          |
|  80 | `tuple()`          | `tup()`                                          |
|  81 | `dict()`           | `dic()`                                          |
|  82 | `set()`            | same                                             |
|  83 | `enumerate()`      | `ind()`                                          |
|  84 | `sorted()`         | same                                             |
|  85 | `reversed()`       | same                                             |
|  86 | `sum()`            | same                                             |
|  87 | `min()`            | same                                             |
|  88 | `max()`            | same                                             |
|  89 | `abs()`            | same                                             |
|  90 | `round()`          | same                                             |
|  91 | `any()`            | same                                             |
|  92 | `all()`            | same                                             |
|  93 | `match`            | same                                             |
|  94 | `case`             | same                                             |
|  95 | f-strings          | same                                             |
|  96 | Escape sequences   | same                                             |
|  97 | Raw strings        | same                                             |
|  98 | Multiline strings  | same                                             |
|  99 | `#` comments       | same                                             |
| 100 | Multiline comments | another `#` on each line                         |
| 101 | `.py`              | `.fch`                                           |

# Development

FACOH is currently being worked on as an interpreter.

Current parts:

* Lexer
* Parser
* Diagnostics
* Interpreter

The long term plan is to make a compiler for FACOH after the interpreter is finished.

FACOH files use the `.fch` extension.
