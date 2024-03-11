import sys

from .directories import check_directories, purge_directories
from .registry import check_uninstallers, check_registry, purge_registry


def main(args = sys.argv[1:]) -> int:

    if not args:
        print('Example usage, searching for ["Microsoft"]')
        check_uninstallers(["Microsoft"])
    else:
        if not '--skip-uninstallers-check' in args:
            check_uninstallers(args)
        else:
            args.remove('--skip-uninstallers-check')

        if '--purge-paths' in args:
            args.remove('--purge-paths')
            purge_directories(args)
        else:
            check_directories(args)

        if '--purge-registry' in args:
            args.remove('--purge-registry')
            purge_registry(args)
        else:
            check_registry(args)

    return 0

if __name__ == '__main__':
    main()


