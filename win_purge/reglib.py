import winreg
import enum
from typing import Self, Any, Iterator, Iterable, Container, Hashable
from contextlib import contextmanager

ROOT_KEYS = {winreg.HKEY_CLASSES_ROOT: 'HKCR',
             winreg.HKEY_CURRENT_CONFIG: 'HKCC',
             winreg.HKEY_CURRENT_USER: 'HKCU',
             winreg.HKEY_DYN_DATA: 'HKDD',
             winreg.HKEY_LOCAL_MACHINE: 'HKLM',
             winreg.HKEY_PERFORMANCE_DATA: 'HKPD',
             winreg.HKEY_USERS: 'HKU',
            }

class Root(enum.Enum):
    HKCR = 'HKEY_CLASSES_ROOT'
    HKCC = 'HKEY_CURRENT_CONFIG'
    HKCU = 'HKEY_CURRENT_USER'
    HKDD = 'HKEY_DYN_DATA'
    HKLM = 'HKEY_LOCAL_MACHINE'
    HKPD = 'HKEY_PERFORMANCE_DATA'
    HKU = 'HKEY_USERS'

    @classmethod
    def from_str(cls, str_: str) -> Self:
        str_ = str_.upper()
        
        # Full name
        if str_ in cls:
            return cls(str_)
        
        # Abbreviation
        if str_ in cls.__members__:
            return cls[str_]
        
        raise Exception(f'Non-existent Windows Registry root key: {str_}')

    @classmethod
    def from_HKEY_Const(cls, hkey_const: int) -> Self:
        return cls[ROOT_KEYS[hkey_const]]

    @enum.property
    def HKEY_Const(self):
        return getattr(winreg, self.value)


class CaseInsensitiveDict(dict):

    @staticmethod
    def _lower_if_str(k):
        return k.lower() if isinstance(k, str) else k
    
    def __init__(self, items: Iterable[tuple[Hashable, Any]]):
        super().__init__((self._lower_if_str(k), v) for k, v in items)

    def __getitem__(self, k: Hashable):
        k = self._lower_if_str(k)
        return super().__getitem__(k)

    def __setitem__(self, k: Hashable, v: Any):
        k = self._lower_if_str(k)
        super().__setitem__(k, v)



class Key:

    def __init__(self, root: Root, rel_key: str):
        self.root = root
        self.rel_key = rel_key


    @classmethod
    def from_str(cls, key_str: str) -> Self:
        prefix, __, rel_key = key_str.partition('\\')
        root = Root.from_str(prefix)
        return cls(root, rel_key)


    def __str__(self) -> str:
        return f'{self.root.name}\\{self.rel_key}'


    @property
    def sub_key(self) -> str:
        return '\\'.join([self.root.name, self.rel_key])


    @property
    def HKEY_Const(self) -> int:
        return self.root.HKEY_Const


    def _get_handle(self, access = winreg.KEY_READ) -> winreg.HKEYType:
        # May raise OSError.
        # Caller is responsible for calling .Close().  Otherwise
        # __del__ is relied on to do this whenever the garbage
        # collector runs, which can be buggy in 
        # non-CPython implementations.
        return winreg.OpenKey(key = self.HKEY_Const,
                              sub_key = self.sub_key,
                              reserved = 0,
                              access = access
                             )


    def exists(self) -> bool:
        try:
            self._get_handle()
            return True
        except (OSError, FileExistsError):
            return False


    @contextlib.contextmanager
    def handle(self, access = winreg.KEY_READ):
        try:
            handle = self._get_handle(access = access)
        except (OSError, FileExistsError):
            raise Exception(f'Key: {self} does not exist in Registry '
                            f'or is inaccessible under permission: {access}'
                           )
        try:
            yield handle
            # code inside with statement runs
        finally:
            handle.Close()


    def children(self) -> list[str]:
        
        # Enumerate and store all the children at once, so we can 
        # access each one using its
        # individual index, even if the child will be destroyed 
        # by the caller (which would change the key count used by EnumKey).
        # Otherwise we must use two different calls, 
        # i) winreg.EnumKey(key, 0) when iterating destructively and
        # ii) winreg.EnumKey(key, i) when iterating non-destructively.

        with self.handle() as handle:
            num_sub_keys, __, __ = winreg.QueryInfoKey(handle)
            return [winreg.EnumKey(handle, i) for i in range(num_sub_keys)]


    def walk(self, access: int = winreg.KEY_READ, max_depth: int = 5) -> Iterator[Self]:
        """Bottom-up Depth First Search, with each node's children cached. """

        if max_depth == 0:
            return

        with self.handle(access = access) as handle:
            num_sub_keys, num_vals, last_updated = winreg.QueryInfoKey(handle)

            for child_str in self.children():

                child = self.__class__(self.root, f'{self.rel_key}\\{child_str}')

                # Walking the entire Registry can yield wierd non-existent keys
                # that only their parents know about.
                if not child.exists():
                    continue

                yield from child.walk(access = access, max_depth = max_depth-1)
            
            yield self



    def iter_names_vals_and_types(self) -> Iterator[tuple[str, Any, int]]:
        with self.handle() as key_handle:
            # winreg.QueryInfoKey actually returns a pair & a type. I.e. a triple.
            __, num_name_data_pairs, __ = winreg.QueryInfoKey(key_handle)
            for i in range(num_name_data_pairs):
                yield winreg.EnumValue(key_handle, i)

    def vals_dict(self) -> CaseInsensitiveDict:
        retval =  CaseInsensitiveDict() 
        dupes = []
        for name, data, type_ in self.iter_names_vals_and_types():
            if name in retval:
                dupes.append(dict(name = name, data = data, type = type_))
            retval[name] = data

        if dupes:
            raise Exception(f"Registry key: {self}'s value contain duplicated names ('keys'): {dupes}")

        return retval


    def search_keys_and_names(
        strs: Container[str], 
        ) -> Iterator[Self]:



        for key in self.walk():
            vals = self.vals_dict()
                
            # Don't yield subkeys of already yielded keys
            if any(search_str in str(self).rpartition('\\')[2] for search_str in strs):
                yield key
            else:
                for val_name, val in vals.items():
                    if any(search_str in str(val) for search_str in strs):
                        yield key
                        break