import winreg
import enum
import pathlib
from typing import Self, Any, Iterator, Iterable, Container, Hashable
from contextlib import contextmanager 
import warnings

import send2trash

APPDATA = pathlib.Path(os.getenv('APPDATA'))

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


class KeyBackupMaker(abc.ABC):
    @abc.abstractmethod
    def tmp_backup_key(name: str):
        pass

    def consolidate_backups() -> None:
        pass


class CmdKeyBackupMaker(KeyBackupMaker):
    
    prefix: str = 'deleted_and_modified_keys_'

    ext: str = '.reg'

    app_folder_name: str = pathlib.Path(__file__).parent.stem

    backups_dir: pathlib.Path = None

    tmp_dir: pathlib.Path = None

    tmp_backups: set[pathlib.Path] = set()

    @classmethod
    @property
    def backup_file_pattern(cls):
        return f'{cls.prefix}%s{cls.ext}'

    @classmethod
    def get_unused_path(cls, dir_: pathlib.Path) -> pathlib.Path:

        i = 0
        
        while True:
            path = dir_ / (cls.backup_file_pattern % i)
            if path.exists():
                i += 1
                continue
            return path


    @staticmethod
    def _backup_key(name_inc_root: str, path: pathlib.Path) -> None:
        subprocess.run(f'reg export {name_inc_root} {path}')

    @classmethod
    def backup_hive(cls, name: str) -> None:
        assert name in Root.__members__
        cls._backup_key(name, BACKUPS_DIR / f'{name.lower()}{cls.ext}')


    @classmethod
    def tmp_backup_key(cls, name: str, dir_: pathlib.Path = None) -> pathlib.Path:

        if dir_ is None:
            if cls.tmp_dir is None:
                cls.tmp_dir = pathlib.Path(tempfile.gettempdir()) / cls.app_folder_name
                cls.tmp_dir.mkdir(exist_ok = True, parents = True)
            dir_ = cls.tmp_dir

        tmp_file = cls.get_unused_path(dir_)

        cls._backup_key(name, tmp_file)

        cls.tmp_backups.add(tmp_file)

        return tmp_file


    @classmethod
    def consolidate_tmp_backups(
        cls,
        dir_: pathlib.Path = None,
        tmp_backups_dir: pathlib.Path = None,
        ) -> None:

        if dir_ is None:
            if cls.backups_dir is None:
                cls.backups_dir = APPDATA / self.app_folder_name / 'registry_backups'
                cls.backups_dir.mkdir(exist_ok = True, parents = True)
            dir_ = cls.backups_dir


        tmp_backups_dir = tmp_backups_dir or cls.tmp_dir

        # Check for anything else in the directory that matches our pattern
        if tmp_backups_dir is not None:
            tmp_dir_backups = set(tmp_backups_dir.glob(cls.backup_file_pattern % '*'))
            previous_tmp_backups = tmp_dir_backups - cls.tmp_backups
            if previous_tmp_backups:
                warnings.warn(f'Also consolidating {previous_tmp_backups=}')
                cls.tmp_backups |= previous_tmp_backups

        # Reverse for readability, so that parents consolidated before children.
        tmp_backups = reversed(sorted(cls.tmp_backups))

        
        backups_file = cls.get_unused_path(dir_)

        header_written = False

        with backups_file.open('at') as f_w:
            for tmp_backup in tmp_backups:
                with tmp_backup.open('rt') as f_r:
                    for line in f_r:
                        if header_written and line.startswith('Windows Registry Editor '):
                            header_written = True
                            continue
                        f_w.write(line)

                send2trash.send2trash(tmp_backup)


class Key:

    def __init__(
        self,
        root: Root, 
        rel_key: str,
        BackupMaker: type = CmdKeyBackupMaker,
        ):
        self.root = root
        self.rel_key = rel_key
        self.BackupMaker = BackupMaker


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


    def walk(self,
             access: int = winreg.KEY_READ,
             max_depth: int | None  = 5,
             skip_children: Callable[[Self], bool] = None,
             ) -> Iterator[Self]:
        """    Depth First Search, with each node's children cached.
               By default the nodes are yielded Bottom-Up, from the 
               depth cap of max_depth upwards, unless a 
               predicate Callable skip_children is specified, (e.g. 
               if all sub keys will be deleted anyway) in which 
               case the nodes are returned Lowest-Up. """
        if max_depth == 0:
            return

        if skip_children is None or not skip_children(self):
            with self.handle(access = access) as handle:
                num_sub_keys, num_vals, last_updated = winreg.QueryInfoKey(handle)

                for child_str in self.children():

                    child = self.__class__(self.root, f'{self.rel_key}\\{child_str}')

                    # Walking the entire Registry can yield wierd non-existent keys
                    # that only their parents know about.
                    if not child.exists():
                        continue

                    yield from child.walk(access = access,
                                          max_depth = None if max_depth is None else max_depth - 1
                                          )
            
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



    def _delete(self, save_backup_first = True) -> None:
        if save_backup_first:
            self.BackupsMaker.tmp_backup_key(str(self))

        with self.handle(access = winreg.KEY_ALL_ACCESS) as handle:
            winreg.DeleteKey(handle, '')

    def delete(self) -> None:
        self._delete(save_backup_first = True)

    def consolidate_backups(self, dir_: pathlib.Path = None):
        self.BackupsMaker.consolidate_tmp_backups(dir_)

