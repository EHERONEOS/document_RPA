
# -*- coding: utf-8 -*-
from copy import deepcopy
from wise_utils.db import get_redis_client
from app.config.nacos_config import REDIS_CONFIG

# 通过index创建对应的redis_db
def get_redis_db_client(db_index=15):
    redis_config_new = deepcopy(REDIS_CONFIG)
    redis_config_new['db'] = db_index
    db_redis_client = get_redis_client(redis_config_new)
    return db_redis_client


class RedisClient:
    def __init__(self, db_index=15):
        self.db_redis_client = get_redis_db_client(db_index)

    
    def set_redis_key(self, key, value, ex=None):
        self.db_redis_client.set(name=key, value=value, ex=ex)

    def get_redis_key(self, key):
        return self.db_redis_client.get(name=key)
    
    def delete_redis_key(self, key):
        self.db_redis_client.delete(name=key)