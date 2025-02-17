from __future__ import annotations
import os
import abc
from typing import (
    Self,
    Any,
    Iterator,
    Iterable,
    Hashable,
    Callable,
    Optional,
    Type,
    Collection,
)
import winreg
import enum
import pathlib
import collections
import contextlib
import warnings
import atexit
import subprocess
import tempfile
import functools

import send2trash  # type: ignore


def getenv(name: str) -> str:
    # Convenience function for brevity and to pass type checking
    return os.getenv(name) or ""


PATH = getenv("PATH")

APPDATA = pathlib.Path(getenv("APPDATA"))

ROOT_KEYS = {
    winreg.HKEY_CLASSES_ROOT: "HKCR",
    winreg.HKEY_CURRENT_CONFIG: "HKCC",
    winreg.HKEY_CURRENT_USER: "HKCU",
    winreg.HKEY_DYN_DATA: "HKDD",
    winreg.HKEY_LOCAL_MACHINE: "HKLM",
    winreg.HKEY_PERFORMANCE_DATA: "HKPD",
    winreg.HKEY_USERS: "HKU",
}


class Root(enum.Enum):
    HKCR = "HKEY_CLASSES_ROOT"
    HKCC = "HKEY_CURRENT_CONFIG"
    HKCU = "HKEY_CURRENT_USER"
    HKDD = "HKEY_DYN_DATA"
    HKLM = "HKEY_LOCAL_MACHINE"
    HKPD = "HKEY_PERFORMANCE_DATA"
    HKU = "HKEY_USERS"

    @classmethod
    def from_str(cls, str_: str) -> Self:
        str_ = str_.upper()

        # Full name
        if str_ in cls:
            return cls(str_)

        # Abbreviation
        if str_ in cls.__members__:
            return cls[str_]

        raise Exception(f"Non-existent Windows Registry root key: {str_}")

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

    def __init__(self, items: Iterable[tuple[Hashable, Any]] = []):
        super().__init__((self._lower_if_str(k), v) for k, v in items)

    def __getitem__(self, k: Hashable):
        k = self._lower_if_str(k)
        return super().__getitem__(k)

    def __setitem__(self, k: Hashable, v: Any):
        k = self._lower_if_str(k)
        super().__setitem__(k, v)


class KeyBackupMaker(abc.ABC):
    def __init__(self):
        atexit.register(self.consolidate_tmp_backups)

    @classmethod
    @abc.abstractmethod
    def make_tmp_backup_of_registry_key(cls, name: str):
        pass

    def consolidate_tmp_backups(self, dir_: Optional[pathlib.Path]) -> None:
        pass

    backs_up_sub_keys_too = False


class CmdKeyBackupMaker(KeyBackupMaker):
    prefix: str = "deleted_and_modified_keys_"

    ext: str = ".reg"

    app_folder_name: str = pathlib.Path(__file__).parent.stem

    backups_dir: pathlib.Path | None = None

    tmp_dir: pathlib.Path | None = None

    tmp_backups: dict[pathlib.Path, set] = collections.defaultdict(set)

    backup_file_pattern = f"{prefix}%s{ext}"

    backs_up_sub_keys_too = True

    _shared_instance: Optional[Self] = None

    @classmethod
    def get_shared_instance(cls) -> Self:
        cls._shared_instance = cls._shared_instance or cls()
        return cls._shared_instance

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
    def _backup_registry_key(name_inc_root: str, path: pathlib.Path) -> None:
        subprocess.run(f'reg export "{name_inc_root}" "{path}"')

    @classmethod
    def make_tmp_backup_of_registry_key(
        cls,
        name: str,
        dir_: Optional[pathlib.Path] = None,
    ) -> pathlib.Path:
        if dir_ is None:
            if cls.tmp_dir is None:
                cls.tmp_dir = pathlib.Path(tempfile.gettempdir()) / cls.app_folder_name
                cls.tmp_dir.mkdir(exist_ok=True, parents=True)
            dir_ = cls.tmp_dir

        tmp_file = cls.get_unused_path(dir_)

        cls._backup_registry_key(name, tmp_file)

        cls.tmp_backups[dir_].add(tmp_file)

        return tmp_file

    def consolidate_tmp_backups(
        self,
        dir_: Optional[pathlib.Path] = None,
    ) -> None:
        if dir_ is None:
            if self.backups_dir is None:
                self.backups_dir = APPDATA / self.app_folder_name / "registry_backups"
                self.backups_dir.mkdir(exist_ok=True, parents=True)
            dir_ = self.backups_dir

        for tmp_backups_dir, tmp_backups in self.tmp_backups.items():
            # Double check for anything else in the directory that
            # matches our pattern, that failed to be consolidated before
            tmp_dir_backups = set(tmp_backups_dir.glob(self.backup_file_pattern % "*"))
            previous_tmp_backups = tmp_dir_backups - tmp_backups
            if previous_tmp_backups:
                warnings.warn(f"Also consolidating {previous_tmp_backups=}")
                tmp_backups |= previous_tmp_backups

            backups_file = self.get_unused_path(dir_)

            header_written = False

            with backups_file.open("at", encoding="utf16") as f_w:
                # Sort and Reverse for readability, so that parents appear before children.
                # Order is most recent first (children backed up before parents), e.g.:
                # deleted_and_modified_keys_9.reg, ..., deleted_and_modified_keys_0.reg
                for tmp_backup in reversed(sorted(tmp_backups)):
                    with tmp_backup.open("rt", encoding="utf16") as f_r:
                        for line in f_r:
                            if line.startswith("Windows Registry Editor "):
                                if header_written:
                                    continue
                                else:
                                    header_written = True
                            f_w.write(f"{line}\n")

                    send2trash.send2trash(tmp_backup)


