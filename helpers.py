import sys
from typing import Iterable, Iterator, Callable, Union, Any
import winreg



UNINSTALLERS_REGISTRY_KEY = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'




def _walk_deepest_first_dfs(
    key_name: str,
    root_key: Union[winreg.HKEYType, int] = winreg.HKEY_LOCAL_MACHINE,
    access: int = winreg.KEY_READ,
    max_depth: int = 2,
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


def get_names_vals_and_types(key: winreg.HKEYType) -> Iterator[tuple[str, Any, int]]:

    __, num_vals, __ = winreg.QueryInfoKey(key)
    for i in range(num_vals):
        yield winreg.EnumValue(key, i)


def _matching_uninstallers(strs: Iterable[str]) -> Iterator[tuple[winreg.HKEYType, str, str, str, str, Any]]:
    for uninstaller_key, key_name in _walk_deepest_first_dfs(UNINSTALLERS_REGISTRY_KEY, max_depth=2):


        for search_str in strs:
            
            vals = {val_name: val 
                    for val_name, val, __ in get_names_vals_and_types(uninstaller_key)
                   }
            
            name = vals.get('DisplayName',
                            next((val 
                                  for val_name, val in vals.items()
                                  if 'name' in val_name.lower()
                                 ),
                                 ''
                                 )
                           )

            if search_str in key_name.rpartition('\\')[1]:
                yield uninstaller_key, name, key_name, search_str, '', ''
                break

            for val_name, val in vals.items():
                if search_str in str(val):
                    yield uninstaller_key, name, key_name, search_str, val_name, val
                    break

def check_uninstallers(strs: Iterable[str]):
    
    matches = []

    for uninstaller, name, key_name, str_, val_name, val in _matching_uninstallers(strs):
        matches.append(uninstaller)

        print(f'Matching uninstaller: {name} for: {str_=}', end='')
        
        if val_name:
            print(f', {val_name=}, {val=}', end='')

        print(f' at: {key_name}')

    if matches:
        raise Exception('Matching uninstaller(s) found. Run these uninstallers first before purging. ')



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


if __name__ == '__main__':
    # for key in _walk_deepest_first_dfs('SOFTWARE'):
    #     print(key)

    args = sys.argv[1:]

    if not args:
        print('Example usage, searching for ["Microsoft"]')
        args = ['Microsoft']

    check_uninstallers(args)
