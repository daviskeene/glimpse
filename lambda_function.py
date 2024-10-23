import json
import subprocess
import os

# Define commands for each language
LANGUAGE_COMMANDS = {
    "py": {
        "execute": ["python3"],
        "file_ext": "py",
    },
    "java": {
        "compile": ["javac"],
        "execute": ["java"],
        "file_ext": "java",
    },
    "cpp": {
        "compile": ["g++"],
        "compile_args": ["-o"],
        "execute": [],
        "file_ext": "cpp",
        "output_ext": "out",
    },
    "c": {
        "compile": ["gcc"],
        "compile_args": ["-o"],
        "execute": [],
        "file_ext": "c",
        "output_ext": "out",
    },
    "js": {
        "execute": ["node"],
        "file_ext": "js",
    },
    "go": {
        "execute": ["go", "run"],
        "file_ext": "go",
    }
}

def lambda_handler(event, context):
    try:
        # Extract code and language from the event
        language = event.get("language")
        code = event.get("code")
        input_data = event.get("input")

        if language not in LANGUAGE_COMMANDS:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": f"Unsupported language: {language}"})
            }

        # Get language details
        lang_config = LANGUAGE_COMMANDS[language]
        file_ext = lang_config["file_ext"]

        # Create a temporary file to save the code
        code_file = f"/tmp/temp_code.{file_ext}"
        with open(code_file, "w") as f:
            f.write(code)

        # Initialize output_file variable for compiled languages
        output_file = None

        # Compile code if needed
        if "compile" in lang_config:
            compile_command = lang_config["compile"] + [code_file]
            if "compile_args" in lang_config:
                output_file = f"/tmp/temp_code.{lang_config['output_ext']}"
                compile_command += [output_file]

            # Run the compile command
            compile_result = subprocess.run(
                compile_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )

            # Check for compilation errors
            if compile_result.returncode != 0:
                return {
                    "statusCode": 200,
                    "body": json.dumps({"output": "", "error": compile_result.stderr.decode()})
                }

        # Prepare the execution command
        if output_file:
            execute_command = [output_file]
        else:
            execute_command = lang_config["execute"] + [code_file]

        # Run the code using subprocess
        exec_process = subprocess.Popen(
            execute_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # If input is provided, pass it to the process
        if input_data:
            stdout, stderr = exec_process.communicate(input=input_data.encode())
        else:
            stdout, stderr = exec_process.communicate()

        # Wait for the process to complete
        exec_process.wait()

        # Check for runtime errors
        if exec_process.returncode != 0:
            return {
                "statusCode": 200,
                "body": json.dumps({"output": "", "error": stderr.decode()})
            }

        return {
            "statusCode": 200,
            "body": json.dumps({"output": stdout.decode(), "error": ""})
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
