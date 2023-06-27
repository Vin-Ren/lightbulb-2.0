import sys
from typing import Dict, Union, Any, TextIO, Iterable

dict_updater = lambda base,updater:(lambda dbase,dupdt:[dbase.update(dupdt), dbase][-1])(base.copy(), updater)


class MultiWritePipe:
    def __init__(self, *target_pipes: TextIO):
        self.target_pipes=target_pipes
    
    def flush(self):
        for pipe in self.target_pipes:
            pipe.flush()
    
    @property
    def closed(self):
        is_closed=0
        for pipe in self.target_pipes:
            is_closed|=pipe.closed
        return is_closed
    
    def write(self, __s: str):
        for pipe in self.target_pipes:
            pipe.write(__s)
    
    def writelines(self, __lines: Iterable[str]):
        for pipe in self.target_pipes:
            pipe.writelines(__lines)
            
    def seek(self, __cookie: int, __whence: int = 0):
        for pipe in self.target_pipes:
            pipe.seek(__cookie, __whence)


class PrettyPrinter:
    _PRINTERS = []
    _DEFAULT_PRINTER = None
    
    def __new__(cls):
        instance = super().__new__(cls)
        cls._PRINTERS.append(instance)
        return instance
    
    @classmethod
    def _get_default(cls):
        if cls._DEFAULT_PRINTER is None:
            cls._DEFAULT_PRINTER = cls()
        return cls._DEFAULT_PRINTER
    
    def __init__(self, debug: bool = False, target_pipe: Union[TextIO,MultiWritePipe] = sys.stdout, defaults: Dict = {}, **kw):
        self.pipe = target_pipe
        self.debug = debug
        self.defaults = {'header_prefix':'|+|', 'converter':str}
        self.defaults.update(dict_updater(defaults, kw))
    
    def set_defaults(self, new_defaults: Dict):
        self.defaults = new_defaults
    
    def update_defaults(self, updater: Dict):
        self.defaults.update(updater)
    
    def make_info(self, header_text: str, header_prefix: str, info_entries: Dict[str,Any], *, with_header: bool = True, converter = str, **kw):
        head = "{header_prefix}{header_text}".format(header_prefix=header_prefix, header_text=header_text)
        max_name_length = len(max(info_entries.keys(), key=len))
        entries = ["{prefix}{entry}".format(prefix=" "*len(header_prefix), entry="{} : {}".format(name.ljust(max_name_length), converter(value))) for name, value in info_entries.items()]
        return [head]+entries if with_header else entries
    
    def print_info(self, header_text: str, info_entries: Dict[str,Any], **kw):
        kwargs = dict_updater(self.defaults, dict_updater({'header_text':header_text, 'info_entries':info_entries}, kw))
        lines = self.make_info(**kwargs)
        self.pipe.write("\n".join(lines)+"\n")
        self.pipe.flush()
    
    def print(self, header_text: str, info_entries: Dict[str,Any], *args, **kw):
        return self.print_info(header_text, info_entries, *args, **kw)
    
    def print_debug(self, header_text: str, info_entries: Dict[str,Any], *args, **kw):
        if self.debug:
            self.print_info(header_text, info_entries, *args, **kw)
