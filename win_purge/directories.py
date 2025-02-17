import os
import pathlib
from typing import Iterable, Collection, Iterator

import send2trash

from .registry import check_uninstallers


def getenv(name: str) -> str:
    # Convenience function for brevity and to pass type checking
    return os.getenv(name) or ''

APPDATA = pathlib.Path(getenv('APPDATA'))

def candidate_installation_directories(names: Iterable[str], publisher = '') -> Iterator[pathlib.Path]:

    if isinstance(names, str):
        names = [names]
    
    SYSTEM_DRIVE = getenv('SYSTEMDRIVE') + os.sep

    for name in names:
        for path in getenv('PATH').split(';'):
            if name.lower() in path.lower() or publisher and publisher.lower() in path.lower():
                yield pathlib.Path(path) 

        
        # An exact match with name is required in the remainder of cases.  
        yield pathlib.Path(SYSTEM_DRIVE) / publisher / name # r'C:\' + name
        # os.sep is needed.  getenv('SYSTEMDRIVE') returns c: on Windows.
        #                    assert pathlib.Path(('c:', 'foo') == 'c:foo'
        yield pathlib.Path(getenv('PROGRAMFILES')) / publisher / name
        yield pathlib.Path(getenv('PROGRAMFILES(X86)')) / publisher / name
        yield APPDATA / publisher / name
        yield pathlib.Path(getenv('LOCALAPPDATA')) / publisher / name
        yield pathlib.Path(getenv('LOCALAPPDATA')) / 'Programs' / publisher / name
        yield pathlib.Path(getenv('LOCALAPPDATA')).parent / 'LocalLow' / publisher / name


def existing_installation_directories(strs: Iterable[str]) -> Iterator[pathlib.Path]:
    for path in candidate_installation_directories(strs):
        if path.exists():
            yield path


def search_directories(args: Iterable[str]) -> None:
    print('Checking directories.  Run with "purge-paths" to move the following paths to the Recycle Bin:')
    for path in existing_installation_directories(args):
        print(str(path))


def _purge_directories(args: Iterable[str]) -> None:
    print('WARNING!! Moving the following directories to the Recycle Bin: \n')
    paths = existing_installation_directories(args)
    for path in paths:
        confirmation = input(f'Delete: {str(path)}? (y/n/quit) ')

        if confirmation.lower().startswith('q'):
            break

        if confirmation.lower() == 'y':
            send2trash.send2trash(path)

def purge_directories(args: Collection[str]) -> None:
    check_uninstallers(args)
    _purge_directories(args)
