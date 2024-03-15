from typing import Iterator, Any, Collection, Optional

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

def search_registry_for_text(strs: Collection[str], max_depth: Optional[int] = 5):
    yield from global_root.search_key_and_subkeys_for_text(strs, max_depth=max_depth)




def search_registry_keys(
    args: Collection[str],
    max_depth: Optional[int] = None,
    ) -> None:



    check_uninstallers(args)

    print(f'Searching for Registry keys containing: {args}.\n'
          f'Run with "--purge-registry" to delete the following registry keys: '
         )
    
    for result in search_registry_for_text(args,  max_depth):
        
        key, __, __, __, __ = result
        if key.contains_path_env_variable():
            _pprint_result(prefix='Match found in System Path registry key: ', result=result)
        else:
            _pprint_result(prefix='Matching registry key: ', result=result)




def _purge_registry_keys(
    args: Collection[str],
    max_depth: Optional[int] = None,
    ) -> None:
    print('WARNING!! Deleting the following Registry keys: ')



    for result in search_registry_for_text(args,  max_depth):
        key, __, __, __, vals = result

        contains_path_env_variable = key.contains_path_env_variable()


        if contains_path_env_variable:

            
            _pprint_result(prefix='Match found in System Path registry key: ', result=result)

            confirmation = ''

            for path_val_name in key.names_of_path_env_variables():
                
                contains_path_env_variable = True

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
                        type_ = 1,
                        )

            if confirmation.lower().startswith('q'):
                break
            else:
                continue


                


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
