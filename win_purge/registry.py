import sys
from typing import Iterable, Iterator, Callable, Union, Any, Container
import winreg


ROOT_KEYS = (winreg.HKEY_CLASSES_ROOT,
             winreg.HKEY_CURRENT_CONFIG,
             winreg.HKEY_CURRENT_USER,
             winreg.HKEY_DYN_DATA,
             winreg.HKEY_LOCAL_MACHINE,
             winreg.HKEY_PERFORMANCE_DATA,
             winreg.HKEY_USERS,
            )

UNINSTALLERS_REGISTRY_KEY = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'




def _walk_deepest_first_dfs(
    key_name: str,
    root_key: Union[winreg.HKEYType, int],
    access: int = winreg.KEY_READ,
    max_depth: int = 5,
    )-> Iterator[tuple[winreg.HKEYType, str]]:

    if max_depth == 0:
        return

    with winreg.OpenKey(root_key, key_name, 0, access) as this_key:

        num_sub_keys, num_vals, last_updated = winreg.QueryInfoKey(this_key)
        

        # Cache the children so we can access each one using its
        # individual index, even if the child will be destroyed 
        # by the caller, which would change the key count used by EnumKey.
        # Otherwise we must use two different calls, 
        # i) winreg.EnumKey(this_key, 0) when walking destructively and
        # ii) winreg.EnumKey(this_key, i) when walking non-destructively.
        children = [winreg.EnumKey(this_key, i) for i in range(num_sub_keys)]


        for child in children:
            yield from _walk_deepest_first_dfs(f'{key_name}\\{child}', root_key, access, max_depth-1)
        
        yield this_key, key_name

        # The context manager is not closed until the next next(), 
        # so it is recommended to consume the whole iterator.


def _walk_all_roots_deepest_first_dfs(
    key_name: str,
    root_keys: Iterable[Union[winreg.HKEYType, int]] = ROOT_KEYS,
    access: int = winreg.KEY_READ,
    max_depth: int = 5,
    )-> Iterator[tuple[winreg.HKEYType, str]]:

    for root_key in root_keys:
        yield from _walk_deepest_first_dfs(
                                    key_name=key_name,
                                    root_key=root_key,
                                    access=access,
                                    max_depth=max_depth.
                                    )



def get_names_vals_and_types(key: winreg.HKEYType) -> Iterator[tuple[str, Any, int]]:

    __, num_vals, __ = winreg.QueryInfoKey(key)
    for i in range(num_vals):
        yield winreg.EnumValue(key, i)


SearchResult = tuple[winreg.HKEYType, str, str, str, str, Any]


def _search_keys_and_names(
    strs: Container[str], 
    root_keys: Iterable[str],
    keys_and_names: Iterator[tuple[winreg.HKEYType, str]],
    ) -> Iterator[SearchResult]:
    for key, name in keys_and_names:
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
            yield key, display_name, name, search_str, '', ''
        else:
            for val_name, val in vals.items():
                if any(search_str in str(val) for search_str in strs):
                    yield key, display_name, name, search_str, val_name, val
                    break


def _matching_uninstallers(strs: Container[str]) -> Iterator[SearchResult]:
    yield from _search_keys_and_names(strs,
                                      _walk_deepest_first_dfs(key_name=UNINSTALLERS_REGISTRY_KEY,
                                                              root_key=winreg.HKEY_LOCAL_MACHINE,
                                                             ),
                                      )     


def _pprint_result(result: SearchResult, prefix: str = ''):

    key, name, key_name, str_, val_name, val = result

    print(f'{prefix}{name} for: {str_=}', end='')
    
    if val_name:
        print(f', {val_name=}, {val=}', end='')

    print(f' at: {key_name}')


def check_uninstallers(strs: Container[str]):
    
    found = []

    for result in _matching_uninstallers(strs):
        found.append(result)
        _pprint_result(prefix='Matching uninstaller: ', result)


    if found:
        raise Exception('Matching uninstaller(s) found. Run these uninstallers first before purging. ')


def search_registry_keys(args: Iterable[str]) -> None:
    print('Searching for matching Registry keys.  Run with "--purge-registry" to delete the following registry keys:')
    for root_key in ROOT_KEYS:
        for result in _walk_all_roots_deepest_first_dfs(_walk_deepest_first_dfs('')):
            _pprint_result(prefix='Matching registry key: ', result)
                            



def _purge_registry_keys(args: Iterable[str]) -> None:
    print('WARNING!! Deleting the following Registry keys: ')
    for root_key in ROOT_KEYS:
        for result in _walk_all_roots_deepest_first_dfs(_walk_deepest_first_dfs('')):
            _pprint_result(prefix='Matching registry key: ', result)

            key, name, key_name, str_, val_name, val = result
            confirmation = input(f'Delete registry key: {key_name}? (y/n/quit) ')

            if confirmation.lower().startswith('q'):
                break

            if confirmation.lower() == 'y':

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

