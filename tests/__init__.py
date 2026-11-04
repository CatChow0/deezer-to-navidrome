"""Tests run against a throwaway data folder, never the real data/ directory."""
import os
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="d2n-tests-")
os.environ.pop("DISABLE_AUTH", None)
