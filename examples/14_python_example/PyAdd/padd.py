def mean(xs):
    return sum(xs) / len(xs)

def scale(x, s):
    return x * s

def normalize(xs):
    m = sum(xs) / len(xs)
    return [(x - m) for x in xs]

def describe(d):
    return {k: v * 2 for k, v in d.items()}
def add(a,b):
    return a + b