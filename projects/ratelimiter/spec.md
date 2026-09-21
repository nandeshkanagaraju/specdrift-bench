# Rate Limiter Specification

The rate limiter admits or rejects client requests using one token bucket per client.
Time is supplied by the caller in seconds, so behaviour is fully deterministic.
Every rule below is atomic and testable.

## Buckets

- **R01** Each client MUST have its own token bucket, created on first use.
- **R02** A new bucket MUST start full.
- **R03** The burst limit MUST be 10 tokens.
- **R04** Tokens MUST refill at a rate of 2 tokens per second.
- **R05** A bucket MUST NOT hold more than the burst limit after a refill.

## Admission

- **R06** A request MUST be allowed when the client's bucket holds at least 1 token.
- **R07** An allowed request MUST consume exactly 1 token.
- **R08** A request MUST be rejected with `RateLimited` when the bucket holds fewer than 1 token.
- **R09** A blocked client MUST be rejected with `ClientBlocked` regardless of its token count.
- **R10** A token MUST be consumed only after every admission check has passed.
- **R11** The decision MUST be appended to the log after the token count has been updated.

## Blocking and reporting

- **R12** A client MUST be blocked automatically once it has accumulated 5 rejections.
- **R13** `report` MUST return clients sorted by rejection count, highest first, ties broken by client id ascending.
