import pandas as pd
import json
import os

from deck import Deck
from player import Player
from game import Game

def get_keypress():
    if os.name == 'nt': #Windows
        import msvcrt
        return msvcrt.getch().decode('utf-8', errors='ignore')
    else: #macOS / Linux
        import sys, tty, termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, oldsettings)
        return ch

class Card():
    def __init__(self, data):
        self.id = data["id"]
        self.name = data["name"]
        self.card_type = data["card_type"]
        self.deck = data["deck"]

        self.target_categories = data.get("target_categories", [])
        self.strength = data.get("strength")
        self.usage_mode = data.get("usage_mode")
        self.effects = data.get("effects", [])

        self.description = data.get("description", "")
        self.source_text = data.get("source_text", {})

        self.needs_review = data.get("needs_review", False)
        self.review_notes = data.get("review_notes", [])

        # Threat card have these, players do not
        self.phase = data.get("phase")
        self.threat_categories = data.get("threat_categories", [])

        self.strength_modifier = 0

    def current_strength(self):
        if self.strength is None:
            return None

        return max(0, self.strength + self.strength_modifier)

    def __str__(self):
        return f"{self.name} ({self.deck})"

    #def display(self):
    #    print("---- CARD ----")
    #    print(f"Name: {self.name}") 
    #    print(f"Card Type: {self.card_type}")
    #    print(f"Attack Target: {self.attack_target}")
    #    print(f"Strength: {self.strength}")
    #    print(f"Effect: {self.effect}")
    #    print(f"Description: {self.description}")

def import_cards(location):
    with open(location, "r") as f:
        data = json.load(f)

    cards = []

    for card_data in data["cards"]:
        card = Card(card_data)
        cards.append(card)

    return cards

def create_game():
    #Import cards from JSON file
    cards = import_cards("wargame_card_json\\all_cards.json")

    #Verifies that cards were imported correctly
    print(f"Imported {len(cards)} cards from JSON file.\n")

    #Seperates into Player decks
    rescue_deck = [card for card in cards if card.deck == "rescue"]
    strike_deck = [card for card in cards if card.deck == "strike"]
    escort_deck = [card for card in cards if card.deck == "escort"]
    c2_deck = [card for card in cards if card.deck == "c2"]

    #Seperates into other decks
    threat_deck = [card for card in cards if card.card_type == "threat"]
    ip_deck = [card for card in cards if card.card_type == "isolated_personnel"]
    setback_deck = [card for card in cards if card.card_type == "setback"]

    #Seperates Threat deck into phases
    phase_1_threats = [card for card in threat_deck if card.phase == 1]
    phase_2_threats = [card for card in threat_deck if card.phase == 2]
    phase_3_threats = [card for card in threat_deck if card.phase == 3]
    phase_4_threats = [card for card in threat_deck if card.phase == 4]

    #Turns threat lists into deck objects
    phase_1_deck = Deck("Phase 1 Threats", phase_1_threats)
    phase_2_deck = Deck("Phase 2 Threats", phase_2_threats)
    phase_3_deck = Deck("Phase 3 Threats", phase_3_threats)
    phase_4_deck = Deck("Phase 4 Threats", phase_4_threats)

    ip_cards_deck = Deck("Isolated Personnel", ip_deck)
    setback_cards_deck = Deck("Setback Cards", setback_deck)

    
    #Creates player objects with their respective decks
    rescue_player = Player("Rescue", rescue_deck)
    strike_player = Player("Strike", strike_deck)
    escort_player = Player("Escort", escort_deck)
    c2_player = Player("C2", c2_deck)

    #HUMAN INPUT: Gives players their starting hands (for now, just the first 5 cards in their deck)
    #for i in range(5):
    #    print(f"\n--- Loadout Selection {i + 1}/5 ---")
    #    rescue_player.select_card(rescue_player.choose_starting_card())
    #    strike_player.select_card(strike_player.choose_starting_card())
    #    escort_player.select_card(escort_player.choose_starting_card())
    #    c2_player.select_card(c2_player.choose_starting_card())

    #Creates game object with players and decks
    game = Game(
        rescue_player,
        strike_player,
        escort_player,
        c2_player,
        phase_1_deck,
        phase_2_deck,
        phase_3_deck,
        phase_4_deck,
        ip_cards_deck,
        setback_cards_deck
    )
    return game    


def main():

    game = create_game()
    
    game.setup_phase()

    #game.take_action(strike_player, strike_player.hand[0])  # Strike player plays their first card

    #Tests get gurrent player function
    #player = game.get_current_player()
    #print(player.role)

    #Tests turn order and next player function
    #for _ in range(8):
    #    player = game.get_current_player()

    #    print(
    #        f"Turn {game.turn_number}: "
    #        f"{player.role} player's turn."
    #    )

    #    game.next_player()

    #Tests choose card function
    #current_player = game.get_current_player()
    #chosen_card = current_player.choose_card()
    #print(f"You selected: {chosen_card.name} ({chosen_card.card_type})")
    
    # The main Game Loop
    while True:
        player = game.get_current_player()

        print(
            f"\nTurn {game.turn_number} - "
            f"{player.role} Player"
        )

        card = player.choose_card()

        player.play_card(card)

        if game.player_cards_disabled(player):
            print(
                f"{player.role} cards are currently disabled, and is discarded."
            )
            

        
        else:

            if card.usage_mode == "attack_only":
                #Attack a threat    
                if card.strength is not None and card.strength > 0:
                    while True:
                        threat = game.choose_threat()
                        attack_completed = game.engage_threat(card, threat)

                        if attack_completed:
                            break

            elif card.usage_mode == "effect_only":
                # play cards effect
                game.trigger_player_effects(card)
                        
            elif card.usage_mode == "dual_use":
                # ask player if they want to attack or effect
                usage = player.choose_card_usage()

                if usage == "attack":
                    while True:
                        threat = game.choose_threat()

                        attack_completed = game.engage_threat(card, threat)

                        if attack_completed:
                            break

                elif usage == "effect":
                    game.trigger_player_effects(card)

            elif card.usage_mode == "attack_and_effect":
                # Player chooses who to attack first then apply effect
                while True:
                    threat = game.choose_threat()
                    if game.engage_threat(card, threat):
                        break

                game.trigger_player_effects(card)
            

            # Checks to see if phase and game won
            phase_status = game.check_phase_status()
            if phase_status == "complete":
                print(f"\nPhase {game.current_phase} complete!")
                if not game.advance_phase():
                    print("\nAll Phases complete!")
                    print("GAME WON!")
                    break
                continue
            elif phase_status == "failed":
                print(f"\nPhase {game.current_phase} failed!")

                #Draws setback card and checks if game lost
                game_lost = game.draw_setback()
                if game_lost:
                    print("\n Too many setbacks!")
                    print("GAME LOST!")
                    break

                # if game not lost resets phase and retries
                game.retry_phase()
                continue

            game.next_player()
        
        

    
    

if __name__ == "__main__":
    main()