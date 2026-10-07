"""The code the checker should read. R01 is wrong on purpose."""

START = 3
MAX = 10


class Overflow(Exception):
    pass


class Counter:
    def __init__(self) -> None:
        self.value = START

    def add(self, amount: int) -> int:
        if self.value + amount > MAX:
            raise Overflow()
        self.value += amount
        return self.value
