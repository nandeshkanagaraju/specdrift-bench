# Toy shop specification

## Customers

- **R01** A customer MUST be at least 18 years old, and `check_age` MUST raise `ValueError` for anyone younger.

## Pricing

- **R02** An order of 100 or more MUST receive a discount of 10 percent of its total.
- **R03** The total price MUST be the subtotal plus 20 percent tax on the subtotal.
- **R04** An order of 50 or more MUST ship for free, and any smaller order MUST ship for 5.
