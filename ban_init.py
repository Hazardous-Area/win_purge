import inspect

class X():
    @classmethod
    def from_(cls):
        return cls()

    def __init__(self):
        outer_frame = inspect.getouterframes(inspect.currentframe())[1]
        members = dict(inspect.getmembers(outer_frame.frame))
        caller_name = outer_frame.function
        print(f'{caller_name=}')
        outer_cls_is_X = inspect.currentframe().f_back.f_locals.get('cls') is X
        print(f'{outer_cls_is_X=}')

        caller_code_obj = inspect.currentframe().f_back.f_code
        funcs= [dict(inspect.getmembers(func))['__func__'] for func in (self.from_,)]
        factory_code_objs = [dict(inspect.getmembers(func))['__code__'] for func in funcs]
        print(f'{caller_code_obj in factory_code_objs}')

        if caller_code_obj not in factory_code_objs:
            raise Exception(f'Direct instantiation forbidden.  Use a factory from: {[f'{self.__class__.__name__}.{f.co_name}' for f in factory_code_objs]}')
cls=X
# X()   
print()
X.from_()