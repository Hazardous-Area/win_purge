from typing import Iterator, Any, Collection

from . import reglib




def _pprint_result(result: reglib.SearchResult, prefix: str = ''):

    key, display_name, val_name, val, vals = result

    print(f'{prefix}{display_name}', end='')

    name_of_OS_path_data_entry_name = next(key.names_of_path_env_variables(), None)

    if name_of_OS_path_data_entry_name is not None:
        print(f', includes {name_of_OS_path_data_entry_name}: {vals[name_of_OS_path_data_entry_name]}')
    elif val_name:
        print(f', for: {val_name=}, {val=}', end='')

    print(f' at: {key}')




def _matching_uninstallers(strs: Collection[str]) -> Iterator[reglib.SearchResult]:
    for uninstaller_key in reglib.uninstallers_keys:
        yield from uninstaller_key.search_key_and_subkeys_for_text(
                                    strs,
                                    search_children_of_keys_containing_text = True,
                                    )
        
   



def check_uninstallers(strs: Collection[str]):
    
    found = []

    for result in _matching_uninstallers(strs):
        found.append(result)
        _pprint_result(prefix='Matching uninstaller: ', result=result)


    if found:
        raise Exception('Matching uninstaller(s) found. Run these uninstallers first before purging. ')


global_root = reglib.GlobalRoot()

def get_path_keys_and_other_keys(strs: Collection[str]):
    path_keys = []
    other_keys = []
    for result in global_root.search_key_and_subkeys_for_text(strs):
        key, __, ___, ____, _____ = result
        if key.contains_path_env_variable():
            path_keys.append(result)
        else:
            other_keys.append(result)

    return path_keys, other_keys


def search_registry_keys(args: Collection[str]) -> None:
    print('Searching for matching Registry keys.  Run with "--purge-registry" to delete the following registry keys:')
    
    path_keys, other_keys = get_path_keys_and_other_keys(args)
    
    for result in path_keys:
        _pprint_result(prefix='Match found in System Path registry key: ', result=result)

    for result in other_keys:
        _pprint_result(prefix='Matching registry key: ', result=result)




def _purge_registry_keys(args: Collection[str]) -> None:
    print('WARNING!! Deleting the following Registry keys: ')


    path_keys, other_keys = get_path_keys_and_other_keys(args)

    for result in path_keys:
        key, __, __, __, vals = result


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
                writeable_key = reglib.ReadAndWritableKey.from_key(key)
                writeable_key.set_registry_value_data(
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
            deletable_key = reglib.DeletableKey.from_key(key)
            deletable_key.delete()


def purge_registry_keys(args: Collection[str]) -> None:
    check_uninstallers(args)
    _purge_registry_keys(args)
