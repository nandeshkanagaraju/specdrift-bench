# Task queue

A small in-memory job queue with priorities, retries and a dead-letter list.
Every rule below is one requirement.

## Ordering and capacity

- **R01** Jobs MUST be dequeued highest priority first, and first-in first-out within the same priority.
- **R02** The queue MUST hold at most 100 pending jobs; enqueueing beyond that MUST raise `QueueFull`.
- **R03** Enqueueing a job with an idempotency key that is already in the queue MUST return the existing job id and MUST NOT create a new job.
- **R04** A cancelled job MUST NOT be executed.

## Retries

- **R05** A job MUST be tried at most 4 times.
- **R06** The delay before retry number n MUST be 2 to the power n seconds, capped at 60 seconds.
- **R07** A job that fails its last attempt MUST be moved to the dead-letter list.
- **R08** A dead-lettered job MUST keep the error message of its last failure.

## Execution

- **R09** The worker MUST record `started_at` before it calls the handler.
- **R10** A handler that runs longer than 30 seconds MUST cause the job to be marked failed with the reason `timeout`.
