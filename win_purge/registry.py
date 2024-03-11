import sys
from typing import Iterable, Iterator, Callable, Union, Any, Container
import winreg
import subprocess

ROOT_KEYS = {winreg.HKEY_CLASSES_ROOT: 'HKCR',
             winreg.HKEY_CURRENT_CONFIG: 'HKCC',
             winreg.HKEY_CURRENT_USER: 'HKCU',
             winreg.HKEY_DYN_DATA: 'HKDD',
             winreg.HKEY_LOCAL_MACHINE: 'HKLM',
             winreg.HKEY_PERFORMANCE_DATA: 'HKPD',
             winreg.HKEY_USERS: 'HKU',
            }

('HKLM','HKCU','HKCR','HKU','HKCC')

UNINSTALLERS_REGISTRY_KEY = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'




def _walk_deepest_first_dfs(
    key_name: str,
    root_key: Union[winreg.HKEYType, int],
    access: int = winreg.KEY_READ,
    max_depth: int = 5,
    )-> Iterator[tuple[winreg.HKEYType, winreg.HKEYType, str]]:

    if max_depth == 0:
        return

    try:
        this_key = winreg.OpenKey(root_key, key_name, 0, access)
    except OSError:
        pass
        #print(f'Error opening: {ROOT_KEYS[root_key]}\\{key_name}')
    else:
        num_sub_keys, num_vals, last_updated = winreg.QueryInfoKey(this_key)
        

        # Cache the children so we can access each one using its
        # individual index, even if the child will be destroyed 
        # by the caller, which would change the key count used by EnumKey.
        # Otherwise we must use two different calls, 
        # i) winreg.EnumKey(this_key, 0) when walking destructively and
        # ii) winreg.EnumKey(this_key, i) when walking non-destructively.
        children = [winreg.EnumKey(this_key, i) for i in range(num_sub_keys)]


        for child in children:
            yield from _walk_deepest_first_dfs(
                            key_name = f'{key_name}\\{child}' if key_name else child,
                            root_key = root_key, 
                            access = access, 
                            max_depth = max_depth-1,
                            )
        
        yield root_key, this_key, key_name

        this_key.Close()


def _walk_all_roots_deepest_first_dfs(
    key_name: str,
    root_keys: Iterable[Union[winreg.HKEYType, int]] = ROOT_KEYS,
    access: int = winreg.KEY_READ,
    max_depth: int = 5,
    )-> Iterator[tuple[winreg.HKEYType, winreg.HKEYType, str]]:

    for root_key in root_keys:

        # Catch OSErrors, e.g. for obsolete
        # winreg.HKEY_DYN_DATA & winreg.HKEY_PERFORMANCE_DATA
        try:
            with winreg.OpenKey(root_key, ''):
                pass
        except OSError:
            continue

        print(f'\nKeys under {ROOT_KEYS[root_key]}:')

        try:
            yield from _walk_deepest_first_dfs(
                                    key_name=key_name,
                                    root_key=root_key,
                                    access=access,
                                    max_depth=max_depth,
                                    )
        except FileNotFoundError:
            print()


def get_names_vals_and_types(key: winreg.HKEYType) -> Iterator[tuple[str, Any, int]]:

    __, num_vals, __ = winreg.QueryInfoKey(key)
    for i in range(num_vals):
        yield winreg.EnumValue(key, i)

        
SearchResult = tuple[winreg.HKEYType, winreg.HKEYType, str, str, str, Any]

def _pprint_result(result: SearchResult, prefix: str = ''):

    root, key, name, key_name, val_name, val = result

    print(f'{prefix}{name}', end='')
    
    if val_name:
        print(f', for: {val_name=}, {val=}', end='')

    print(f' at: {key_name}')


def _search_keys_and_names(
    strs: Container[str], 
    keys_and_names: Iterator[tuple[winreg.HKEYType, winreg.HKEYType, str]],
    ) -> Iterator[SearchResult]:



    for root, key, name in keys_and_names:
        vals = {val_name: val 
                for val_name, val, __ in get_names_vals_and_types(key)
               }
            
        display_name = vals.get('DisplayName',
                                next((val 
                                      for val_name, val in vals.items()
                                      if 'name' in val_name.lower()
                                     ),
                                     ''
                                    )
                                )


        if any(search_str in name.rpartition('\\')[2] for search_str in strs):
            yield root, key, display_name, name, '', ''
        else:
            for val_name, val in vals.items():
                if any(search_str in str(val) for search_str in strs):
                    yield root, key, display_name, name, val_name, val
                    break


def _matching_uninstallers(strs: Container[str]) -> Iterator[SearchResult]:
    yield from _search_keys_and_names(strs,
                                      _walk_deepest_first_dfs(
                                            key_name=UNINSTALLERS_REGISTRY_KEY,
                                            root_key=winreg.HKEY_LOCAL_MACHINE,
                                            ),
                                      )     

def system_path_registry_entries():
    yield r'HKEY_CURRENT_USER\Environment'
    yield r'HKEY_USERS\S-1-5-21-3648489184-4041388956-2286264135-1001\Environment'


def check_uninstallers(strs: Container[str]):
    
    found = []

    for result in _matching_uninstallers(strs):
        found.append(result)
        _pprint_result(prefix='Matching uninstaller: ', result=result)


    if found:
        raise Exception('Matching uninstaller(s) found. Run these uninstallers first before purging. ')


def search_registry_keys(args: Iterable[str]) -> None:
    print('Searching for matching Registry keys.  Run with "--purge-registry" to delete the following registry keys:')
    for result in _search_keys_and_names(
                        args,
                        _walk_all_roots_deepest_first_dfs(''),
                        ):
                        #
        _pprint_result(prefix='Matching registry key: ', result=result)
                            

def backup_hive(key_name: str):
    # >>> for name in ('HKLM','HKCU','HKCR','HKU','HKCC'):

    backup_name = key_name.replace('//','_').lower()

    subprocess.run(f'reg export {key_name} {backup_name}.reg')


def _purge_registry_keys(args: Iterable[str]) -> None:
    print('WARNING!! Deleting the following Registry keys: ')

    backed_up = set()
    
    for result in _search_keys_and_names(
                        args,
                        _walk_all_roots_deepest_first_dfs(''),
                        ):
                        #

        _pprint_result(prefix='Matching registry key: ', result=result)

        root, key, name, key_name, val_name, val = result

        confirmation = input(f'Delete registry key: {key_name}? (y/n/quit) ')

        if confirmation.lower().startswith('q'):
            break

        if confirmation.lower() == 'y':
            if root not in backed_up:
                backup_hive(ROOT_KEYS[root_key])
                backed_up.add(root)

            # Context manager opened in _walk_deepest_first_dfs
            winreg.DeleteKey(key, '')


def purge_registry_keys(args: Iterable[str]) -> None:
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

