import subprocess
import asyncio
import os
import docker
import time
from fastapi import HTTPException

from utils.file_manager import create_submission, remove_submission
from utils.instructions import command_map, supported_languages
from containers import ContainerPool


async def run_code(
    language: str = "",
    code: str = "",
    input: str = None,
    container_pool: ContainerPool = None,
):
    """
    Asynchronously compiles and executes given source code in a specified language with optional input.

    This function:
    - Validates the supplied language against a list of supported languages.
    - Creates a new submission by writing the supplied code to a file.
    - If necessary, compiles the code using the compile command for the specified language.
    - Executes the compiled code or interprets the source code.
    - Handles any execution errors and timeouts.
    - Cleans up the created submission files.
    - Returns the execution output, error, language, and compiler/interpreter version info.

    Args:
        language (str): The programming language of the provided code. Defaults to an empty string.
        code (str): The source code to be compiled and executed. Defaults to an empty string.
        input (str): The input to be supplied to the code during its execution. Defaults to None.

    Raises:
        ValueError: If no code is provided or if an unsupported language is specified.
        ValueError: If there is an error during the compilation of the code.
        ValueError: If there is an error during the execution of the code.

    Returns:
        dict: A dictionary containing the output of the code execution, any execution errors,
              the language of the code, and the version info of the compiler/interpreter.

    Usage:
        $ asyncio.run(run_code(language='py', code='print("Hello, world!")'))
        {'output': 'Hello, world!\n', 'error': '', 'language': 'py', 'info': 'python3 --version'}
    """

    timeout = 30

    if not code:
        raise ValueError("No Code found to execute.")

    if language not in supported_languages:
        raise ValueError(
            f"Please enter a valid language. The languages currently supported are: {', '.join(supported_languages)}."
        )

    # Start timing
    start_time = time.time()

    if container_pool:
        # If a container pool is provided, use it.
        return await run_code_pool(language, code, input, container_pool)

    file_info = await create_submission(language, code)
    job_id = file_info["jobID"]
    commands = command_map(job_id, language)

    if commands.get("compileCodeCommand"):
        compile_code = await asyncio.create_subprocess_exec(
            commands["compileCodeCommand"],
            *commands.get("compilationArgs", []),
            stderr=subprocess.PIPE,
        )
        _, stderr = await compile_code.communicate()
        if stderr:
            raise ValueError(stderr.decode())

    execute_code = await asyncio.create_subprocess_exec(
        commands["executeCodeCommand"],
        *commands.get("executionArgs", []),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    stdout, stderr = await asyncio.wait_for(
        execute_code.communicate(input.encode() if input else None), timeout=timeout
    )

    if execute_code.returncode != 0:
        raise ValueError(stderr.decode())

    await remove_submission(job_id, language, commands.get("outputExt"))

    # Calculate execution time before return
    execution_time = time.time() - start_time

    return {
        "output": stdout.decode(),
        "error": stderr.decode(),
        "language": language,
        "info": commands["compilerInfoCommand"],
        "execution_time": execution_time,
    }


def strip_docker_control_characters(output):
    return "".join(chr(i) for i in output if (i > 31 and i < 127) or i in (9, 10, 13))


async def run_code_pool(
    language: str = "",
    code: str = "",
    input: str = None,
    container_pool: ContainerPool = None,
):
    """
    Asynchronously compiles and executes given source code in a specified language with optional input.
    This method assumes that this is being ran inside of a Docker container, which was sourced from a container pool.
    """

    if not code:
        raise ValueError("No Code found to execute.")

    if language not in supported_languages:
        raise ValueError(
            f"Please enter a valid language. The languages currently supported are: {', '.join(supported_languages)}."
        )

    # Start timing
    start_time = time.time()

    # Get a container from the pool
    container = container_pool.get_container()

    try:
        # Create the submission file
        file_info = await create_submission(language, code)
        job_id = file_info["jobID"]
        file_path = file_info["filePath"]

        # Inject the submission file into the container
        with open(file_path, "r") as file:
            data = {os.path.basename(file.name): file.read()}
            tar = docker.utils.create_archive(
                os.path.dirname(os.path.abspath(file_path)), data
            )
            container.put_archive(path="/tmp", data=tar)

        # Define the commands
        commands = command_map(job_id, language)
        commands["executionArgs"] = [os.path.join("/tmp", os.path.basename(file_path))]
        compile_command = (
            [commands.get("compileCodeCommand")] + commands.get("compilationArgs", [])
            if commands.get("compileCodeCommand")
            else None
        )
        exec_command = [commands["executeCodeCommand"]] + commands.get(
            "executionArgs", []
        )
        compile_command = " ".join(compile_command) if compile_command else None
        exec_command = " ".join(exec_command)

        # Compile the code if necessary
        if compile_command:
            result = container.exec_run(compile_command)
            if result.exit_code != 0:
                raise ValueError(f"Compilation error: {result.output.decode()}")

        # Execute the code
        if input is not None:
            exec_result = container.exec_run(
                exec_command, stdin=True, socket=True, demux=True
            )
            socket = exec_result.output
            stdin = socket._sock.makefile("w")

            stdin.write(input + "\n")
            stdin.close()

            output = strip_docker_control_characters(socket.read())
            socket.close()

            error = (
                ""
                if exec_result.exit_code == 0 or not exec_result.exit_code
                else output
            )
        else:
            exec_result = container.exec_run(exec_command)
            output = exec_result.output.decode()
            error = "" if exec_result.exit_code == 0 else output

    except Exception as e:
        print(f"Failed to execute code: {e}")
        raise HTTPException(status_code=500, detail="Failed to execute code")

    finally:
        # Remove the submission file
        await remove_submission(job_id, language, commands.get("outputExt"))
        # Replace the used container
        container_pool.replace_container(container)

    # Calculate execution time before return
    execution_time = time.time() - start_time

    # Return the code execution result
    return {
        "output": output,
        "error": error,
        "language": language,
        "info": commands["compilerInfoCommand"],
        "execution_time": execution_time,
    }


async def test():
    """
    Basic testing method.
    """
    response = await run_code("py", "print('Hello, world!')")
    return response


if __name__ == "__main__":
    print(asyncio.run(test()))
