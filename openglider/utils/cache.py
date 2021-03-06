import copy
import time

import numpy as np

import openglider

cache_instances = []


class CachedObject(object):
    """
    An object to provide cached properties and functions.
    Provide a list of attributes to hash down for tracking changes
    """
    hashlist = ()
    cached_properties = []

    def __hash__(self):
        return hash_attributes(self, self.hashlist)

    def __del__(self):
        for prop in self.cached_properties:
            if id(self) in prop.cache:
                prop.cache.pop(id(self))

    def __repr__(self):
        rep = super(CachedObject, self).__repr__()
        if hasattr(self, "name"):
            rep = rep[:-1] + ': "{}">'.format(self.name)
        return rep


def cached_property(*hashlist):
    #@functools.wraps
    class CachedProperty(object):
        def __init__(self, fget=None, doc=None):
            super(CachedProperty, self).__init__()
            self.function = fget
            self.__doc__ = doc or fget.__doc__
            self.__module__ = fget.__module__

            self.hashlist = hashlist
            self.cache = {}

            global cache_instances
            cache_instances.append(self)

        def __get__(self, parentclass, type=None):
            if not openglider.config["caching"]:
                return self.function(parentclass)
            else:
                if not hasattr(parentclass, "_cache"):
                    parentclass._cache = {}

                cache = parentclass._cache
                dahash = hash_attributes(parentclass, self.hashlist)
                # Return cached or recalc if hashes differ
                if self not in cache or cache[self]['hash'] != dahash:
                    res = self.function(parentclass)
                    cache[self] = {
                        "hash": dahash,
                        "value": res
                    }

                return cache[self]["value"]

    return CachedProperty


def clear_cache():
    for instance in cache_instances:
        instance.cache.clear()


def recursive_getattr(obj, attr):
    """
    Recursive Attribute-getter
    """
    if attr == "self":
        return obj
    elif '.' not in attr:
        return getattr(obj, attr)
    else:
        l = attr.split('.')
        return recursive_getattr(getattr(obj, l[0]), '.'.join(l[1:]))


def c_mul(a, b):
    """
    C type multiplication
    http://stackoverflow.com/questions/6008026/how-hash-is-implemented-in-python-3-2
    """
    return eval(hex((int(a) * b) & 0xFFFFFFFF)[:-1])


def hash_attributes(class_instance, hashlist):
    """
    http://effbot.org/zone/python-hash.htm
    """
    value = 0x345678
    for attribute in hashlist:
        el = recursive_getattr(class_instance, attribute)
        # hash
        try:
            thahash = hash(el)
        except TypeError:  # Lists p.e.
            if openglider.config['debug']:
                print("bad cache: "+str(class_instance.__class__.__name__)+" attribute: "+attribute)

            hash_func = getattr(el, "__hash__", None)
            hash_func = None
            if hash_func is not None:
                thahash = el.__hash__()
            else:
                try:
                    thahash = hash(frozenset(el))
                except TypeError:
                    thahash = hash(str(el))

        value = c_mul(1000003, value) ^ thahash
    value = value ^ len(hashlist)
    if value == -1:
        value = -2
    return value


class HashedList(CachedObject):
    """
    Hashed List to use cached properties
    """
    name = "unnamed"
    def __init__(self, data, name=None):
        self._data = None
        self._hash = None
        self.data = data
        self.name = name or getattr(self, 'name', None)

    def __json__(self):
        # attrs = self.__init__.func_code.co_varnames
        # return {key: getattr(self, key) for key in attrs if key != 'self'}
        return {"data": self.data.tolist(), "name": self.name}

    def __getitem__(self, item):
        return self.data[item]

    def __setitem__(self, key, value):
        self.data[key] = np.array(value)
        self._hash = None

    def __hash__(self):
        if self._hash is None:
            self._hash = hash(str(self.data))
            #self._hash = hash("{}/{}".format(id(self), time.time()))
        return self._hash

    def __len__(self):
        return len(self.data)

    def __iter__(self):
        for el in self.data:
            yield el

    def __str__(self):
        return str(self.data)

    def __repr__(self):
        return "<class '{}' name: {}".format(self.__class__, self.name)

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, data):
        if data is not None:
            data = list(data)  # np.array(zip(x,y)) is shit
            self._data = np.array(data)
            #self._data = np.array(data)
            #self._data = [np.array(vector) for vector in data]  # 1,5*execution time
            self._hash = None
        else:
            self._data = []

    def copy(self):
        return copy.deepcopy(self)