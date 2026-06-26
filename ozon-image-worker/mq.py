"""RabbitMQ 消息队列轻封装（pika）。独立模块。"""

from __future__ import annotations

import json
import os
from typing import Callable

GEN_JOB_QUEUE = "ozon_gen_jobs"


def _mq_config() -> dict:
    return {
        "host": os.environ.get("RABBITMQ_HOST") or "124.223.39.167",
        "port": int(os.environ.get("RABBITMQ_PORT") or 5672),
        "username": os.environ.get("RABBITMQ_USER") or "admin",
        "password": os.environ.get("RABBITMQ_PASS") or "ozon_worker_mq_2026",
    }


def _connect():
    import pika
    cfg = _mq_config()
    creds = pika.PlainCredentials(cfg["username"], cfg["password"])
    params = pika.ConnectionParameters(
        host=cfg["host"], port=cfg["port"], credentials=creds,
        heartbeat=600, blocked_connection_timeout=300,
    )
    return pika.BlockingConnection(params)


def consume_gen_jobs(callback: Callable[[int, int, int, str], None]) -> None:
    """阻塞消费：每条消息调 callback(job_id, draft_id, target, mode)；成功返回才 ack。"""
    conn = _connect()
    try:
        ch = conn.channel()
        ch.queue_declare(queue=GEN_JOB_QUEUE, durable=True)
        ch.basic_qos(prefetch_count=1)

        def _handle(ch, method, _properties, body):
            msg = json.loads(body.decode("utf-8"))
            mode = str(msg.get("mode") or "plan")
            try:
                callback(int(msg["job_id"]), int(msg["draft_id"]), int(msg["target"]), mode)
            except Exception:
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            else:
                ch.basic_ack(delivery_tag=method.delivery_tag)

        ch.basic_consume(queue=GEN_JOB_QUEUE, on_message_callback=_handle)
        ch.start_consuming()
    finally:
        conn.close()
