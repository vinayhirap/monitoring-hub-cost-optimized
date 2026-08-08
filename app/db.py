# app/db.py
import os
import mysql.connector
from mysql.connector import pooling

_pool = pooling.MySQLConnectionPool(
    pool_name="monitoring_pool",
    pool_size=10,
    pool_reset_session=True,
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", 3307)),      # 3307 = Docker local, 3306 = EC2 prod
    user=os.getenv("DB_USER", "root"),         # root = Docker local, monitor = EC2 prod
    password=os.getenv("DB_PASSWORD", "root123"),
    database=os.getenv("DB_NAME", "monitoring_hub"),
    use_pure=True,
    connection_timeout=10,
)


def get_connection():
    return _pool.get_connection()
