from __future__ import annotations

import json
from argparse import ArgumentParser
from pathlib import Path

from puccinialin import setup_rust


def main():
    parser = ArgumentParser()
    parser.add_argument("--location", help="The directory for installing rust to")
    parser.add_argument(
        "--program",
        help="The name of the installation directory in the cache, if `--location` was not used. Defaults to 'puccinialin'.",
    )
    parser.add_argument(
        "--info-json", help="Write the new environment variables as JSON to this file"
    )
    args = parser.parse_args()
    extra_env = setup_rust(args.location, args.program)

    json_info = {"env": extra_env}
    if args.info_json:
        Path(args.info_json).write_text(json.dumps(json_info, indent=4))
    else:
        print(json.dumps(json_info, indent=4))


if __name__ == "__main__":
    main()
