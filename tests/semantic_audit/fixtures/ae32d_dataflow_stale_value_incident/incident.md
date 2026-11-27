# Data-flow defect candidate

The declared contract defines invoice total as (subtotal - discount) + tax.
Inspect the value assigned to discounted and the value actually consumed at
the return sink. Do not infer correctness merely because the intermediate
discounted value is computed.
