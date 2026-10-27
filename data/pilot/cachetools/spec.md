# cachetools specification

## Capacity

- **R01** `Cache.__init__` MUST raise `ValueError` when `maxsize` is negative.
- **R02** `Cache.__setitem__` MUST raise `ValueError` when the size of a value is larger than `maxsize`.
- **R03** `Cache.__setitem__` MUST raise `ValueError` when the size of a value is negative.
- **R04** `Cache.__setitem__` MUST evict items until the new value fits within `maxsize`.

## Mapping behaviour

- **R05** `Cache.pop` MUST raise `KeyError` for a missing key when no default is given.
- **R06** `Cache.setdefault` MUST store the default value and return it when the key is missing.
- **R07** `Cache.clear` MUST reset `currsize` to 0.

## Eviction order

- **R08** `FIFOCache.popitem` MUST remove the key that was inserted first.
- **R09** `FIFOCache.__setitem__` MUST move an updated key to the end of the eviction order.
- **R10** `LRUCache.__getitem__` MUST mark the key it reads as most recently used.
- **R11** `LFUCache.popitem` MUST remove the key with the lowest use count.
- **R12** `LRUCache.popitem` MUST raise `KeyError` when the cache is empty.

## Expiry

- **R13** `TTLCache.__contains__` MUST return `False` for an item whose expiry time has been reached.
- **R14** `TTLCache.__getitem__` MUST raise `KeyError` for an item whose expiry time has been reached.
- **R15** `TTLCache.expire` MUST return the expired `(key, value)` pairs and remove them from the cache.

## Cache keys

- **R16** `hashkey` MUST return equal keys when only the order of the keyword arguments differs.
- **R17** `hashkey` MUST distinguish a positional argument from a keyword argument with the same value.
- **R18** `typedkey` MUST distinguish arguments of different types that compare equal.
- **R19** `methodkey` MUST ignore its first argument.
