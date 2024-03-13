import sys
from typing import Iterable, Iterator, Callable, Union, Any, Container
import winreg
import pathlib
import subprocess
import tempfile


from .reglib import ROOT_KEYS

('HKLM','HKCU','HKCR','HKU','HKCC')

UNINSTALLERS_REGISTRY_KEY = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'



def _walk_all_roots_dfs_bottom_up(
    key_name: str,
    root_keys: Iterable[Union[winreg.HKEYType, int]] = ROOT_KEYS,
    access: int = winreg.KEY_READ,
    max_depth: int = 5,
    )-> Iterator[tuple[winreg.HKEYType, str]]:

    for root_key in root_keys:

        # try:
        #     with winreg.OpenKey(root_key, ''):
        #         pass
        # except OSError:
        #     continue

        print(f'\nKeys under {root_keys[root_key]}:')

        try:
            yield from _walk_dfs_bottom_up(
                                    key_name=key_name,
                                    root_key=root_key,
                                    access=access,
                                    max_depth=max_depth,
                                    )
        except FileNotFoundError:
            pass
        print()


def get_names_vals_and_types(root: winreg.HKEYType, key_name: str) -> Iterator[tuple[str, Any, int]]:

    with winreg.OpenKey(root, key_name) as key:
        __, num_vals, __ = winreg.QueryInfoKey(key)
        for i in range(num_vals):
            yield winreg.EnumValue(key, i)


def vals_dict(root: winreg.HKEYType, key_name: str) -> dict:
    return {val_name: val 
            for val_name, val, __ in get_names_vals_and_types(root, key_nam)
           }

def get_path_val_names(vals: dict[str, str]) -> list[str]:
    return [k
            for k in vals
            if k.lower() == 'path'
           ]
        
SearchResult = tuple[winreg.HKEYType, str, str, str, Any, dict]

def _pprint_result(result: SearchResult, prefix: str = ''):

    root, name, key_name, val_name, val, vals = result

    print(f'{prefix}{name}', end='')

    path_val_names = get_path_val_names(vals)

    if path_val_names:
        k = path_val_names[0]
        print(f', includes {k}: {vals[k]}')
    elif val_name:
        print(f', for: {val_name=}, {val=}', end='')

    print(f' at: {key_name}')


def _search_keys_and_names(
    strs: Container[str], 
    roots_and_subkey_names: Iterator[tuple[winreg.HKEYType, str]],
    ) -> Iterator[SearchResult]:



    for root, key_name in keys_and_names:
        vals = vals_dict(root, key_name)
            
        display_name = vals.get('DisplayName',
                                next((val 
                                      for val_name, val in vals.items()
                                      if 'name' in val_name.lower()
                                     ),
                                     name
                                    )
                                )


        if any(search_str in name.rpartition('\\')[2] for search_str in strs):
            yield root, display_name, name, '', '', vals
        else:
            for val_name, val in vals.items():
                if any(search_str in str(val) for search_str in strs):
                    yield root, display_name, name, val_name, val, vals
                    break


def _matching_uninstallers(strs: Container[str]) -> Iterator[SearchResult]:
    yield from _search_keys_and_names(strs,
                                      _walk_dfs_bottom_up(
                                            key_name=UNINSTALLERS_REGISTRY_KEY,
                                            root_key=winreg.HKEY_LOCAL_MACHINE,
                                            ),
                                      )     

def system_path_registry_entries():
    yield r'HKEY_CURRENT_USER\Environment'
    yield r'HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Session Manager\Environment'


def check_uninstallers(strs: Container[str]):
    
    found = []

    for result in _matching_uninstallers(strs):
        found.append(result)
        _pprint_result(prefix='Matching uninstaller: ', result=result)


    if found:
        raise Exception('Matching uninstaller(s) found. Run these uninstallers first before purging. ')




def get_path_keys_and_other_keys(strs: Container[str]):
    path_keys = []
    other_keys = []
    for result in _search_keys_and_names(
                        strs,
                        _walk_all_roots_dfs_bottom_up(''),
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
        root, name, key_name, val_name, val, vals = result

        key_changed = False

        for path_val_name in get_path_val_names(vals):
            system_path = vals[path_val_name]
            paths = [path
                     for path in system_path.split(';')
                     if any(str_.lower() in path.lower() 
                            for str_ in args
                           )
                    ]
            confirmation = input(f'Remove: {paths} from registry key Path value? (y/n/quit)')

            if confirmation.lower().startswith('q'):
                break

            if confirmation.lower() == 'y':
                
                backup(key_name)
                
                if root not in backed_up:
                    backup_hive(ROOT_KEYS[root])
                    backed_up.add(root)

                with winreg.OpenKey(root, key_name) as key:
                    winreg.SetValueEx(
                        key = key, 
                        value_name = path_val_name, 
                        reserved = 0, 
                        type = 1,
                        value = ';'.join(path
                                         for path in system_path.split(';')
                                         if path not in paths
                                        ),
                                
                        )



                

    for result in other_keys:
                        #

        _pprint_result(prefix='Matching registry key: ', result=result)

        root, name, key_name, val_name, val, vals = result

        confirmation = input(f'Delete registry key: {key_name}? (y/n/quit) ')

        if confirmation.lower().startswith('q'):
            break

        if confirmation.lower() == 'y':
            if root not in backed_up:
                backup_hive(ROOT_KEYS[root])
                backed_up.add(root)

            with winreg.OpenKey(root, key_name, 0, access = winreg.KEY_ALL_ACCESS) as key:
                winreg.DeleteKey(key, '')


def purge_registry_keys(args: Container[str]) -> None:
    check_uninstallers(args)
    _purge_registry_keys(args)

# https://stackoverflow.com/a/63290451/20785734
# def delete_sub_key(root, sub):
    
#     try:
#         open_key = winreg.OpenKey(root, sub, 0, winreg.KEY_ALL_ACCESS)
#         num, _, _ = winreg.QueryInfoKey(open_key)
#         for i in range(num):
#             child = winreg.EnumKey(open_key, 0)
#             delete_sub_key(open_key, child)
#         try:
#            winreg.DeleteKey(open_key, '')
#         except Exception:
#            # log deletion failure
#         finally:
#            winreg.CloseKey(open_key)
#     except Exception:
#         # log opening/closure failure

