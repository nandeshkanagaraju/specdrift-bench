from typing import Callable

from jobs.backoff import MAX_ATTEMPTS, retry_delay
from jobs.queue import Job, JobQueue

TIMEOUT_SECONDS = 30


class Worker:
    def __init__(self, queue: JobQueue, handlers: dict[str, Callable], clock: Callable[[], float]) -> None:
        self.queue = queue
        self.handlers = handlers
        self.clock = clock

    def run_next(self) -> Job | None:
        job = self.queue.dequeue()
        if job is None:
            return None
        job.started_at = self.clock()
        try:
            self.handlers[job.name](job.payload)
            if self.clock() - job.started_at > TIMEOUT_SECONDS:
                raise TimeoutError("timeout")
            job.state = "done"
        except Exception as exc:
            self._fail(job, str(exc))
        return job

    def _fail(self, job: Job, message: str) -> None:
        job.attempts += 1
        job.error = message
        if job.attempts >= MAX_ATTEMPTS:
            self.queue.dead_letter(job)
            return
        job.state = "pending"
        job.available_at = self.clock() + retry_delay(job.attempts)
