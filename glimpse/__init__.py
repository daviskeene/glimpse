"""Glimpse: run untrusted code snippets in isolated sandboxes.

This package root deliberately imports nothing heavy so that ``glimpse.languages``
and ``glimpse.execution`` can be used inside the Lambda image without FastAPI,
pydantic or docker installed.
"""

__version__ = "1.0.0"
