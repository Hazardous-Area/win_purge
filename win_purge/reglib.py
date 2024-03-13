import winreg
import enum
import pathlib
import collections
from typing import Self, Any, Iterator, Iterable, Container, Hashable
from contextlib import contextmanager 
import warnings
import atexit

import send2trash

PATH = pathlib.Path(os.getenv('PATH'))

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

    tmp_backups: dict[pathlib.Path, set] = collections.defaultdict(set)

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

        cls.tmp_backups[dir_].add(tmp_file)

        return tmp_file


    @classmethod
    def consolidate_tmp_backups(
        cls,
        dir_: pathlib.Path = None,
        ) -> None:

        if dir_ is None:
            if cls.backups_dir is None:
                cls.backups_dir = APPDATA / self.app_folder_name / 'registry_backups'
                cls.backups_dir.mkdir(exist_ok = True, parents = True)
            dir_ = cls.backups_dir


        for tmp_backups_dir, tmp_backups in cls.tmp_backups.items():

            # Double check for anything else in the directory that 
            # matches our pattern, that failed to be consolidated before
            tmp_dir_backups = set(tmp_backups_dir.glob(cls.backup_file_pattern % '*'))
            previous_tmp_backups = tmp_dir_backups - tmp_backups
            if previous_tmp_backups:
                warnings.warn(f'Also consolidating {previous_tmp_backups=}')
                tmp_backups |= previous_tmp_backups


            
            backups_file = cls.get_unused_path(dir_)

            header_written = False

            with backups_file.open('at') as f_w:
                # Sort and Reverse for readability, so that parents appear before children.
                # Order is most recent first (children backed up before parents), e.g.: 
                # deleted_and_modified_keys_9.reg, ..., deleted_and_modified_keys_0.reg
                for tmp_backup in reversed(sorted(tmp_backups)):
                    with tmp_backup.open('rt') as f_r:
                        for line in f_r:
                            if line.startswith('Windows Registry Editor '):
                                if header_written:
                                    continue
                                else:
                                    header_written = True
                            f_w.write(line)

                    send2trash.send2trash(tmp_backup)

    
    atexit.register(consolidate_backups)


class NoRootError(Exception):
    pass


class BaseKey:


    __do_not_delete_subkeys_of = (
        Root.HKCR,
        )

    __do_not_alter_subkeys_of = (
        Root.HKCC,
        )

    __restricted = {
        Root.HKLM : [r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'.lower(),
                    ],
        Root.HKCU : [r'Environment'.lower(),
                    ],
        }

    __uninstallers = {
        Root.HKLM : [r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'.lower(),
                    ],
        }

    @property
    def root_name(self) -> str:
        # Hook for GlobalRoot
        return self.root.name

    def __str__(self) -> str:
        return f'{self.root_name}\\{self.rel_key}'


    @property
    def sub_key(self) -> str:
        return '\\'.join([self.root.name, self.rel_key])


    @property
    def HKEY_Const(self) -> int:
        return self.root.HKEY_Const


    def _get_handle(self, access = winreg.KEY_READ) -> winreg.HKEYType:

        if self.root is None:
            raise NoRootError(f'Key: {self} does not exist. ')
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

    def restricted(self) -> bool:
        if self.root not in self.__restricted:
            return False
        return self.rel_key.lower() in self.__restricted[self.root]

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



    def iter_names_data_and_types(self) -> Iterator[tuple[str, Any, int]]:
        with self.handle() as key_handle:
            # winreg.QueryInfoKey actually returns a pair & a type. I.e. a triple.
            __, num_name_data_pairs, __ = winreg.QueryInfoKey(key_handle)
            for i in range(num_name_data_pairs):
                yield winreg.EnumValue(key_handle, i)



    def registry_values(self) -> CaseInsensitiveDict:
        retval =  CaseInsensitiveDict() 
        dupes = []
        for name, data, type_ in self.iter_names_data_and_types():
            if name in retval:
                dupes.append(dict(name = name, data = data, type = type_))
            retval[name] = data

        if dupes:
            raise Exception(f"Registry key: {self}'s value contain duplicated names ('keys'): {dupes}")

        return retval





    def names_of_path_env_variables(self) -> Iterator[str]:

        for name, candidate_path in self.registry_values.items():

            if not isinstance(candidate_path, str):
                continue

            # in %PATH% from cmd, the user path is appended to the windows 
            # system path.  So we test for this by iterating from
            # start and end of %PATH%.  This won't find any paths in the middle.

            for iterable in [zip(candidate_path.split(';'), PATH.split(';')),
                            zip(reversed(candidate_path.split(';')), reversed(PATH.split(';'))),
                            ]:

                for reg_path, os_path in iterable:
                    if reg_path != os_path:
                        # Don't return False.  Test next iterable (reversed).
                        break
                    #
                else:
                    # for/ else - if loop did not hit the break statement, 
                    # i.e. if all path entries equalled a corresponding one in
                    # PATH, either from the start of the end.
                    yield name

                    # Don't yield again if the second iterable also tests positive
                    break




    def walk(self,
             access: int = winreg.KEY_READ,
             max_depth: int | None  = 5,
             skip_children: Callable[[BaseKey], bool] = None,
             ) -> Iterator[BaseKey]:
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

                for child in self.children():


                    # Walking the entire Registry can yield wierd non-existent keys
                    # that only their parents know about.
                    if not child.exists():
                        continue

                    yield from child.walk(access = access,
                                          max_depth = None if max_depth is None else max_depth - 1
                                          )
            
        yield self


    def children(self) -> Iterator[BaseKey]:
        
        # Enumerate and store all the child strings at once, so we can 
        # access each one using its
        # individual index, even if the child key will be destroyed 
        # by the caller (which would change the key count used by EnumKey).
        # Otherwise we must use two different calls, 
        # i) winreg.EnumKey(key, 0) when iterating destructively and
        # ii) winreg.EnumKey(key, i) when iterating non-destructively.

        with self.handle() as handle:
            num_sub_keys, __, __ = winreg.QueryInfoKey(handle)
            child_names = [winreg.EnumKey(handle, i) for i in range(num_sub_keys)]

        for child_name in child_names:
            yield self.child_class(self.root, f'{self.rel_key}\\{child_name}')

        



