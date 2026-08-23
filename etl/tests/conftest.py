from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
ETL = PROJECT / "etl"
if str(ETL) not in sys.path:
    sys.path.insert(0, str(ETL))


def load_etl_node(filename: str):
    path = ETL / filename
    module_name = "etl_test_" + filename.replace(".", "_").replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
