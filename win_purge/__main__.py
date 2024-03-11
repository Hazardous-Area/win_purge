import sys

from .directories import search_directories, purge_directories
from .registry import check_uninstallers, search_registry, purge_registry


def main(args = sys.argv[1:]) -> int:

    if not args:
        print('Example usage, searching for ["Microsoft"]')
        check_uninstallers(["Microsoft"])
        return 0


    if '--purge-paths' in args:
        args.remove('--purge-paths')
        # purge_directories(args)
    else:
        search_directories(args)

    if '--purge-registry' in args:
        args.remove('--purge-registry')
        # purge_registry_keys(args)
    else:
        search_registry_keys(args)

    return 0

if __name__ == '__main__':
    main()


