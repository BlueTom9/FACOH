import multiprocessing
import os
import shlex
import sys
from pathlib import Path

from facoh_compiler import Compiler, compile_folder, compile_mod_folder
from facoh_interpreter import FACOHError, Interpreter

COMMANDS = ("run", "cexe", "cdir", "cmod")


def execute_command(command, file, current_directory):
    file_path = os.path.abspath(os.path.join(current_directory, file))

    if command == "cdir":
        output_path = compile_folder(file_path)
        print(f"Compiled successfully: {output_path}")
        return

    if command == "cmod":
        output_path = compile_mod_folder(file_path)
        print(f"Mod packaged successfully: {output_path}")
        return

    if Path(file_path).suffix.lower() != ".fch":
        print("File is not a FACOH file (.fch)")
        return

    with open(file_path, encoding="utf-8") as source_file:
        contents = source_file.read()

    if command == "run":
        interpreter = Interpreter(contents, file_path)
        interpreter.run()
    elif command == "cexe":
        output_path = Path(file_path).with_suffix(".exe")
        compiler = Compiler(contents, file_path)
        compiler.compile(output_path)
        print(f"Compiled successfully: {output_path}")


def handle_error(error):
    if isinstance(error, FileNotFoundError):
        print(f"Missing path: {error.filename}")
        print(error)
    elif isinstance(error, FACOHError):
        print(error)
    elif isinstance(error, (ValueError, TypeError, RuntimeError, OSError)):
        print(f"FACOH error: {error}")


def run_command_line(args):
    if len(args) != 2:
        print(
            "Usage: python facoh_pwsh.py "
            "run <file.fch> | cexe <file.fch> | "
            "cdir <folder> | cmod <mod-folder>"
        )
        return

    command, file = args[0].lower(), args[1]
    if command not in COMMANDS:
        print("Invalid command")
        return

    try:
        execute_command(command, file, os.getcwd())
    except (FileNotFoundError, FACOHError, ValueError, TypeError,
            RuntimeError, OSError) as error:
        handle_error(error)


def shell_prompt(current_directory):
    return f"FCH {current_directory} > "


def run_interactive_shell():
    current_directory = os.getcwd()
    print("FACOH interactive shell. Type 'help' for commands or 'exit' to quit.")

    while True:
        try:
            line = input(shell_prompt(current_directory)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        try:
            args = shlex.split(line, posix=(os.name != "nt"))
            # shlex with posix=False retains quote marks on Windows.
            if os.name == "nt":
                args = [
                    arg[1:-1] if len(arg) >= 2 and arg[0] == arg[-1]
                    and arg[0] in ("'", '"') else arg
                    for arg in args
                ]
        except ValueError as error:
            print(f"Could not parse command: {error}")
            continue

        if not args:
            continue

        command = args[0].lower()

        if command in ("exit", "quit"):
            break

        if command == "help":
            print("FACOH shell commands:")
            print("  run <file.fch>   Run a FACOH source file")
            print("  cexe <file.fch>  Compile a source file to an executable")
            print("  cdir <folder>    Compile a FACOH project folder")
            print("  cmod <folder>    Package a FACOH mod folder")
            print("  cd <directory>   Change the shell's current directory")
            print("  pwd              Show the current directory")
            print("  help             Show this help")
            print("  exit / quit      Close the shell")
            continue

        if command == "pwd":
            print(current_directory)
            continue

        if command == "cd":
            if len(args) != 2:
                print("Usage: cd <directory>")
                continue
            target = os.path.abspath(os.path.join(current_directory, args[1]))
            if os.path.isdir(target):
                current_directory = target
            else:
                print(f"Directory not found: {target}")
            continue

        if command not in COMMANDS:
            print(f"Unknown FACOH command: {args[0]}. Type 'help' for commands.")
            continue

        if len(args) != 2:
            print("Usage: run <file.fch> | cexe <file.fch> | cdir <folder> | cmod <mod-folder>")
            continue

        try:
            execute_command(command, args[1], current_directory)
        except (FileNotFoundError, FACOHError, ValueError, TypeError,
                RuntimeError, OSError) as error:
            handle_error(error)


def main():
    if len(sys.argv) == 1:
        run_interactive_shell()
    else:
        run_command_line(sys.argv[1:])


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
