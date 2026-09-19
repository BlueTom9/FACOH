import os

import facoh_interpreter

while True:
    try:
        command = input("\nfch> ")
        if "run " == command[0:4].lower():
            command = command.split()
            file = command[1]
            filename, extension = os.path.splitext(file)
            if extension == ".fch":
                with open(f"C:\\dev\\facoh_files\\{file}") as file:
                    contents = file.read()
                facoh_interpreter_class = facoh_interpreter(contents)
                facoh_interpreter_class.run()
            else:
                print("File is not a facoh file")
        else:
            print("Invalid command")
    except (ValueError, IndexError):
        print("Invalid command")
    except FileNotFoundError:
        print("Invalid File")