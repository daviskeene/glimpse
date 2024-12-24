import json
import os
import subprocess
import time

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
        "env": {"JAVA_OPTS": "-Xmx256m -Xms128m"},
    },
    "cpp": {
        "compile": ["g++"],
        "compile_args": ["-o", "/tmp/temp_code_cpp.out"],
        "execute": ["/tmp/temp_code_cpp.out"],
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
        "execute": ["/usr/local/go/bin/go", "run"],
        "file_ext": "go",
        "env": {"GOCACHE": "/tmp/.cache/go-build", "HOME": "/tmp"},
    },
    "kt": {
        "compile": ["kotlinc"],
        "compile_args": [
            "-include-runtime",
            "-d",
            "-J-Xmx256m",
            "-J-Xms256m",  # Make initial heap same as max to avoid resizing
            "-J-XX:+TieredCompilation",
            "-J-XX:TieredStopAtLevel=1",  # Faster JVM startup
        ],
        "execute": ["java", "-jar"],
        "file_ext": "kt",
        "output_ext": "jar",
    },
}

def get_sanitized_env():
    """
    Constructs a minimal environment dictionary for running user snippets
    without exposing AWS credentials or other sensitive values.
    Adjust as needed for your runtimes and libraries.
    """
    base_env = {
        "PATH": os.environ.get("PATH", "/usr/bin"),         # Essential for compilers/interpreters
        "LANG": "en_US.UTF-8",                               # Locale
        "JAVA_HOME": "/usr/lib/jvm/java-11-amazon-corretto", # Needed for Java/Kotlin
        "JAVA_OPTS": "-Xmx256m -Xms128m",                    # Java memory settings
        "KOTLIN_OPTS": "-Xmx256m -Xms128m",                  # Kotlin memory settings
        "LAMBDA_TASK_ROOT": "/var/task",                     # Where your Lambda code resides
        "HOME": "/tmp",                                      # Safe 'home' directory for caching
        "GOCACHE": "/tmp/.cache/go-build"                    # Go build cache
    }
    return base_env

def lambda_handler(event, context):
    try:
        # Extract code and language from the event
        language = event.get("language")
        code = event.get("code")
        input_data = event.get("input")

        if language not in LANGUAGE_COMMANDS:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": f"Unsupported language: {language}"}),
            }

        # Start timing
        start_time = time.time()

        # Get language details
        lang_config = LANGUAGE_COMMANDS[language]
        file_ext = lang_config["file_ext"]

        lang_specific_env = lang_config.get("env", {})  # e.g., {"GOCACHE": ...} for Go
        env_for_subprocess = {**get_sanitized_env(), **lang_specific_env}

        # Create a temporary file to save the code
        code_file = (
            "/tmp/Main.java" if language == "java" else f"/tmp/temp_code.{file_ext}"
        )
        with open(code_file, "w") as f:
            f.write(code)

        # Initialize output_file variable for compiled languages
        output_file = None

        # Compile code if needed
        if "compile" in lang_config:
            compile_command = lang_config["compile"] + [code_file]
            if "compile_args" in lang_config:
                output_file = f"/tmp/temp_code.{lang_config['output_ext']}"
                compile_command.extend(lang_config["compile_args"])
                compile_command.append(output_file)

            # Run the compile command with timeout
            try:
                compile_result = subprocess.run(
                    compile_command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=20,
                    env=env_for_subprocess,
                )
                if compile_result.returncode != 0:
                    return {
                        "statusCode": 200,
                        "body": json.dumps(
                            {"output": "", "error": compile_result.stderr.decode()}
                        ),
                    }
            except subprocess.TimeoutExpired:
                return {
                    "statusCode": 200,
                    "body": json.dumps(
                        {"output": "", "error": "Compilation timed out"}
                    ),
                }

        # Prepare the execution command
        if output_file:
            if language == "kt":
                execute_command = lang_config["execute"] + [output_file]
            else:
                execute_command = [output_file]
        else:
            execute_command = lang_config["execute"] + [code_file]

        # Run the code using subprocess
        exec_process = subprocess.Popen(
            execute_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env_for_subprocess,
        )

        # If input is provided, pass it to the process
        if input_data:
            stdout, stderr = exec_process.communicate(input=input_data.encode())
        else:
            stdout, stderr = exec_process.communicate()

        # Wait for the process to complete
        exec_process.wait()

        # Calculate execution time
        execution_time = time.time() - start_time

        # Check for runtime errors
        if exec_process.returncode != 0:
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "output": "",
                        "error": stderr.decode(),
                        "executionTime": execution_time,
                    }
                ),
            }

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "output": stdout.decode(),
                    "error": "",
                    "executionTime": execution_time,
                }
            ),
        }

    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
