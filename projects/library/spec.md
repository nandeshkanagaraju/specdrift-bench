# Library Specification

The library service tracks members, a book catalogue, and the loans between them.
Every rule below is atomic and testable.

## Membership

- **R01** A member MUST be at least 18 years old at registration.
- **R02** Registration MUST raise `UnderageMember` when R01 is not satisfied.
- **R03** Registration MUST raise `DuplicateMember` when the email already belongs to a registered member.

## Catalogue

- **R04** Every book in the catalogue MUST have a unique ISBN.
- **R05** Adding a book whose ISBN is already in the catalogue MUST raise `DuplicateBook`.

## Loans

- **R06** A member MUST NOT hold more than 3 active loans at once.
- **R07** Borrowing MUST raise `LoanLimitExceeded` when R06 would be violated.
- **R08** Borrowing MUST raise `BookUnavailable` when the book has no available copies.
- **R09** A suspended member MUST NOT borrow, and the attempt MUST raise `MemberSuspended`.
- **R10** The available-copy count MUST be decremented only after every borrow check has passed.
- **R11** The audit entry for a loan MUST be appended after the loan has been recorded.

## Fees and reporting

- **R12** The loan period MUST be 14 days from the borrow date.
- **R13** The late fee MUST be 0.50 per day late, capped at 20.00, rounded to 2 decimal places.
- **R14** `list_loans` MUST return a member's active loans sorted by due date, earliest first.
