# Wallet Specification

The wallet service holds accounts and moves money between them, charging a fee and
enforcing a daily limit. Every rule below is atomic and testable.

## Accounts

- **R01** An account MUST be opened with a balance greater than or equal to 0.
- **R02** Opening an account with a negative balance MUST raise `InvalidAmount`.
- **R03** Opening an account with an id that already exists MUST raise `DuplicateAccount`.

## Transfers

- **R04** A transfer amount MUST be greater than 0.
- **R05** A transfer amount of 0 or less MUST raise `InvalidAmount`.
- **R06** A transfer MUST raise `InsufficientFunds` when the sender's balance does not cover the amount plus the fee.
- **R07** The daily total of transfer amounts sent from one account MUST NOT exceed 1000.00.
- **R08** A transfer that would breach R07 MUST raise `DailyLimitExceeded`.
- **R09** A frozen account MUST NOT send money, and the attempt MUST raise `AccountFrozen`.
- **R10** The sender MUST be debited only after every transfer check has passed.

## Fees and audit

- **R11** The transfer fee MUST be 1% of the amount, with a minimum of 0.10 and a maximum of 5.00, rounded to 2 decimal places.
- **R12** The audit entry for a transfer MUST be appended after both balances have been updated.
- **R13** `statement` MUST return an account's audit entries newest first.
