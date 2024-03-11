

# https://github.com/JamesParrott/sDNA_GH/blob/f2ada568abe760023f21006353aaa24ee8d37d9d/sDNA_GH/custom/skel/tools/helpers/funcs.py#L85
# def windows_installation_paths(names):
#     #type(str/Sequence(str)) -> list(str)
#     r""" Yields possible installation paths on Windows for an 
#         un-located app named name.

#         for each name in names, yields:
#             all paths on the system path with name as a substring
#             r'C:' + '\\' name
#             r'C:\Program Files' + '\\'name
#             r'C:\Program Files (x86)' + '\\'name
#             e.g. r'C:\Users\USER_NAME\AppData\Roaming' + '\\'name

#     """
#     if isinstance(names, basestring):
#         names = [names]
#     for name in names:
#         for path in os.getenv('PATH').split(';'):
#             if name in path:
#                 yield path 
#         yield os.path.join(os.getenv('SYSTEMDRIVE'), os.sep, name)# r'C:\' + name
#         # os.sep is needed.  os.getenv('SYSTEMDRIVE') returns c: on Windows.
#         #                    assert os.path.join('c:', 'foo') == 'c:foo'
#         yield os.path.join(os.getenv('PROGRAMFILES'), name)
#         yield os.path.join(os.getenv('PROGRAMFILES(X86)'), name)
#         yield os.path.join(os.getenv('APPDATA'), name)
#         yield os.path.join(os.getenv('LOCALAPPDATA'), name)
#         yield os.path.join(os.getenv('LOCALAPPDATA'), 'Programs', name)