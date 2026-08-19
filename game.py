class Game:
    def __init__(
        self,
        rescue_player,
        strike_player,
        escort_player,
        c2_player,
        phase_1_deck,
        phase_2_deck,
        phase_3_deck,
        phase_4_deck,
        ip_deck,
        setback_deck
    ):
        self.players = [
            rescue_player,
            strike_player,
            escort_player,
            c2_player
        ]

        self.turn_order = [
            strike_player,
            c2_player,
            escort_player,
            rescue_player
        ]

        self.current_player_index = 0
        self.turn_number = 1

        self.phase_decks = {
            1: phase_1_deck,
            2: phase_2_deck,
            3: phase_3_deck,
            4: phase_4_deck
        }

        self.ip_deck = ip_deck
        self.setback_deck = setback_deck

        
        self.active_threats = []
        self.active_ip_card = None
        self.active_setbacks = []
        self.active_effects = []

        self.threat_chooser = None
        self.support_chooser = None
        self.setback_chooser = None
        self.discard_chooser = None

        self.total_reward = 0.0
        self.pending_reward = 0.0
        self.reward_log = []

        self.current_phase = 1
        self.threats_per_phase = {
            1: 3,
            2: 4,
            3: 5,
            4: 6
        }

    # returns the current player based on the turn order and current player index
    def get_current_player(self):
        return self.turn_order[self.current_player_index]

    def next_player(self):
        self.current_player_index += 1

        if self.current_player_index >= len(self.turn_order):
            self.current_player_index = 0
            self.reveal_threat_after_turn()
            self.expire_active_effects("turn_end")
            self.turn_number += 1

        

    def take_action(self, player, card):
        current_player = self.get_current_player()

        if player != current_player:
            print(f"It's not {player.role}'s turn.")
            return None

        played_card = player.play_card(card)

        if played_card is None:
            print("Card not in hand, cannot play it.")
            return None

        self.next_player()

        return played_card
    
    #player chooses a threat to engage with from the active threats list
    def choose_threat(self):
        print("\nActive Threats:")

        # Prints list of threats for the phase
        for i, threat in enumerate(self.active_threats):
            self.display_threat(threat, i+1)

        while True:
            try:
                choice = int(input("Choose a threat to engage with: "))

                if 1 <= choice <= len(self.active_threats):
                    selected_threat = self.active_threats[choice -1]

                    if selected_threat.defeated:
                        print("Threat already defeated. Choose a different target.")
                        continue
                    return selected_threat                

                print("Invalid Choice...")

            except ValueError:
                print("Please enter a valid number.")

    # calculates the attack strength of a card against a threat based on matching categories
    def calculate_attack_strength(self, card, threat):
        target_match = any(
            category in card.target_categories
            for category in threat.card.threat_categories
        )

        attack_strength = card.current_strength()

        if target_match:
            return attack_strength

        return attack_strength // 2  # Halve the strength if no matching categories

    # Engages and resolves threat
    def engage_threat(self, card, threat):

        if not threat.face_up:
            threat.reveal()
            print(f"Revealed threat: {threat.card.name} (Strength: {threat.current_strength()}) Categories: {', '.join(threat.card.threat_categories)}")

            #Trigger effects for threats that are on reveal
            self.trigger_threat_effects(threat, "on_reveal")

        attack_strength = self.calculate_attack_strength(card, threat)
        threat_strength = threat.current_strength()

        print(f"\n{card.name} engages {threat.card.name}!")
        print(f"Attack Strength: {attack_strength}")
        print(f"Threat Strength: {threat_strength}")

        #Threat becomes engaged and effects go into effect imediately, then checks if defeated
        threat.engaged = True

        # Effect-only threat
        if threat_strength is None:
            print(
                f"{threat.card.name} is an effect only card"
                "and cannot be attacked."
            )
            return False

        # Inflicts damage to targeted threat
        threat.damage_taken += attack_strength

        # Check to see if threat is defeated
        if threat.current_strength() <= 0:
            threat.defeated = True
            print("Threat defeated!")

            # Reward function: + points
            self.add_reward("threat_defeated")

            self.expire_active_effects("source_removed",source=threat)
        else:
            print(
                "Threat not defeated. It remains active and engaged.\n"
                f"{threat.current_strength()} strength Remains"
            )
            self.trigger_threat_effects(threat, "on_engage")

        return True
            
    def trigger_player_effects(self, card, threat_chooser=None, support_chooser=None):
        for effect in card.effects:
            if effect.get("trigger") == "on_effect_play":
                self.resolve_player_effects(effect, card, threat_chooser=threat_chooser, support_chooser=support_chooser)

    def trigger_threat_effects(self, threat, trigger):

        if self.has_active_effect("suppress_effect", threat):
            print(f"{threat.card.name}'s effect is suppressed.")
            return

        for effect in threat.card.effects:
            if effect.get("trigger") == trigger:
                self.resolve_threat_effect(effect, threat)

    def trigger_ip_effects(self, card, trigger):
        for effect in card.effects:
            if effect.get("trigger") == trigger:
                self.resolve_ip_effect(effect, card)

    def trigger_setback_effects(self, card, trigger):
        # Checks for effect suppression and returns if true
        if self.has_active_effect("suppress_effect", card):
            print(f"{card.name}'s effect is suppressed.")
            return
        for effect in card.effects:
            if effect.get("trigger") == trigger:
                self.resolve_setback_effect(effect, card)

    def resolve_effect(self, effect, source=None, threat_chooser=None, support_chooser=None):
        effect_type = effect["type"]

        if effect_type == "modify_strength":
            source_threat = (
                source
                if isinstance(source, ThreatInstance)
                else None
            )

            affected_targets = self.apply_strength_modifier(effect, source_threat=source_threat, threat_chooser=threat_chooser, support_chooser=support_chooser)

            self.register_active_effect(effect, source=source, targets=affected_targets)

        elif effect_type in {"draw_card", "draw_threat", "draw_setback"}:
            self.apply_draw_card(effect)

        elif effect_type == "reveal_card":
            self.apply_reveal_card(effect)

        elif effect_type == "force_discard":
            self.apply_force_discard(effect)

        elif effect_type == "suppress_effect":
            self.apply_suppress_effect(effect, source=source)

        elif effect_type == "remove_card":
            self.apply_remove_card(effect)

        elif effect_type == "modify_phase_setup":
            self.apply_modify_phase_setup(effect, source=source)

        elif effect_type == "disable_cards":
            self.apply_disable_cards(effect, source=source)

        else:
            print(
                f"Effect not implemented: "
                f"{effect_type}"
            )

    # Normalizes persistent effects
    def register_active_effect(self, effect, source=None, targets=None):
            duration = effect.get("duration", "instant")
    
            # Instant effects do not need to be tracked
            if duration == "instant":
                return None
    
            # Always start targets as a list
            if targets is None:
                targets = []
    
            elif not isinstance(targets, list):
                targets = [targets]
    
            active_effect = ActiveEffect(
                effect=effect,
                source=source,
                targets=targets,
                start_phase=self.current_phase,
                start_turn=self.turn_number
            )
    
            self.active_effects.append(active_effect)
    
            return active_effect

    def expire_active_effects(self, event, source=None):
        remaining_effects = []
        expired_effects = []

        for active_effect in self.active_effects:
            expired = False
            # expires at end/start of turn (kinda broke rn if want full turn i.e. last player plays effect and it only lasts till end of his played card)
            if (
                active_effect.duration == "turn"
                and event == "turn_end"
            ):
                expired = True

            # End of phase effects
            elif (
                active_effect.duration == "phase"
                and event == "phase_end"
            ):
                expired = True

            # Effects that last while source is active
            elif active_effect.duration == "while_source_active":
                if (
                    event == "source_removed"
                    and active_effect.source is source
                ):
                    expired = True

                elif event == "phase_end":
                    expired = True


            # Effects that persist until their source is removed
            elif(
                active_effect.duration == "until_removed"
                and event == "source_removed"
                and active_effect.source is source
            ):
                expired = True


            if expired:
                expired_effects.append(active_effect)
            else:
                remaining_effects.append(active_effect)

        #Update active list 
        self.active_effects = remaining_effects

        # Undo / clean expired effects
        for active_effect in expired_effects:
            effect_type = active_effect.effect["type"]

            # Restore strength when modifier expires (if supressed does not restore)
            if (
                effect_type == "modify_strength"
                and not active_effect.suppressed
            ):
                amount = active_effect.effect["amount"]
                for target in active_effect.targets:
                    target.strength_modifier -= amount

            #When suppression expires, restore source's effects
            elif effect_type == "suppress_effect":
                for target in active_effect.targets:
                    if not self.has_active_effect("suppress_effect", target):
                        self.set_source_effects_suppressed(target, False)

            print(
                f"Effect expired: "
                f"{effect_type}"
            )

            
    def has_active_effect(self, effect_type, target=None):
        for active_effect in self.active_effects:

            if active_effect.suppressed:
                continue

            if active_effect.effect["type"] != effect_type:
                continue

            if target is None:
                return True

            if target in active_effect.targets:
                return True

        return False

    def get_active_effects(self, effect_type, target=None):
        matching_effects = []

        for active_effect in self.active_effects:

            if active_effect.suppressed:
                continue

            if active_effect.effect["type"] != effect_type:
                continue

            if (
                target is not None
                and active_effect.effect.get("target") != target
            ):
                continue

            matching_effects.append(active_effect)

        return matching_effects

    def resolve_threat_effect(self, effect, threat):
        print(
            f"     {threat.card.name} activates effect: "
            f"     {effect['type']}"
        )
        self.resolve_effect(effect, source=threat)        

    def resolve_player_effects(self, effect, card, threat_chooser=None, support_chooser=None):
        print(
            f"{card.name} activates effects: "
            f"{effect['type']}"
        )

        self.resolve_effect(effect, source=card, threat_chooser=threat_chooser, support_chooser=support_chooser)

    def resolve_ip_effect(self, effect, card):
        print(
            f"     {card.name} activates effect: "
            f"{effect['type']}"
        )

        self.resolve_effect(effect, source=card)

    def resolve_setback_effect(self, effect, card):
        print(
            f"     {card.name} activates effecg: "
            f"     {effect['type']}"
        )

        self.resolve_effect(effect, source=card)

    def apply_strength_modifier(self, effect, source_threat=None, threat_chooser=None, support_chooser=None):
        target = effect["target"]
        amount = effect["amount"]

        affected_targets = []

        attack_modes = {
            "attack_only",
            "dual_use",
            "attack_and_effect"
        }

        threat_category_targets = {
            "a_sam": "sam",
            "sam": "sam",
            "air": "air",
            "air_threat": "air",
            "ground": "ground",
            "ground_threat": "ground",
            "ew": "ew"
        }

        print(f"     Applying {amount:+} strength to {target}")

        

        # Support target
        if target == "support":

            count = effect.get("count")

            # for if there is a number of specific cards (i.e. 2 cards lose 2 points)
            if count is not None:
                selected_cards = self.choose_support_cards(count, chooser=support_chooser)

                for player, card in selected_cards:
                    card.strength_modifier += amount
                    affected_targets.append(card)

                    print(
                        f"{player.role}'s {card.name} "
                        f"recieved {amount:+} strength. "
                        f"Current strength: {card.current_strength()}"
                    )  

            # Applies effect to all suppot attack cards
            else:
                for player in self.players:
                    for card in player.hand:
                        if card.usage_mode in attack_modes:
                            card.strength_modifier += amount
                            affected_targets.append(card)
            return affected_targets

        # for modifying  any threats
        if target == "threat":
            count = effect.get("count")

            if count is not None:
                selected_threats = self.choose_threats_for_effect(count, chooser=threat_chooser)

                for threat in selected_threats:
                    threat.strength_modifier += amount
                    affected_targets.append(threat)

                    print(
                        f"{threat.card.name} recieves {amount:+} strength. "
                        f"Current Strength: {threat.current_strength()}"
                    )

            else:
                for threat in self.active_threats:
                    # Skips face down cards
                    if not threat.face_up:
                        continue
                    # Skips defeated Cards
                    if threat.defeated:
                        continue
                    # Skips effect only cards
                    if threat.current_strength() is None:
                        continue
                    # Card Skips itself
                    if source_threat is not None and threat is source_threat:
                        continue

                    threat.strength_modifier += amount
                    affected_targets.append(threat)
                    print(
                        f"{threat.card.name} recieves {amount:+} strength. "
                        f"Current Strength: {threat.current_strength()}"
                        f"\n"
                    )
            return affected_targets  

        # Modifies support cards from a specific player role
        if target in {"strike", "escort", "rescue", "c2"}:
            count = effect.get("count")

            if count is not None:
                selected_cards = self.choose_support_cards(count, role=target, chooser=support_chooser)

                for player, card in selected_cards:
                    card.strength_modifier += amount
                    affected_targets.append(card)
                    print(
                        f"{player.role}'s {card.name} "
                        f"recieved {amount:+} strength. "
                        f"Current Strength: {card.current_strength()}"
                    )

            else:
                for player in self.players:
                    if player.role.lower() == target:
                        for card in player.hand:
                            if card.usage_mode in attack_modes:
                                card.strength_modifier += amount
                                affected_targets.append(card)
            return affected_targets

        # Modifies specific threat category
        if target in threat_category_targets:
            category = threat_category_targets[target]
            count = effect.get("count", 1)

            selected_threats = self.choose_threats_for_effect(
                count,
                category=category,
                chooser=threat_chooser
            )

            for threat in selected_threats:
                threat.strength_modifier += amount
                affected_targets.append(threat)

                print(
                    f"{threat.card.name} "
                    f"received {amount:+} strength. "
                    f"Current Strength: {threat.current_strength()}"
                )
            return affected_targets

        # Modifies the Card just revealed
        if target == "revealed_threat":
            threat = self.last_revealed_threat

            if threat is None:
                print("No Revealed threat to modify")
                return affected_targets

            if threat.current_strength() is None:
                print("Revealed Threat is an Effect Card.")
                return affected_targets

            threat.strength_modifier += amount
            affected_targets.append(threat)

            print(
                f"{threat.card.name} recieves {amount:+} strength. "
                f"Current Strength: {threat.current_strength()}"
            )

            return affected_targets

    def apply_reveal_card(self, effect):
        target = effect["target"]
        count = effect.get("count", 1)

        self.last_revealed_threat = None

        if target == "hidden_threat":
            hidden_threats = [
                threat
                for threat in self.active_threats
                if not threat.face_up
            ]

            if len(hidden_threats) == 0:
                print("\nNo hidden threats available.")
                return

            # Prevents impossible selection counts
            count = min(count, len(hidden_threats))

            for i in range(count):
                threat = hidden_threats[i]
                threat.reveal()

                self.last_revealed_threat = threat

                print("\nThreat Revealed: ")
                self.display_threat(threat)

                self.trigger_threat_effects(threat, "on_reveal")

    # Method for applying draw card effect
    def apply_draw_card(self, effect):
        target = effect["target"]
        count = effect.get("count", 1)

        # Draws IP Card
        if target == "isolated_personnel":
            for i in range(count):
                card = self.ip_deck.draw_one_card()

                if card is None:
                    print("No IP cards remaining...")
                    return

                self.active_ip_card = card

                print(f"\nIP card drawn: {card.name}")

                if card.source_text.get("effect"):
                    print(
                        f"     EFFECT: "
                        f"{card.source_text.get('effect')}"
                    )
                self.trigger_ip_effects(card, "on_draw")

        # Draws additional Face-up/down threat to current phase
        elif target == "current_phase_threat_deck":
            threat_deck = self.phase_decks[self.current_phase]
            reveal = effect.get("reveal", False)

            for i in range(count):
                card = threat_deck.draw_one_card()

                if card is None:
                    print("No Threats left to draw...")
                    return

                threat = ThreatInstance(card)
                self.active_threats.append(threat)

                if reveal:
                    threat.reveal()

                    print("\nAdditional threat drawn face-up:")
                    self.display_threat(threat)

                    self.trigger_threat_effects(threat, "on_reveal")
                else:
                    print("\nAdditional face-down threat drawn.")

        # Draw additional Setback Card
        elif target == "setback_deck":
            for i in range(count):

                game_lost = self.draw_setback()

                if game_lost:
                    print("\nToo many active Setbacks.\nGAME OVER")
                    return

    # Method for forcing players to discard a card effect
    def apply_force_discard(self, effect):
        target = effect["target"]
        count = effect.get("count", 1)

        targets = target if isinstance(target, list) else [target]

        targets = [t.lower() for t in targets]

        for player in self.players:
            if player.role.lower() not in targets:
                continue
            if player.role.lower() in targets:
                for i in range(count):
                    if len(player.hand) == 0:
                        print(f"{player.role} has no cards to discard.")
                        break
                    if self.discard_chooser is not None:
                        choice = self.discard_chooser(player, player.hand)
                        if not(
                            1 <= choice <= len(player.hand)
                        ):
                            print("invalid choice")
                            continue
                        card = player.hand.pop(choice - 1)
                    
                    else:

                    #Player chooses what card to discard    
                        card = player.choose_card(f"{player.role} Choose a card to Discard:")
                        player.hand.remove(card)

                    print(
                        f"{player.role} discards "
                        f"{card.name}"
                    )

    def apply_suppress_effect(self, effect, source=None):
        target = effect["target"]
        count = effect.get("count", 1)
        

        if target == "threat":
            selected_targets = self.choose_threats_for_effect(count)

        elif target == "setback":
            selected_targets = self.choose_setback_for_effect(count)

        else:
            print(f"Suppress effect not implemented for {target}")
            return

        if not selected_targets:
            return    
        
        self.register_active_effect(effect, source=source, targets=selected_targets)

        for target in selected_targets:
            self.set_source_effects_suppressed(target, True)
            # Threat Instance
            if isinstance(target, ThreatInstance):
                name = target.card.name

            # normal Card Object, 
            else: 
                name = target.name

            print(
                f"{name}'s effect "
                f"has been suppressed."
            )

    # Function to apply the effect of removing a card
    def apply_remove_card(self, effect):
        target = effect["target"]
        count = effect.get("count",1)

        if target == "setback":
            selected_setbacks = self.choose_setback_for_effect(count)

            if not selected_setbacks:
                return
            
            for setback in selected_setbacks:
                removed = self.remove_from_play(setback, self.active_setbacks)
            if removed:
                print(
                    f"Setback removed: "
                    f"{setback.name}"
                )

    def apply_modify_phase_setup(self, effect, source=None):
        self.register_active_effect(effect, source=source)

    # Disables a whole category/deck of cards
    def apply_disable_cards(self, effect, source=None):
        self.register_active_effect(effect, source=source)

    # generic function to remove cards from play
    def remove_from_play(self, source, collection):
        if source not in collection:
            return False

        collection.remove(source)

        self.expire_active_effects("source_removed", source=source)

        return True

    # Chooses support cards to apply strength to
    def choose_support_cards(self, count, role=None, chooser=None):
        if chooser is None:
            chooser = self.support_chooser

        attack_modes = {
            "attack_only",
            "dual_use",
            "attack_and_effect"
        }            

        eligible_cards = []

        for player in self.players:
            if role is not None and player.role.lower() != role:
                continue
            for card in player.hand:
                if card.usage_mode in attack_modes:
                    eligible_cards.append((player, card))

        if not eligible_cards:
            print("\nNo eligible support cards!")
            return[]

        count = min(count, len(eligible_cards))

        selected_cards = []

        while len(selected_cards) < count:
            print(
                f"\nChoose support card "
                f"{len(selected_cards) + 1} of {count}: "
            )

            for i, (player, card) in enumerate(eligible_cards):
                print(
                    f"{i + 1}. {player.role} - {card.name}"
                    f"(Strength: {card.current_strength()})"
                )

            try:
                if chooser is not None:
                    choice = chooser(eligible_cards)
                else:
                    choice = int(input("Choose a card: "))

                if 1 <= choice <= len(eligible_cards):
                    selected = eligible_cards.pop(choice - 1)
                    selected_cards.append(selected)

                else:
                    print("Invalid Choice.")

            except ValueError:
                print("Please enter a valid number.")

        return selected_cards

    #Chooses threat cards to apply effects
    def choose_threats_for_effect(self, count, category=None, chooser=None):
        if chooser is None:
            chooser = self.threat_chooser

        eligible_threats = []

        #Obtaining current valid threat targets
        for threat in self.active_threats:
            if threat.defeated:
                continue

            if threat.current_strength() is None:
                continue

            if category is not None:
                if not threat.face_up:
                    continue

                if category not in threat.card.threat_categories:
                    continue

            eligible_threats.append(threat)

        # Checks to see if there are any eligible threats
        if len(eligible_threats) == 0:
            print("\nNo valid threats available for this effect.")
            return []

        if len(eligible_threats) < count:
            print(
                f"\nOnly {len(eligible_threats)} valid target(s)."
                f"Effect will only targe those."
            )
            count = len(eligible_threats)
        

        selected_threats = []

        while len(selected_threats) < count:
            print(
                f"\nChoose Threat "
                f"{len(selected_threats) + 1} of {count}: "
            )

            for i, threat in enumerate(eligible_threats):
                print(
                    f"{i + 1}. {threat.card.name} "
                    f"(Strength: {threat.current_strength()})"
                )

            try:
                if chooser is not None:
                    choice = chooser(eligible_threats)
                else:
                    choice = int(input("Choose a threat: "))

                if 1 <= choice <= len(eligible_threats):
                    selected = eligible_threats.pop(choice - 1)
                    selected_threats.append(selected)
                else:
                    print("Invalid Choice.")
            except ValueError:
                print("Please enter a valid number.")

        return selected_threats

    #Cooses setback to apply/remove
    def choose_setback_for_effect(self, count, chooser=None):
        if chooser is None:
            chooser = self.setback_chooser
            
        if len(self.active_setbacks) == 0:
            print("\nNo active setbacks!")
            return []

        
        available_setbacks = self.active_setbacks.copy()
        count = min(count, len(available_setbacks))
        selected_setbacks = []

        while len(selected_setbacks) < count:
            print(f"\nChoose Setback "
                  f"{len(selected_setbacks) + 1} of {count}:")
            if not available_setbacks:
                break
            for i, setback in enumerate(available_setbacks):
                print(f"{i+1}. {setback.name}")
            if chooser is not None:
                choice = chooser(available_setbacks)
            else:
                try:
                    choice = int(input("Choose a Setback: "))

                    if 1 <= choice <= len(available_setbacks):
                        selected = available_setbacks.pop(choice - 1)
                        selected_setbacks.append(selected)
                    else:
                        print("Invalid Choice...")

                except ValueError:
                    print("Please enter a valid number.")
                    continue
            if(
                1 <= choice
                <= len(available_setbacks)
            ):
                selected = (
                    available_setbacks.pop(choice - 1)
                )
                selected_setbacks.append(selected)
            else:
                print("invalid Choice")

        return selected_setbacks

    # reverses current effects coming on/off suppression
    def set_source_effects_suppressed(self, source, suppressed):
        for active_effect in self.active_effects:
            if active_effect.source is not source:
                continue

            if active_effect.suppressed == suppressed:
                continue

            # Stateful strength modifiers must be reversed/restored
            if active_effect.effect["type"] == "modify_strength":
                amount = active_effect.effect["amount"]

                for target in active_effect.targets:
                    if suppressed:
                        target.strength_modifier -= amount
                    else:
                        target.strength_modifier += amount
            active_effect.supperssed = suppressed

    def player_cards_disabled(self, player):
        disabled_effects = self.get_active_effects("disble_cards", player.role.lower())
        return len(disabled_effects) > 0

    #sets up the current phase by shuffling the threat deck, drawing the appropriate number of threats, and revealing them based on the current phase
    def setup_phase(self):
        print(f"\n--- Phase {self.current_phase} ---\n")

        threat_deck = self.phase_decks[self.current_phase]
        threat_deck.shuffle()
        
        #gets number of threats for the current phase and draws them from the threat deck
        number_of_threats = self.threats_per_phase[self.current_phase]
        drawn_threats = threat_deck.draw_card(number_of_threats)

        self.active_threats = []

        # Creates ThreatInstance objects for each drawn threat card and adds them to the active threats list
        for card in drawn_threats:
            threat = ThreatInstance(card)
            self.active_threats.append(threat)


        # Calculate number of face-up threats based on the current phase and effects
        face_down_count = self.current_phase // 2 + 1

        setup_effects = self.get_active_effects("modify_phase_setup", "hidden_threat_count")

        for active_effect in setup_effects:
            face_down_count += active_effect.effect.get("amount", 0)

        face_down_count = min(face_down_count, number_of_threats)
        face_up_count = number_of_threats - face_down_count


        # Reveal the appropriate number of threats based on the current phase
        for i in range(face_up_count):
            threat = self.active_threats[i]
            threat.reveal()
            self.trigger_threat_effects(
                threat,
                "on_reveal"
            )

        ip_deck = self.ip_deck
        ip_deck.shuffle()

        if self.current_phase > 1:
           self.active_ip_card = self.ip_deck.draw_one_card()

        if self.active_ip_card:
            print(f"Active Isolated Personnel: {self.active_ip_card.name}")

            if self.active_ip_card.source_text.get("effect"):
                print(
                    f"     Effect: "
                    f"{self.active_ip_card.source_text.get('effect')}"
                )

            self.trigger_ip_effects(self.active_ip_card, "on_draw")

        for threat in self.active_threats:
            self.display_threat(threat)

    def reveal_threat_after_turn(self):
        for threat in self.active_threats:
            if threat.face_up == False:
                threat.reveal()
                #print(f"DEBUG reveal: {threat.card.name}, face_up = {threat.face_up}")

                print(
                    f"\nThreat revealed after full turn: "
                    f"{threat.card.name} "
                    f"Strength: {threat.current_strength()}" 
                )

                self.trigger_threat_effects(
                    threat,
                    "on_reveal"
                )
                return

    def strength_threats_remaining(self):
        return[
            threat
            for threat in self.active_threats
            if threat.card.strength is not None
            and not threat.defeated
        ]

    # phase complete checker, if all threats defeated complete, if no cards left to play then phase failed
    def check_phase_status(self):
        remaining_threats = self.strength_threats_remaining()
        if len(remaining_threats) == 0:
            return "complete"

        players_have_cards = any(
            len(player.hand) > 0
            for player in self.players
        )

        if not players_have_cards:
            return "failed"

        return "ongoing"
    
    # Reset player turns and order; advances phase number
    def advance_phase(self):

        self.expire_active_effects("phase_end")
        
        if self.current_phase >=4:
            return False
        
        self.current_phase += 1

        # Reset Player Hands
        for player in self.players:
            player.reset_hand()

            # Resets strength Modifiers for cards
            for card in player.available_cards:
                card.strength_modifier = 0

        # reset Turn
        self.current_player_index = 0
        self.turn_number = 1

        self.setup_phase()

        return True
    
    #Runs if players fail phase, resets threats, hands, and turns
    def retry_phase(self):
        self.expire_active_effects("phase_end")

        threat_deck = self.phase_decks[self.current_phase]

        # Return threats to deck
        for threat in self.active_threats:
            threat_deck.cards.append(threat.card)

        # Reset player State
        for player in self.players:
            player.reset_hand()

            for card in player.available_cards:
                card.strength_modifier = 0

        # Reset Turn
        self.current_player_index = 0
        self.turn_number = 1

        # Reset IP card
        if self.active_ip_card is not None:
            self.ip_deck.cards.append(self.active_ip_card)
            self.active_ip_card = None

        self.setup_phase()

    def draw_setback(self):
        setback = self.setback_deck.draw_one_card()

        if setback is None:
            print("No setback cards remaining.")
            return False

        self.active_setbacks.append(setback)

        print(f"\nSETBACK DRAWN: {setback.name}")
        print(
            f"Active Setbacks: "
            f"{len(self.active_setbacks)}/5"
        )

        self.trigger_setback_effects(setback, "while_active")

        return len(self.active_setbacks) > 5

    def display_threat(self, threat, number=None):
            # Optional number for selection menus
            prefix = f"{number}. " if number is not None else "Threat: "
    
            #Prints defeated threats
            if threat.defeated:
                print(f"{prefix}DEFEATED THREAT - {threat.card.name}")
            #Prints information of card
            elif threat.face_up:
                print(f"{prefix}{threat.card.name}")
                if threat.card.strength is not None:
                    print(f"     Strength: {threat.current_strength()}")
                if threat.card.effects:
                    print(f"     Effect: {threat.card.source_text.get('effect','')}")
    
            #Prints mystery face down card
            else:
                print(f"{prefix}Face-down threat card")
            print("\n")#seperator line

    def add_reward(self, reason):
        amount = 0.0
        match reason:
            case "step":
                amount = -0.05
            case "threat_defeated":
                amount = 0.5    
            case "phase_complete":
                amount = 10
            case "game_win":
                amount = 100
            case "game_loss":
                amount = -100
        
        self.total_reward += amount
        self.pending_reward += amount

        self.reward_log.append((reason, amount))

    def consume_reward(self):
        reward = self.pending_reward
        self.pending_reward = 0.0

        return reward
       
class ThreatInstance:
    def __init__(self, card, face_up=False):
        self.card = card
        self.face_up = face_up
        self.engaged = False
        self.defeated = False
        self.strength_modifier = 0
        self.damage_taken = 0
        #self.effect_suppressed = False

    def reveal(self):
        self.face_up = True

    def current_strength(self):
        if self.card.strength is None:
            return None

        return max(0, self.card.strength + self.strength_modifier - self.damage_taken)

class ActiveEffect:
    def __init__(
        self,
        effect,
        source,
        targets,
        start_phase,
        start_turn
    ):
        self.effect = effect
        self.source = source
        self.targets = targets

        self.duration = effect.get("duration", "instant")

        self.start_phase = start_phase
        self.start_turn = start_turn

        self.suppressed = False



