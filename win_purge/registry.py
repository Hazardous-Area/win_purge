import sys
from typing import Iterable, Iterator, Callable, Union, Any, Container
import winreg
import pathlib
import subprocess
import tempfile


import reglib



            # e.g.   key,            display_name, val_name, val, vals
SearchResult = tuple[reglib.BaseKey, str,          str,      Any, dict]

def _pprint_result(result: SearchResult, prefix: str = ''):

    key, display_name, val_name, val, vals = result

    print(f'{prefix}{display_name}', end='')

    name_of_OS_path_data_entry_name = next(key.names_of_path_env_variables(), None)

    if name_of_OS_path_data_entry_name is not None:
        print(f', includes {name_of_OS_path_data_entry_name}: {vals[name_of_OS_path_data_entry_name]}')
    elif val_name:
        print(f', for: {val_name=}, {val=}', end='')

    print(f' at: {key}')


def _search_keys_and_names(
    strs: Container[str], 
    keys: Iterator[reglib.reglib.BaseKey],
    ) -> Iterator[SearchResult]:

    for key in keys:
        vals = key.registry_values()
            
        display_name = vals.get('DisplayName',
                                next((val 
                                      for val_name, val in vals.items()
                                      if 'name' in val_name.lower()
                                     ),
                                     str(key)
                                    )
                                )


        if any(search_str in key.rel_key.rpartition('\\')[2] 
               for search_str in strs):
            #    
            yield key, display_name, '', '', vals
        else:
            for val_name, val in vals.items():
                if any(search_str in str(val) for search_str in strs):
                    yield key, display_name, val_name, val, vals
                    break


def _matching_uninstallers(strs: Container[str]) -> Iterator[SearchResult]:
    for uninstaller_key in reglib.uninstallers_keys:
        yield from _search_keys_and_names(uninstaller_key.children())
        
   



def check_uninstallers(strs: Container[str]):
    
    found = []

    for result in _matching_uninstallers(strs):
        found.append(result)
        _pprint_result(prefix='Matching uninstaller: ', result=result)


    if found:
        raise Exception('Matching uninstaller(s) found. Run these uninstallers first before purging. ')


global_root = reglib.GlobalRoot()

def get_path_keys_and_other_keys(strs: Container[str]):
    path_keys = []
    other_keys = []
    for result in _search_keys_and_names(
                        strs,
                        global_root.walk(),
                        ):
        if get_path_val_names(result[5]):
            path_keys.append(result)
        else:
            other_keys.append(result)

    return path_keys, other_keys


def search_registry_keys(args: Container[str]) -> None:
    print('Searching for matching Registry keys.  Run with "--purge-registry" to delete the following registry keys:')
    
    path_keys, other_keys = get_path_keys_and_other_keys(args)
    
    for result in path_keys:
        _pprint_result(prefix='Match found in System Path registry key: ', result=result)

    for result in other_keys:
        _pprint_result(prefix='Matching registry key: ', result=result)




def _purge_registry_keys(args: Container[str]) -> None:
    print('WARNING!! Deleting the following Registry keys: ')

    backed_up = set()

    tmp_backups = []

    def backup(key_name: str) -> None:
        tmp_backups.append(tmp_backup_key(key_name))

    path_keys, other_keys = get_path_keys_and_other_keys(args)

    for result in path_keys:
        key, __, __, __, vals = result

        key_changed = False

        for path_val_name in key.names_of_path_env_variables():
            system_paths = set(vals[path_val_name].split(';'))
            matching_paths = {
                     path
                     for path in system_paths
                     if any(str_.lower() in path.lower() 
                            for str_ in args
                           )
                    }
            confirmation = input(f'Remove: {matching_paths} from registry key Path value? (y/n/quit)')

            if confirmation.lower().startswith('q'):
                break

            if confirmation.lower() == 'y':
                key.set_registry_value_data(
                    name = path_val_name,
                    data = ';'.join(system_paths - matching_paths),
                    type = 1,
                    )




                

    for result in other_keys:
                        #

        _pprint_result(prefix='Matching registry key: ', result=result)

        key, __, __, __, __ = result

        confirmation = input(f'Delete registry key: {key}? (y/n/quit) ')

        if confirmation.lower().startswith('q'):
            break

        if confirmation.lower() == 'y':
            key.delete()


def purge_registry_keys(args: Container[str]) -> None:
    check_uninstallers(args)
    _purge_registry_keys(args)
