import time
import calendar

from fusion.common.cache_backing_store import BackingStore
from fusion.openstack.common import log as logging
from oslo.config import cfg
from fusion.common import config

logger = logging.getLogger(__name__)


class Cache(object):
    def __init__(self, timeout=None, backing_store=None, store=None):
        self._max_age = self.__default_timeout() if not timeout else timeout
        self._store = store or {}
        self._backing_store = BackingStore.create(backing_store,
                                                  self._max_age)

    def __default_timeout(self):
        return config.safe_get_config("cache", "default_timeout")

    def __call__(self, func):
        if not self.caching_enabled():
            return func

        def wrapped_f(*args, **kwargs):
            key = self.get_hash(func.__name__, *args, **kwargs)
            result = self.try_cache(key)
            if not result:
                result = func(*args, **kwargs)
                self.update_cache(key, result)
            return result

        return wrapped_f

    def caching_enabled(self):
        return 'cache' in cfg.CONF

    def try_cache(self, key):
        if key in self._store:
            birthday, data = self._store[key]
            age = calendar.timegm(time.gmtime()) - birthday
            if age < self._max_age:
                logger.debug("[%s] Cache hit for key %s",
                             self.__class__.__name__, key)
                return data
        elif self._backing_store:
            value = self._backing_store.retrieve(key)
            if value:
                logger.debug("[%s] Cache hit for key %s",
                             self._backing_store.__class__.__name__, key)
                birthday_backing_store = self._backing_store.get_birthday(key)
                birthday = (calendar.timegm(time.gmtime())
                            if not birthday_backing_store
                            else birthday_backing_store)
                self._store[key] = (birthday, value)
                return value
        return None

    def update_cache(self, key, value):
        self._store[key] = (calendar.timegm(time.gmtime()), value)
        logger.debug("[%s] Updated cache for key %s",
                     self.__class__.__name__, key)
        if self._backing_store:
            self._backing_store.cache(key, value)
            logger.debug("[%s] Updated cache for key %s",
                         self._backing_store.__class__.__name__, key)

    def get_hash(self, func_name, *args, **kwargs):
        return str((func_name, args, tuple(sorted(kwargs.items()))))
