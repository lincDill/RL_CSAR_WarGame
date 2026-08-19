import random

class RandomAgent:
    def choose_action(self, state, legal_actions):
        return random.choice(legal_actions)