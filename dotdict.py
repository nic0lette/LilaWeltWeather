"""
DotDict class from `dotdict(dict)`: https://github.com/Gallopsled/pwntools
"""


class DotDict(dict):
    """Wrapper to allow dotted access to dictionary elements.

    Is a real :class:`dict` object, but also serves up keys as attributes
    when reading attributes.

    Supports recursive instantiation for keys which contain dots.

    Example:

        >>> x = DotDict()
        >>> isinstance(x, dict)
        True
        >>> x['foo'] = 3
        >>> x.foo
        3
        >>> x['bar.baz'] = 4
        >>> x.bar.baz
        4
    """

    def __getattr__(self, name):
        if name in self:
            if type(self[name]) == dict:
                return DotDict(self[name])
            return self[name]

        name_dot = name + '.'
        name_len = len(name_dot)
        subkeys = {k[name_len:]: self[k] for k in self if k.startswith(name_dot)}

        if subkeys:
            return DotDict(subkeys)
        raise AttributeError(name)
