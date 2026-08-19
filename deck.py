import random

class Deck:
    def __init__(self, name, cards):
        self.name = name
        self.cards = cards.copy()

    def shuffle(self):
        random.shuffle(self.cards)

    def draw_one_card(self):
        if len(self.cards) == 0:
            return None
        return self.cards.pop(0)

    def draw_card(self, amount=1):
        drawn_cards = []

        for _ in range(amount):
            if len(self.cards) == 0:
                break

            drawn_cards.append(self.cards.pop())

        return drawn_cards

    def __len__(self):
        return len(self.cards)