import os

from facoh_interpreter import FACOHError, Interpreter

current_directory = os.getcwd()
while True:
    try:
        command = input(f"FCH {current_directory}> ")
        if command.lower() == "exit":
            break

        elif command.lower().startswith("cd "):
            path = command[3:].strip()

            if os.path.isabs(path):
                new_directory = os.path.abspath(path)
            else:
                new_directory = os.path.abspath(
                    os.path.join(current_directory, path)
                )

            if os.path.isdir(new_directory):
                current_directory = new_directory
            else:
                print("Directory not found")

        elif command.lower() == "cd":
            print(current_directory)

        elif "run " == command[0:4].lower():
            command = command.split()
            file = command[1]
            filename, extension = os.path.splitext(file)
            if extension == ".fch":
                file_path = os.path.join(current_directory, file)
                with open(file_path) as file:
                    contents = file.read()
                interpreter = Interpreter(contents)
                interpreter.run()
            else:
                print("File is not a facoh file")

        else:
            print("Invalid command")

    except (ValueError, IndexError):
        print("Invalid command")

    except FileNotFoundError:
        print("Invalid File")
    
    except KeyboardInterrupt:
        break

    except FACOHError as error:
        print(error)