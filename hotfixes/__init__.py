import os

SELF_PATH = os.path.dirname(os.path.realpath(__file__))
CACHE_PATH = os.path.join(SELF_PATH, "cache")

if not os.path.exists(CACHE_PATH):
    os.makedirs(CACHE_PATH, exist_ok=True)

__all__ = ["dbdefs", "structures", "parser", "utils"]
