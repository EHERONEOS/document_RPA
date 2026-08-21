
# -*- coding: utf-8 -*-
from copy import deepcopy
from wise_utils.db import get_redis_client
from app.config.nacos_config import REDIS_CONFIG

# 通过index创建对应的redis_db
def get_redis_db_client(db_index=15):
    redis_config_new = deepcopy(REDIS_CONFIG)
    redis_config_new['db'] = db_index
    return get_redis_client(redis_config_new)
