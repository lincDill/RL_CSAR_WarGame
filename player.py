class Player:
    def __init__(self, role, available_cards):
        self.role = role
        self.available_cards = available_cards
        self.starting_hand = []
        self.hand = []
        self.played_cards = []

    def select_card(self, cards):
        self.starting_hand.append(cards)
        self.hand.append(cards)


    def play_card(self, card):
        if card not in self.hand:
            return None  # Card not in hand, cannot play it

        self.hand.remove(card)
        self.played_cards.append(card)

        return card  # Return the played card for further processing

    def choose_card(self, prompt="Choose a card to Play: "):
        # show player hand
        print(f"{self.role} Player's Hand:")

        for i, card in enumerate(self.hand):
            print(f"{i + 1}. {card.name} (original strength: {card.strength}) - Targets: {', '.join(card.target_categories)}")
            # Prints strength if attack card
            if card.strength != 0:
                print(f"     Current strength: {card.current_strength()}")
            # Prints card effect if it has one
            if card.effects:
                print(f"     Effect: {card.source_text.get('effect','')}")
            print("\n") #adds a line of seperation btw cards
            
        while True:
            try:
                choice = int(input(prompt))

                if 1 <= choice <= len(self.hand):
                    return self.hand[choice - 1]

                print("Invalid Choice...")

            except ValueError:
                print("Please enter a valid number.")

            

        if self.hand:
            return self.hand[0]  # For now, just return the first card in hand
        return None

    def choose_starting_card(self):
        available_choices = [
            card
            for card in self.available_cards
            if card not in self.starting_hand
        ]

        print(f"\n{self.role} Available Cards: ")

        for i, card in enumerate(available_choices):
            print(f"{i + 1}. {card.name} Strength: {card.strength}")
            if card.source_text.get("effect"):
                print(f"     Effect: {card.source_text.get('effect')}")

        while True:
            try: 
                choice = int(input("Choose a card for your loadout: "))
                if 1 <= choice <= len(available_choices):
                    return available_choices[choice - 1]
                print("Invalid Choice.")

            except ValueError:
                print("Please enter a valid number.")

    def choose_card_usage(self):
        while True:
            print("\n1. Attack")
            print("2. Use Effect")

            try:
                choice = int(input("Choose how to use this card: "))

                if choice == 1:
                    return "attack"

                if choice == 2:
                    return "effect"

                print("Invalid Choice")

            except ValueError:
                print("Please enter a valid number")

    def reset_hand(self):
        self.hand = self.starting_hand.copy()
        self.played_cards = []
