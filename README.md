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
|  40 | `continue`         | doesn't exist                                    |
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
|  63 | `raise`            | throw                                            |
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

# Concurrency

FACOH can use Python's `threading` and `multiprocessing` modules through `use`. 
Their module attributes, constructors, and methods are available, and native calls accept keyword arguments. FACOH functions can be passed as thread or process targets:

use threading;
use multiprocessing;
func send_result(channel, value);
    channel.put(value + 1)

channel = multiprocessing.Queue()
worker = threading.Thread(target = send_result, args = \[channel, 41\])
worker.start()
worker.join(timeout = 5)
dis(channel.get())
For CPU-parallel or isolated work, replace `threading.Thread` with `multiprocessing.Process` call `start()` and `join()` the same way.

# Development

FACOH has an interpreter and a compiler. The compiler can compile FACOH
source into native executables, including folder-based projects. The
compiler is being developed alongside the language runtime; behavior and
supported features may differ between interpreted and compiled
execution.

Core components include:

-   Lexer and parser
-   Diagnostics and error handling
-   Interpreter and runtime
-   Native compiler and executable generation
-   Standard-library modules and optional extensions

FACOH source files use the `.fch` extension.

## Running FACOH

Clone the repository:

https://github.com/BlueTom9/FACOH

For interpreter usage, run `python facoh_pwsh.py` from the repository's
appropriate directory, then use the `run` command for a `.fch` file.
Check the current repository scripts and command-line help for the exact
arguments supported by your checkout.

The compiler has a separate workflow for producing native executables.
Folder compilation uses the `cdir` command and the project's
manifest/configuration where applicable. Consult the compiler's current
help or examples for the available options.

## VS Code extension

The FACOH VS Code extension provides language support for `.fch` files,
including syntax highlighting, language-aware bracket and indentation
behavior, lint diagnostics, formatting, and completion/snippet
suggestions.

The extension's grammar recognizes FACOH constructs such as `func`,
`obj`, control-flow statements, exception handling, imports (`use` and
`from`), built-in functions, operators, comments, strings, and
f-strings. Editor diagnostics and formatting depend on the installed
extension version and the matching FACOH lexer/parser files, so keep
those components compatible.

This projects Icon pack uses Seti's icons + Facoh icon
