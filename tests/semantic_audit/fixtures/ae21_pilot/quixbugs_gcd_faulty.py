# Curated semantic transcription of the QuixBugs gcd challenge, MIT licensed.
# It is not asserted to be byte-identical to an upstream checkout.
def gcd(a, b):
    if b == 0:
        return a
    return gcd(a % b, b)