class Key(BaseKey):


    def __init__(
        self,
        root: Root, 
        rel_key: str,
        BackupMaker: type = CmdKeyBackupMaker,
        ):
        if not rel_key:
            raise Exception(f'Keys cannot be created for root keys. '
                            f'Use RootKey instead.  Got: {rel_key=}'
                           )
        self.root = root
        self.rel_key = rel_key
        self.BackupMaker = BackupMaker
        self.child_class = self.__class__



    @classmethod
    def from_str(cls, key_str: str) -> Self:
        prefix, __, rel_key = key_str.partition('\\')
        root = Root.from_str(prefix)
        return cls(root, rel_key)


    def make_tmp_backup(self) -> None:
        self.BackupsMaker.tmp_backup_key(str(self))

    def check_in_alterable_root(self) -> None:
        if self.root in self.__do_not_alter_subkeys_of:
            raise Exception(f'Cannot modify sub keys of: {self.root.value}')

    def check_not_restricted(self) -> None:
        if self.restricted:
            raise Exception(f'Cannot delete restricted key: {self}')

    def _delete(self, save_backup_first: bool = True) -> None:

        self.check_in_alterable_root()

        self.check_not_restricted()
        
        if self.root in self.__do_not_delete_subkeys_of:
            raise Exception(f'Cannot delete sub keys of: {self.root.value}')

        if self.contains_path_env_variable():
            raise Exception(f'Cannot delete key whose value contains system path data: {self}')

        if save_backup_first:
            self.make_tmp_backup()

        with self.handle(access = winreg.KEY_ALL_ACCESS) as handle:
            winreg.DeleteKey(handle, '')

    def delete(self) -> None:
        self._delete(save_backup_first = True)

    def consolidate_backups(self, dir_: pathlib.Path = None) -> None:
        self.BackupsMaker.consolidate_tmp_backups(dir_)

    def _set_registry_value_data(
        self,
        name: str,
        data: Any,
        type_: int = None,
        save_backup_first: bool = True
        ) -> None:

        self.check_in_alterable_root()

        self.check_not_restricted()

        if save_backup_first:
            self.make_tmp_backup()

        if type_ is None:
            type_ = 1

        with self.handle(access = winreg.KEY_ALL_ACCESS) as handle:
            winreg.SetValueEx(
                key = handle, 
                value_name = path_val_name, 
                reserved = 0, 
                type = type_,
                value = data,    
                )

    def set_registry_value_data(
        self,
        name: str,
        data: Any,
        type_: int = None,
        ) -> None:

        self._set_registry_value_data(name, data, type_, save_backup_first=True)

        

class RootKey(BaseKey):

    rel_key = ''
    child_class = Key

    def __init__(self, root: Root):
        self.root = root


class GlobalRoot(BaseKey):


    HKEY_Const = None
    root_name = 'Pseudo Global Root'
    rel_key = ''
    root = None
    exists = lambda: False
    registry_values = lambda: {}

    def children(self) -> Iterator[RootKey]:
        for root in Root:
            yield RootKey(root)

uninstallers_keys = [Key(root, rel_key) for root, rel_key in Key.__uninstallers.items()]