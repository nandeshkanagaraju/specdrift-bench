# Auth gateway

Registers users, logs them in, issues sessions and guards admin actions.
Every rule below is one requirement.

## Passwords

- **R01** A password MUST be at least 12 characters long; otherwise registration MUST raise `WeakPassword`.
- **R02** A password MUST contain at least one digit; otherwise registration MUST raise `WeakPassword`.
- **R03** Passwords MUST be stored only as a salted hash and never as plaintext.

## Login and lockout

- **R04** After 5 consecutive failed logins the account MUST be locked and `AccountLocked` MUST be raised.
- **R05** A successful login MUST reset the failed-login counter to 0.
- **R06** A locked account MUST stay locked for 15 minutes.
- **R07** A login with an unknown username and a login with a wrong password MUST raise the same `InvalidCredentials` error.
- **R08** Every failed login MUST be written to the audit log with the username and MUST NOT include the password.

## Sessions

- **R09** A session MUST expire 30 minutes after its last activity.
- **R10** Logging out MUST invalidate the session.
- **R11** Changing a password MUST revoke every existing session of that user.

## Authorisation

- **R12** Admin actions MUST require the role `admin`; otherwise `Forbidden` MUST be raised.
