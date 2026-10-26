# Shop checkout

Turns a cart into a paid order: prices it, reserves stock, charges the card.
Every rule below is one requirement.

## Cart

- **R01** A cart MUST NOT be empty; checkout of an empty cart MUST raise `EmptyCart`.
- **R02** Each line quantity MUST be between 1 and 20 inclusive; otherwise checkout MUST raise `InvalidQuantity`.

## Pricing

- **R03** The subtotal MUST be the sum of unit price times quantity over all lines.
- **R04** An order whose subtotal is 100.00 or more MUST receive a 10% discount.
- **R05** The coupon `SAVE5` MUST take 5.00 off the amount after the percentage discount.
- **R06** A coupon MUST NOT bring the amount below 0.
- **R07** Tax MUST be 8% of the amount after discount and coupon, rounded half-up to 2 decimal places.
- **R08** Shipping MUST be free when the amount after discount and coupon is 50.00 or more, otherwise 6.99.

## Stock and payment

- **R09** Stock MUST be reserved before the payment is charged.
- **R10** If stock is insufficient checkout MUST raise `OutOfStock` and MUST NOT charge the payment.
- **R11** If the payment is declined, the reserved stock MUST be released and `PaymentDeclined` MUST be raised.

## Orders

- **R12** Order ids MUST be sequential, starting at `ORD-1000`.
