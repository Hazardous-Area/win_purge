import sys
import argparse
from typing import Any, Callable, Collection

from .directories import search_directories, delete_directories
from .registry import search_registry, delete_values_or_keys_from_registry

COMMANDS: dict[str, Callable[[Collection[str]], Any]] = {
    "--purge-paths": delete_directories,
    "--search-paths": search_directories,
    "--purge-registry": delete_values_or_keys_from_registry,
    "--search-registry": search_registry,
}

DEFAULT_COMMAND = search_registry


def main(args=sys.argv[1:]) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(required=True, dest="command")

    sub_parsers = {}

    # create the parser for the "foo" command
    for command_name in COMMANDS:
        sub_parsers[command_name] = subparsers.add_parser(command_name)

    # Args common to all subparsers
    parser.add_argument("search_terms", action="extend", nargs="+", type=str)

    namespace = parser.parse_args(args)

    command = COMMANDS.get(namespace.command, DEFAULT_COMMAND)

    command(namespace.search_terms)

    return 0


if __name__ == "__main__":
    main()
