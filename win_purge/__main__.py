import sys

from .directories import search_directories, purge_directories
from .registry import check_uninstallers, search_registry_keys, purge_registry_keys

COMMANDS = {# Values must not be None
            '--purge-paths' : purge_directories,
            '--search-paths' : search_directories,
            '--purge-registry' : purge_registry_keys,
            '--search-registry' : search_registry_keys,
            }
DEFAULT_COMMAND = search_registry_keys


def main(args = sys.argv[1:]) -> int:


    #  TODO:  Redo using Argparse if simpler.
    if not args:
        print('Example usage: [python -m win_purge "Unwanted_application"]')
        args = ["Unwanted_application"]

        return 0

    args_without_opts = []
    command = None

    for arg in args:
        if arg not in COMMANDS 
            args_without_opts.append(arg)
        elif command is None:
            command = COMMANDS[arg]
        
    command = command or DEFAULT_COMMAND
    
    command(args_without_opts)

    return 0

if __name__ == '__main__':
    main()


