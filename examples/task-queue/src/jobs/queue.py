from dataclasses import dataclass, field
from typing import Any, Callable

from jobs.errors import QueueFull

MAX_PENDING = 100


@dataclass
class Job:
    id: int
    name: str
    payload: Any
    priority: int = 0
    key: str | None = None
    attempts: int = 0
    state: str = "pending"
    error: str | None = None
    started_at: float | None = None
    available_at: float = 0.0
    seq: int = 0


class JobQueue:
    def __init__(self, clock: Callable[[], float]) -> None:
        self.clock = clock
        self.jobs: dict[int, Job] = {}
        self.dead: list[Job] = []
        self._next_id = 1

    def pending(self) -> list[Job]:
        return [j for j in self.jobs.values() if j.state == "pending"]

    def enqueue(self, name: str, payload: Any, priority: int = 0, key: str | None = None) -> int:
        if key is not None:
            for job in self.pending():
                if job.key == key:
                    return job.id
        if len(self.pending()) >= MAX_PENDING:
            raise QueueFull()
        job = Job(self._next_id, name, payload, priority, key, seq=self._next_id)
        self.jobs[job.id] = job
        self._next_id += 1
        return job.id

    def cancel(self, job_id: int) -> None:
        job = self.jobs[job_id]
        if job.state == "pending":
            job.state = "cancelled"

    def dequeue(self) -> Job | None:
        now = self.clock()
        ready = [j for j in self.pending() if j.available_at <= now]
        if not ready:
            return None
        job = min(ready, key=lambda j: (-j.priority, -j.seq))
        job.state = "running"
        return job

    def dead_letter(self, job: Job) -> None:
        job.state = "dead"
        job.error = None
        self.dead.append(job)
