# Curated semantic transcription of QuixBugs' corrected gcd, MIT licensed.
# It is not asserted to be byte-identical to an upstream checkout.
def gcd(a, b):
    if b == 0:
        return a
    return gcd(b, a % b)
