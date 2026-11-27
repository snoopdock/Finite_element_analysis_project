def invoice_total(subtotal, discount, tax):
    discounted = subtotal - discount
    return subtotal + tax
