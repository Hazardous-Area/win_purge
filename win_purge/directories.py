import os
import pathlib
import shutil
from typing import Iterable, Iterator

from send2trash import send2trash


def candidate_installion_directories(names: Iterable[str], publisher = '') -> Iterator[pathlib.Path]:

    if isinstance(names, str):
        names = [names]
    
    SYSTEM_DRIVE = os.getenv('SYSTEMDRIVE') + os.sep

    for name in names:
        for path in os.getenv('PATH').split(';'):
            if name.lower() in path.lower() or publisher and publisher.lower() in path.lower():
                yield pathlib.Path(path) 
        yield pathlib.Path(SYSTEM_DRIVE) / publisher / name # r'C:\' + name
        # os.sep is needed.  os.getenv('SYSTEMDRIVE') returns c: on Windows.
        #                    assert pathlib.Path(('c:', 'foo') == 'c:foo'
        yield pathlib.Path(os.getenv('PROGRAMFILES')) / publisher / name
        yield pathlib.Path(os.getenv('PROGRAMFILES(X86)')) / publisher / name
        yield pathlib.Path(os.getenv('APPDATA')) / publisher / name
        yield pathlib.Path(os.getenv('LOCALAPPDATA')) / publisher / name
        yield pathlib.Path(os.getenv('LOCALAPPDATA')) / 'Programs' / publisher / name
        yield pathlib.Path(os.getenv('LOCALAPPDATA')).parent / 'LocalLow' / publisher / name


def existing_installion_directories(strs: Iterable[str]) -> Iterator[pathlib.Path]:
    for path in candidate_installion_directories(strs):
        if path.exists():
            yield path


def check_directories(args: Iterable[str]) -> None:
    print('Checking directories.  Run with "--purge-paths" to move the following paths to the Recycle Bin:')
    for path in existing_installion_directories(args):
        print(str(path))


def purge_directories(args: Iterable[str]) -> None:
    print('WARNING!! Moving the following directories to the Recycle Bin: \n')
    paths = list(existing_installion_directories(args))
    for path in paths:
        confirmation = input(f'Delete: {str(path)}? (y/n/quit) ')

        if confirmation.lower().startswith('q'):
            break

        if confirmation.lower() == 'y':
            send2trash(path)