class NoRootError(Exception):
    pass


class ReadableKey:
    def __init__(
        self,
        root: Optional[Root],
        rel_key: str,
    ):
        if root is None:
            raise Exception(
                f"Key has no root.  Got: {root=}.  Specify one from {list(Root)=}"
            )

        # Tell Mypy self._root can be None in subclasses (i.e. GlobalRoot)
        self._root: Root | None = root
        self._rel_key = rel_key
        self._registry_values: CaseInsensitiveDict | None = None

        # Class specific overridable default class to assign to
        # create specific classed of children from (in
        # self.children and self.walk)
        #
        # if None, uses ReadableKey, to force mutable subclasses
        # and DeletableKeys to be expicitly constructed, instead
        # of making all their children automatically mutable or
        # deletable too (principle of least privilege).
        #
        # Used to define the normal heirarchy:
        # GlobalRoot -> RootKey -> ReadableKey -> ReadableKey -> ...
        self._child_class = ReadableKey

    @property
    def rel_key(self):
        return self._rel_key

    @property
    def root(self):
        return self._root

    @classmethod
    def from_str(cls, str_: str) -> Self:
        prefix, __, rel_key = str_.partition("\\")
        # prefix = '' => Should be GlobalRoot
        root = Root.from_str(prefix) if prefix else None
        return cls(root, rel_key)

    @classmethod
    def from_key(cls, key: ReadableKey) -> Self:
        # Explictly create subclasses with more methods.
        return cls(key.root, key.rel_key)

    # I don't know any detailed reasons why these keys should be in
    # the following protected categories, except that errors occur
    # otherwise, and even regedit refuses to modify some of them.
    _do_not_delete_subkeys_of: dict[Root, list[str]] = {}

    # This category is to forbid winreg.SetValue[Ex] as well as to forbid
    # deletions (of both value names/ values, and child keys)
    _do_not_alter_subkeys_of = {
        Root.HKLM: [
            r"SOFTWARE\WOW6432Node\Microsoft\Windows Search\CrawlScopeManager\Windows\SystemIndex\WorkingSetRules",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows Search\Gather\Windows\SystemIndex\Sites\LocalHost\Paths",
            r"SOFTWARE\Microsoft\Windows Search\CrawlScopeManager\Windows\SystemIndex\WorkingSetRules",
            r"SOFTWARE\Microsoft\Windows Search\Gather\Windows\SystemIndex\Sites\LocalHost\Paths",
        ],
        # Empty string Includes all on this root.
        Root.HKCC: [""],
    }

    # Do not delete value names/ value pairs from, and do not delete
    _restricted = {
        Root.HKLM: [
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ],
        Root.HKCU: [
            r"Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\MuiCache",
        ],
        Root.HKCR: [],
    }

    uninstallers = {
        Root.HKLM: [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        ],
    }

    for k, v in uninstallers.items():
        if k not in _restricted:
            _restricted[k] = []
        _restricted[k].extend(v)

    @property
    def root_name(self):
        # Hook for GlobalRoot
        return self.root.name

    def __str__(self):
        if self.root is None:
            return "\\"
        if not self.rel_key:
            return self.root.name
        return f"{self.root_name}\\{self.rel_key}"

    def __repr__(self):
        if self.root is None:
            return f"<{GlobalRoot.__name__}()>"
        return f"<{self.__class__.__name__}(Root.{self.root.name}, {self.rel_key})>"

    def __hash__(self):
        # Instances for the same registry key will have the same hash,
        # even if e.g. they are of different sub-classes or own
        # different KeyBackupMakers.
        return hash((self.root, self.rel_key))

    @property
    def sub_key(self):
        """Includes the root prefix, e.g. HKLM,
        as that's what winreg expects.
        """
        return str(self)

    @property
    def HKEY_Const(self):
        return self.root.HKEY_Const

    def _get_handle(self, access=winreg.KEY_READ):
        if self.root is None:
            raise NoRootError(f"Key: {self} does not exist. ")
        # Caller is responsible for calling .Close().  Otherwise
        # __del__ is relied on to do this whenever the garbage
        # collector runs, which can be buggy in
        # non-CPython implementations.

        return winreg.OpenKey(
            key=self.HKEY_Const, sub_key=self.rel_key, reserved=0, access=access
        )

    def exists(self) -> bool:
        try:
            self._get_handle()
            return True
        except (OSError, FileExistsError):
            return False

    def restricted(self) -> bool:
        for rel_key in self._restricted.get(self.root, []):
            if self.rel_key.lower().startswith(rel_key.lower()):
                return True
        return False

    def in_alterable_root(self) -> bool:
        for rel_key in self._do_not_alter_subkeys_of.get(self.root, []):
            if self.rel_key.lower().startswith(rel_key.lower()):
                return False
        return True

    def can_delete_subkeys_of_parents(self) -> bool:
        for rel_key in self._do_not_delete_subkeys_of.get(self.root, []):
            if self.rel_key.lower().startswith(rel_key.lower()):
                return False
        return True

    def check_in_alterable_root(self) -> None:
        if not self.in_alterable_root():
            raise Exception(f"Cannot modify sub keys of: {self.root.value}")

    def check_not_restricted(self) -> None:
        if self.restricted():
            raise Exception(f"Cannot delete restricted key: {self}")

    def check_can_delete_subkeys_of_parents(self) -> None:
        if not self.can_delete_subkeys_of_parents():
            raise Exception(f"Cannot delete sub keys of: {self.root.value}")

    @contextlib.contextmanager
    def handle(self, access=winreg.KEY_READ):
        try:
            handle = self._get_handle(access=access)
        except (OSError, FileExistsError):
            raise Exception(
                f"Key: {self} does not exist in Registry "
                f"or is inaccessible under permission: {access}"
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
        if self._registry_values is None:
            self._registry_values = CaseInsensitiveDict()
            dupes = []
            for name, data, type_ in self.iter_names_data_and_types():
                if name in self._registry_values:
                    dupes.append(dict(name=name, data=data, type=type_))
                self._registry_values[name] = data

            if dupes:
                raise Exception(
                    f"Registry key: {self}'s values contain duplicated names ('keys'): {dupes}"
                )

        return self._registry_values

    def names_of_path_env_variables(self) -> Iterator[str]:
        # Speed up walking the registry, so we don't test every
        # str val/val_name pair on every key.
        # Could also require self.rel_name.endswith("Environment")
        if "path" not in self.registry_values():
            return

        # for name, candidate_path in self.registry_values().items():

        candidate_path = self.registry_values()["path"]

        if not isinstance(candidate_path, str) or not candidate_path:
            return

        # in %PATH% from cmd, the user path is appended to the windows
        # system path.  So we test for this by iterating from
        # start and end of %PATH%.  This won't find any paths in the middle.
        #
        # This uses zip, not itertools.zip_longest, so in one of these two
        # options, the user's cwd should be ignored at the end of the iterable,
        # as candidate_path is one shorter.

        candidate_paths = candidate_path.split(";")
        os_env_paths = PATH.split(";")

        for iterable in [
            zip(candidate_paths, os_env_paths),
            zip(reversed(candidate_paths), reversed(os_env_paths)),
        ]:
            for reg_path, os_env_path in iterable:
                if reg_path != os_env_path:
                    # Don't return False.  Test next iterable (same pair reversed).
                    break
                #
            else:
                # for/ else - if loop did not hit the break statement,
                # i.e. if all path entries equalled a corresponding one in
                # PATH, either from the start of the end.
                yield "path"

                # Don't yield again if the second iterable also tests positive
                break

    def contains_path_env_variable(self) -> bool:
        return next(self.names_of_path_env_variables(), None) is not None

    def walk(
        self,
        access: int = winreg.KEY_READ,
        max_depth: int | None = 5,
        skip_children: Optional[Callable[[Self], bool]] = None,
        child_class: Optional[Type[ReadableKey]] = None,
    ) -> Iterator[Self]:
        """Depth First Search, with each node's children cached.
        By default the nodes are yielded Bottom-Up, from the
        depth cap of max_depth upwards, unless a
        predicate Callable skip_children is specified, (e.g.
        if all sub keys will be deleted anyway) in which
        case the nodes are returned Lowest-Up."""

        if max_depth == 0 or (self.root and not self.exists()):
            return

        if skip_children is None or not skip_children(self):
            for child in self.children():
                # Walking the entire Registry can yield wierd non-existent keys
                # that only their parents know about.
                if not child.exists():
                    continue

                yield from child.walk(
                    access=access,
                    max_depth=None if max_depth is None else max_depth - 1,
                )

        yield self

    def strs_in_rel_key(self, strs: Collection[str]) -> Iterator[str]:
        for str_ in strs:
            if str_ in self.rel_key:
                yield str_

    def vals_or_val_names_containing(
        self, strs: Collection[str]
    ) -> Iterator[tuple[str, Any]]:
        for val_name, val in self.registry_values().items():
            for str_ in strs:
                if str_ in val_name or str_ in str(val):
                    yield val_name, val

    def display_name(self) -> str:
        vals = self.registry_values()

        if "DisplayName" in vals:
            return vals["DisplayName"]

        for val_name, val in vals.items():
            if "name" in val_name.lower() and isinstance(val, str):
                return val

        return ""

    def search_for_text(
        self,
        strs: Collection[str],
    ) -> Iterator[SearchResult]:
        vals = self.registry_values()

        display_name = self.display_name()

        for str_ in strs:
            if str_ in display_name:
                yield self, display_name, "", "", vals, str_
                return

        for val_name, val in self.vals_or_val_names_containing(strs):
            yield self, display_name, val_name, val, vals, ""
            return

        for str_ in self.strs_in_rel_key(strs):
            yield self, display_name, "", "", vals, str_
            return

    @staticmethod
    def text_in_key_or_vals(
        key,
        strs: Collection[str],
    ) -> bool:
        return next(key.search_for_text(strs), None) is not None

    def search_key_and_subkeys_for_text(
        self,
        strs: Collection[str],
        search_children_of_keys_containing_text: bool = False,
        max_depth: Optional[int] = 5,
    ) -> Iterator[SearchResult]:
        if search_children_of_keys_containing_text:
            skip_children = None
        else:
            skip_children = functools.partial(self.text_in_key_or_vals, strs=strs)

        for key in self.walk(skip_children=skip_children, max_depth=max_depth):
            yield from key.search_for_text(strs)

    def child_names(self) -> Iterator[str]:
        with self.handle() as handle:
            num_sub_keys, __, __ = winreg.QueryInfoKey(handle)
            for i in range(num_sub_keys):
                yield winreg.EnumKey(handle, i)

    def children(
        self,
        child_class: Optional[Type[ReadableKey]] = None,
    ):
        # Enumerate and store all the child strings at once, so we can
        # access each one using its
        # individual index, even if the child key will be destroyed
        # by the caller (which would change the key count used by EnumKey).
        # Otherwise we must use two different calls,
        # i) winreg.EnumKey(key, 0) when iterating destructively and
        # ii) winreg.EnumKey(key, i) when iterating non-destructively.
        child_names = list(self.child_names())

        # Deletable Keys need to delete their children first
        # but GlobalRoot's default children are RootKey instances,
        # and RootKeys' default children are ReadableKeys (like their grandparents).
        child_class = child_class or self._child_class

        for child_name in child_names:
            child_rel_key = (
                f"{self.rel_key}\\{child_name}" if self.rel_key else child_name
            )
            yield child_class(
                root=self.root,
                rel_key=child_rel_key,
            )


# e.g.               key,         display_name, val_name, val, vals, str_in_rel_key
SearchResult = tuple[ReadableKey, str, str, Any, CaseInsensitiveDict, str]


class ReadAndWritableKey(ReadableKey):
    def __init__(
        self,
        root: Root,
        rel_key: str,
        backup_maker: Optional[KeyBackupMaker] = None,
    ):
        super().__init__(root, rel_key)

        self.backup_maker = backup_maker or CmdKeyBackupMaker.get_shared_instance()

    def make_tmp_backup(self) -> None:
        self.backup_maker.make_tmp_backup_of_registry_key(str(self))

    def consolidate_backups(self, dir_: Optional[pathlib.Path] = None) -> None:
        self.backup_maker.consolidate_tmp_backups(dir_)

    def _set_registry_value_data(
        self,
        name: str,
        data: Any,
        type_: Optional[int] = None,
        save_backup_first: bool = True,
    ) -> None:
        self.check_in_alterable_root()

        if save_backup_first:
            self.make_tmp_backup()

        if type_ is None:
            type_ = 1

        with self.handle(access=winreg.KEY_ALL_ACCESS) as handle:
            winreg.SetValueEx(
                handle,  # key =
                name,  # value_name = name,
                0,  # reserved = 0
                type_,  # type = type_
                data,  # value = data
            )

    def set_registry_value_data(
        self,
        name: str,
        data: Any,
        type_: Optional[int] = None,
    ) -> None:
        self._set_registry_value_data(name, data, type_, save_backup_first=True)


class KeyWithDeletableValueNamesAndValues(ReadAndWritableKey):
    def _delete_value_and_value_name(
        self,
        value_name: str,
        save_backup_first: bool = True,
    ):
        self.check_in_alterable_root()

        self.check_not_restricted()

        if save_backup_first:
            self.make_tmp_backup()

        with self.handle(access=winreg.KEY_ALL_ACCESS) as handle:
            winreg.DeleteValue(handle, value_name)

    def delete_value_and_value_name(self, value_name: str):
        self._delete_value_and_value_name(value_name, save_backup_first=True)


class DeletableKey(ReadAndWritableKey):
    def _delete(self, save_backup_first: bool = True) -> None:
        self.check_in_alterable_root()

        self.check_not_restricted()

        self.check_can_delete_subkeys_of_parents()

        if self.contains_path_env_variable():
            raise Exception(
                f"Cannot delete key whose value contains system path data: {self}"
            )

        if save_backup_first:
            self.make_tmp_backup()

        for key in self.children(child_class=DeletableKey):
            key._delete(save_backup_first=not self.backup_maker.backs_up_sub_keys_too)

        with self.handle(access=winreg.KEY_ALL_ACCESS) as handle:
            winreg.DeleteKey(handle, "")

    def delete(self) -> None:
        self._delete(save_backup_first=True)


class RootKey(ReadableKey):
    def __init__(self, root: Optional[Root], rel_key: str = ""):
        # Keep rel_key in __init__ args so that from_str still works as is.
        if rel_key:
            raise Exception(f"RootKeys cannot have a relative key. Got: {rel_key=}")

        super().__init__(root=root, rel_key="")

        self._child_class = ReadableKey


class GlobalRoot(RootKey):
    def __init__(self, root: Optional[Root] = None, rel_key: str = ""):
        if root is not None:
            raise Exception(f"GlobalRoot has no root itself.  Got: {root=}")

        if rel_key:
            raise Exception(f"GlobalRoot cannot have a relative key. Got: {rel_key=}")

        self._root = None
        self._rel_key = ""

        self._child_class = RootKey

    @property
    def HKEY_Const(self) -> None:
        return None

    @property
    def root_name(self) -> str:
        return "Pseudo Global Root"

    def exists(self):
        return False

    def registry_values(self):
        return CaseInsensitiveDict()

    def child_names(self):
        for root in Root:
            yield root.name

    def children(self, child_class: Optional[Type[ReadableKey]] = None):
        for root in Root:
            yield RootKey(root)


uninstallers_keys = [
    ReadableKey(root, rel_key)
    for root, rel_keys in ReadableKey.uninstallers.items()
    for rel_key in rel_keys
]
