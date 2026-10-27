import pytest

from jobs.errors import QueueFull
from jobs.queue import JobQueue
from jobs.worker import Worker


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make(handlers=None):
    clock = Clock()
    queue = JobQueue(clock)
    return queue, Worker(queue, handlers or {"ok": lambda p: None}, clock), clock


def test_priority_order():
    queue, worker, _ = make()
    low = queue.enqueue("ok", 1, priority=1)
    high = queue.enqueue("ok", 2, priority=9)
    assert worker.run_next().id == high
    assert worker.run_next().id == low


def test_capacity():
    queue, _, _ = make()
    for i in range(100):
        queue.enqueue("ok", i)
    with pytest.raises(QueueFull):
        queue.enqueue("ok", 101)


def test_idempotency_key():
    queue, _, _ = make()
    assert queue.enqueue("ok", 1, key="k") == queue.enqueue("ok", 2, key="k")


def test_cancelled_job_is_not_run():
    queue, worker, _ = make()
    job_id = queue.enqueue("ok", 1)
    queue.cancel(job_id)
    assert worker.run_next() is None


def test_job_dies_after_four_failures():
    def boom(payload):
        raise ValueError("bad input")

    queue, worker, clock = make({"boom": boom})
    queue.enqueue("boom", 1)
    for _ in range(4):
        clock.now += 1000
        worker.run_next()
    assert len(queue.dead) == 1


def test_timeout_counts_as_failure():
    queue, worker, clock = make({"slow": lambda p: setattr(clock, "now", clock.now + 40)})
    queue.enqueue("slow", 1)
    job = worker.run_next()
    assert job.error == "timeout"
