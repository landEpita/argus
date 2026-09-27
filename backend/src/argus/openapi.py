"""Print the OpenAPI document: ``python -m argus.openapi > openapi.json``.

The frontend generates its TypeScript types from this file, and CI fails if the
committed copy drifts from what the code produces.
"""

from __future__ import annotations

import json
import sys

from argus.config import Settings
from argus.main import create_app


def main() -> None:
    settings = Settings(database_url="sqlite+aiosqlite://", _env_file=None)
    schema = create_app(settings).openapi()
    json.dump(schema, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
