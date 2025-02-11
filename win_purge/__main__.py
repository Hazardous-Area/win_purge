import sys

from .directories import search_directories, purge_directories
from .registry import check_uninstallers, search_registry_keys, purge_registry_keys


def main(args = sys.argv[1:]) -> int:

    if not args:
        print('Example usage: [python -m win_purge "Microsoft"]')
        args = ["Microsoft"]

        return 0


    if '--purge-paths' in args:
        args.remove('--purge-paths')
        purge_directories(args)
        return 0
    elif '--search-paths' in args:
        args.remove('--search-paths')
        search_directories(args)
        return 0


    if '--purge-registry' in args:
        args.remove('--purge-registry')
        purge_registry_keys(args)
    else:
        search_registry_keys(args)

    return 0

if __name__ == '__main__':
    main()


