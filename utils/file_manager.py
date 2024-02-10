import os
from pathlib import Path
from uuid import uuid4


async def create_submission(language: str, code: str):
    """
    Creates a submission file given a programming language
    and the code that a user has submitted.
    """
    job_id = str(uuid4())
    file_name = f"{job_id}.{language}"
    file_path = Path.cwd() / "submissions" / file_name

    os.makedirs(Path.cwd() / "submissions", exist_ok=True)
    os.makedirs(Path.cwd() / "outputs", exist_ok=True)

    with open(file_path, "w") as f:
        f.write(code or "")

    return {"fileName": file_name, "filePath": str(file_path), "jobID": job_id}


async def remove_submission(uuid: str, lang: str, output_ext: str):
    """
    Removes a submission file given the uuid assigned to our submission,
    the programming language associated with it, and the output extension.
    """
    code_file = Path.cwd() / "submissions" / f"{uuid}.{lang}"
    output_file = Path.cwd() / "outputs" / f"{uuid}.{output_ext}"

    if code_file.exists():
        os.remove(code_file)
    if output_file.exists() and output_ext:
        os.remove(output_file)


async def remove_all_submissions():
    """
    Removes all submissions from the /submissions/ directory.
    """
    code_file_dir = Path.cwd() / "submissions"
    for f in os.listdir(code_file_dir):
        os.remove(os.path.join(dir, f))
