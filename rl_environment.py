from init import create_game
from random_agent import RandomAgent
from collections import Counter
from dqn_agent import DQNAgent
import torch

import random

import sys
import os
import contextlib

MAX_THREATS = 10
MAX_ROLE_CARDS = 10
ATTACK_ACTION = 0
EFFECT_ACTION = 1

def build_state_reference(game):
    return{
        "ip_names": sorted(
            card.name
            for card in game.ip_deck.cards
        ),

        "setback_names": sorted(
            card.name
            for card in game.setback_deck.cards
        )
    }

# normalizes the game state for the NN
def encode_game_state(game, player, state_refernce):
    state = []

    # ==== General Game State ==== #
    # Phase: 0.25, 0.5, 0.75, 1.0
    state.append(game.current_phase / 4)

    # Keep very large turn numbers bounded
    state.append(min(game.turn_number, 20) / 20)

    # Current player's role
    roles = ["strike", "c2", "escort", "rescue"]

    for role in roles:
        state.append(1.0 if player.role.lower() == role else 0.0)

    # Number of setbacks
    state.append(len(game.active_setbacks) / 6)

    # Current player's hand size
    state.append(len(player.hand) / MAX_ROLE_CARDS)

    # Whether this player's cards are disabled
    state.append(1.0 if game.player_cards_disabled(player) else 0.0)

    # ==== PLAYER HAND ==== #  
    role_cards = sorted(player.available_cards, key=lambda card: card.name)

    for i in range(MAX_ROLE_CARDS):
        if i < len(role_cards):
            card = role_cards[i]

            in_hand = (1.0 if card in player.hand else 0.0)

            strength = 0.0

            if card in player.hand:
                current_strength = card.current_strength()

                if current_strength is not None:
                    strength = (current_strength / 10)

            state.extend([in_hand, strength])
        else:
            # Rescue deck only has 7 cards so pad remaining
            state.extend([0.0, 0.0])

    # ==== ACTIVE THERATS ==== #
    for i in range(MAX_THREATS):
        if i >= len(game.active_threats):

            # Empty threat slots
            state.extend([
                0.0, #exists
                0.0, # face up
                0.0, # defeated
                0.0, # effect only
                0.0, # strength
                0.0, # SAM
                0.0, # air
                0.0, # ground
                0.0, # EW
                0.0  # Engaged
            ])
            continue
        threat = game.active_threats[i]

        exists = 1.0

        face_up = (1.0 if threat.face_up else 0.0)
        defeated = (1.0 if threat.defeated else 0.0)
        effect_only = 0.0
        strength = 0.0
        sam = 0.0
        air = 0.0
        ground = 0.0
        ew = 0.0

        if threat.face_up:
            current_strength = threat.current_strength()
            if current_strength is None:
                effect_only = 1.0
            else:
                strength = (current_strength / 10)

            categories = threat.card.threat_categories

            sam = (1.0 if "sam" in categories else 0.0)
            air = (1.0 if "air" in categories else 0.0)
            ground = (1.0 if "ground" in categories else 0.0)
            ew = (1.0 if "ew" in categories else 0.0)
        engaged = (1.0 if threat.engaged else 0.0)

        state.extend([
            exists,
            face_up,
            defeated,
            effect_only,
            strength,
            sam,
            air,
            ground,
            ew,
            engaged
        ])

    # ==== ACTIVE IP CARD ==== #
    for name in state_refernce["ip_names"]:
        state.append(1.0 if(
            game.active_ip_card is not None
            and game.active_ip_card.name == name
        ) else 0.0)

    # ==== ACTIVE SETBACKS ==== #
    active_setback_names = [setback.name for setback in game.active_setbacks]

    for name in state_refernce["setback_names"]:
        state.append(1.0 if name in active_setback_names else 0.0)

    return state

# normalize usage state
def encode_usage_state(game, player, state_reference, card_action):
    state = encode_game_state(game, player, state_reference)

    #10-value one-hot encoding ID'ing the card that was selected
    card_identity = [0.0] * MAX_ROLE_CARDS
    card_identity[card_action] = 1.0

    return state + card_identity

# ADD CARD ACTION SPACE #
def get_card_action_space(player):
    role_cards = sorted(
        player.available_cards, key=lambda card: card.name
    )

    action_slots = [None] * MAX_ROLE_CARDS
    action_mask = [0] * MAX_ROLE_CARDS

    for i, card in enumerate(role_cards):
        if card in player.hand:
            action_slots[i] = card
            action_mask[i] = 1

    return action_slots, action_mask


def get_loadout_state(player):
    return{
        "role": player.role,
        "selected_cards": [
            card.name
            for card in player.starting_hand
        ],
        "cards_remaining_to_select": 5 - len(player.starting_hand)
    }

def get_turn_state(game, player):
    return{
        "phase": game.current_phase,
        "turn": game.turn_number,
        "role": player.role,
        "hand_size": len(player.hand),
        "active_threats": len(game.active_threats)
    }

def get_attack_targets(game):
    legal_targets = []

    for threat in game.active_threats:
        # Disregards defeated threats
        if threat.defeated:
            continue

        #Disregards effect only face-up threats
        if(
            threat.face_up
            and threat.current_strength() is None
        ):
            continue

        legal_targets.append(threat)
    return legal_targets

def get_attack_action_space(game):
    action_slots = [None] * MAX_THREATS
    action_mask = [0] * MAX_THREATS

    for i, threat in enumerate(game.active_threats[:MAX_THREATS]):
        action_slots[i] = threat

        # Defeated threats are illegal actions
        if threat.defeated:
            continue
        # Known effect-only threats are illegal
        if (
            threat.face_up
            and threat.current_strength() is None
        ):
            continue

        # Face-down threats ARE legal
        action_mask[i] = 1

    return action_slots, action_mask

def choose_attack_target(game):
    action_slots, action_mask = get_attack_action_space(game)

    legal_actions = [
        i
        for i, legal in enumerate(action_mask)
        if legal
    ]

    if not legal_actions:
        return None, None

    action = random.choice(legal_actions)
    threat = action_slots[action]

    return threat, action


def choose_card_usage(game, player, state_reference, usage_agent, card, card_action):

    if card.usage_mode == "attack_only":
        return "attack", None, None

    if card.usage_mode == "effect_only":
        return "effect", None, None

    if card.usage_mode == "attack_and_effect":
        return "attack_and_effect", None, None

    if card.usage_mode == "dual_use":
        usage_state = encode_usage_state(game, player, state_reference, card_action)

        legal_actions = [ATTACK_ACTION, EFFECT_ACTION]

        usage_action = usage_agent.choose_action(usage_state, legal_actions)

        if usage_action == ATTACK_ACTION:
            return "attack", usage_state, usage_action

        if usage_action == EFFECT_ACTION:
            return "effect", usage_state, usage_action

    return None, None, None    


# Current Random
def agent_threat_chooser(game, agent, eligible_threats):
    return random.randrange(len(eligible_threats)) + 1

# Current Random

def agent_support_chooser(game, agent, eligible_cards):
        return random.randrange(len(eligible_cards)) + 1

# Current Random

def agent_setback_chooser(game, agent, eligible_setbacks):
    return random.randrange(len(eligible_setbacks)) + 1

# Current Random

def agent_discard_chooser(game, agent, player, eligible_cards):
    return random.randrange(len(eligible_cards)) + 1

def agent_attack(game, agent, state, card):
    while True:
        threat, target_action = choose_attack_target(game)
        if threat is None:
            print("No valid Attack Targets.")
            return
        if threat.face_up:
            print(f"Agent targets: {threat.card.name}")
        else:
            print("agent targets a face-down threat.")
        attack_completed = game.engage_threat(card,threat)
        if attack_completed:
            return

        # If a face-down ard is revealed as EW, rebuild and agent chooses again
        #state = get_turn_state(game, game.get_current_player())

def choose_effect_threats(game, agent, state, count, category=None):
    legal_targets = []

    for threat in game.active_threats:
        if threat.defeated:
            continue

        if category is not None:
            if category not in threat.card.threat_categories:
                continue

        legal_targets.append(threat)

    selected = []

    count = min(count, len(legal_targets))

    for _ in range(count):
        action = random.randrange(len(legal_targets))
        threat = legal_targets.pop(action)

        selected.append(threat)
    return selected

def run_game(card_agent, usage_agent):

    def record_usage_experience():
        if usage_state is None:
            return

        usage_reward = game.total_reward - usage_reward_start

        usage_experiences.append((
            usage_state,
            usage_action,
            usage_reward,
            [0.0] * len(usage_state),
            [0,0],
            True
        ))


    experiences = []
    usage_experiences = []

    game = create_game()

    state_reference = build_state_reference(game)

    game.threat_chooser = (
        lambda eligible_threats:
            agent_threat_chooser(game, card_agent, eligible_threats)
    )

    game.support_chooser = (
        lambda eligible_cards:
            agent_support_chooser(game, card_agent, eligible_cards)
    )

    game.setback_chooser = (
        lambda eligible_setbacks:
            agent_setback_chooser(game, card_agent, eligible_setbacks)
    )

    game.discard_chooser = (
        lambda player, eligible_cards:
            agent_discard_chooser(game, card_agent, player, eligible_cards)
    )


    for player in game.players:
        print(f"\nSelecting loadout for {player.role}")

        # Chooses initial loadouts
        for i in range(5):
            available_choices = [
                card
                for card in player.available_cards
                if card not in player.starting_hand
            ]

            card = random.choice(available_choices)

            player.select_card(card)

            #print(f"{i + 1}. {card.name}")

    for player in game.players:
        print(f"\n{player.role} Starting Hand:")
        for card in player.starting_hand:
            print(f"- {card.name}")

    game.setup_phase()

    player = game.get_current_player()

    state = encode_game_state(game, player, state_reference)

    # DEBUG: testing state encoder
    #print(f"State length: {len(state)}", file=sys.__stdout__)
    #print(state, file=sys.__stdout__)

    # infinite loop checker
    steps = 0
    max_steps = 5000

    # Max targets seen checker
    max_seen_threats = 0

    while True:

        max_seen_threats = max(max_seen_threats, len(game.active_threats))

        steps += 1

        if steps > max_steps:
            print("\npossible infinite loop")
            # TEMP: Reward counter
            reward_counts = Counter(reason for reason, amount in game.reward_log)
            return "stuck", steps, game.total_reward, experiences, usage_experiences, max_seen_threats
        
        player = game.get_current_player()

        print(
            f"\n=========================="
            f"\nTurn {game.turn_number} - "
            f"{player.role} Player"
            f"\n=========================="
        )

        # if this player has no cards move to next player
        if len(player.hand) == 0:
            print(f"{player.role} has no cards remaining.")
            phase_status = game.check_phase_status()

            if phase_status == "failed":
                game_lost = False
                game_lost = game.draw_setback()
                if game_lost:
                    game.add_reward("game_loss")
                    return "loss", steps, game.total_reward, experiences, usage_experiences, max_seen_threats
                game.retry_phase()
                continue

            game.next_player()
            continue

        # === BUILD STATE === #
        state = get_turn_state(game, player)

        # === Choose a Card === #
        available_actions = player.hand.copy()

        # Reward function penalizes long series of moves: -0.01/step
        game.consume_reward()
        game.add_reward("step")

        state = encode_game_state(game, player, state_reference)

        action_slots, action_mask = get_card_action_space(player)
        legal_actions = [
            i
            for i, legal in enumerate(action_mask)
            if legal
        ]

        
        action = card_agent.choose_action(state, legal_actions)
        card = action_slots[action]

        print(
            f"\nAgent selected for {player.role}: "
            f"{card.name}"
        )

        player.play_card(card)

        # Usage NN
        usage, usage_state, usage_action = choose_card_usage(game, player, state_reference, usage_agent, card, action)
        
        usage_reward_start = game.total_reward

        print(f"Agent will use {card.name} as: {usage}")


        # === RESOLVE ATTACK === #
        if usage == "attack":
            agent_attack(game, card_agent, state, card)

        elif usage == "effect":
            game.trigger_player_effects(
                card,
                threat_chooser=lambda eligible_threats:
                    agent_threat_chooser(
                        game,
                        card_agent,
                        eligible_threats
                    ),
                support_chooser=lambda eligible_cards:
                    agent_support_chooser(
                        game,
                        card_agent,
                        eligible_cards
                    )
            )

        elif usage == "attack_and_effect":
            agent_attack(game, card_agent, state, card)

            game.trigger_player_effects(
                card,
                threat_chooser=lambda eligible_threats:
                    agent_threat_chooser(
                        game,
                        card_agent,
                        eligible_threats
                    ),
                support_chooser=lambda eligible_cards:
                    agent_support_chooser(
                        game,
                        card_agent,
                        eligible_cards
                    )
            )

        # === CHECK PHASE === #
        record_usage_experience()
        phase_status = game.check_phase_status()
        if phase_status == "complete":
            print(f"\nPhase {game.current_phase} complete!")

            # Rewards completed phase
            game.add_reward("phase_complete")

            if not game.advance_phase():
                print("\nAll PHASES COMPLETE\nGAME WON!")

                # Rewards a won game
                game.add_reward("game_win")

                # TEMP: Reward counter
                #reward_counts = Counter(reason for reason, amount in game.reward_log)
                
                reward = game.consume_reward()
                experiences.append(
                    (
                        state,
                        action,
                        reward,
                        [0.0] * len(state),
                        [0] * MAX_ROLE_CARDS,
                        True
                    )
                )
                return "win", steps, game.total_reward, experiences, usage_experiences, max_seen_threats

            #phase won game not
            reward = game.consume_reward()
            next_player = game.get_current_player()

            next_state = encode_game_state(game, next_player, state_reference)
            _, next_action_mask = (get_card_action_space(next_player))
            experiences.append(
                (
                    state,
                    action,
                    reward,
                    next_state,
                    next_action_mask,
                    False
                )
            )

            continue

        elif phase_status == "failed":
            print(f"\nPhase {game.current_phase} failed!")

            game_lost = game.draw_setback()

            if game_lost:
                print("\nToo many setbacks!\nGAME LOST!")

                # Penalizes lost game
                game.add_reward("game_loss")

                # TEMP: Reward counter
                reward_counts = Counter(reason for reason, amount in game.reward_log)

                reward = game.consume_reward()
                experiences.append(
                    (
                        state,
                        action,
                        reward,
                        [0.0] * len(state),
                        [0] * MAX_ROLE_CARDS,
                        True
                    )
                )

                return "loss", steps, game.total_reward, experiences, usage_experiences, max_seen_threats
            
            # Phase failed but game continues

            game.retry_phase()
            reward = game.consume_reward()

            next_player = game.get_current_player()

            next_state = encode_game_state(game, next_player, state_reference)

            _, next_action_mask = (get_card_action_space(next_player))

            experiences.append((state, action, reward, next_state, next_action_mask, False))

            continue

        # === NEXT PLAYER === #
        record_usage_experience()
        game.next_player()

        reward = game.consume_reward()
        next_player = game.get_current_player()
        next_state = encode_game_state(game, next_player, state_reference)

        _, next_action_mask = (
            get_card_action_space(next_player)
        )

        experiences.append(
            (
                state,
                action,
                reward,
                next_state,
                next_action_mask,
                False
            )
        )

def training_loop(card_agent, usage_agent):
    games = 1

    wins = 0
    stuck = 0
    step_counts = []
    training_steps = 20
    overall_max_threats = 0
    old_epsilon = 0.0

    print("Starting Training")
    for i in range(games):

        # Uncomment this to see full game
        #result, steps, reward, experiences, max_seen_threats = run_game(card_agent, usage_agent)

        # Uncomment for hidden game
        with open(os.devnull, "w") as f:
            with contextlib.redirect_stdout(f):
                result, steps, reward, experiences, usage_experiences, max_seen_threats = run_game(card_agent, usage_agent)
                
        for experience in experiences:
            state = experience[0]
            action = experience[1]
            reward = experience[2]
            next_state = experience[3]
            next_action_mask = experience[4]
            done = experience[5]

            card_agent.remember(state, action, reward, next_state, next_action_mask, done)

        loss = None

        for _ in range(training_steps):
            new_loss = card_agent.train_step()
            if new_loss is not None:
                loss = new_loss
                
        card_agent.decay_epsilon()

        step_counts.append(steps)
        
        if result == "win":
            wins += 1

        if result == "stuck":
            stuck += 1

        if (i + 1) % 500 == 0:
            print(f"Game {i + 1} of {games}... continuing simulations...")
            print(f"    stuck: {stuck}")
        # Check min and max rewards
        #rewards = [
        #    experience[2]
        #    for experience in experiences
        #]
        #print(
        #    f"Game {i + 1} | Min Reward: {min(rewards):.2f} | Max Reward: {max(rewards):.2f}"
        #)
        # Checks every 100 games
        if (i + 1) % 100 == 0:
            print(f"Game {i + 1} | Memory: {len(card_agent.memory)} | Loss: {loss}\nEpsilon: {card_agent.epsilon:.4f}")
        old_epsilon = card_agent.epsilon
        #print(f"\nGame {i + 1} total reward: {reward:.2f}")
        #print(f"experinces collected: {len(experiences)}")
        #print("\nFirst Experience:")
        #print(experiences[0])

    print("\n===== TRAINING RESULTS =====")
    print(f"Games: {games}")
    print(f"Wins: {wins}")
    print(f"Losses: {games - wins}")
    print(f"Win rate: {wins / games:.2%}")
    print(f"Average steps: {sum(step_counts) / len(step_counts)}")
    print(f"Longest Game: {max(step_counts)}")
    print(f"Epsilon: {old_epsilon}")

    

    # SAVE The trained model
    #torch.save(card_agent.model.state_dict(), "dqn_card_agent.pt")
    #print("\nmodel Saved\n")


# NN for choosing what card to play
card_agent = DQNAgent(state_size=147, action_size=10)

# NN for choosing what to use card as for "dual-use" cards
usage_agent = DQNAgent(state_size=147, action_size=2)

#training_loop(card_agent, usage_agent)

#checkpoint = torch.load("dqn_card_agent.pt", map_location="cpu")

#card_agent.model.load_state_dict(checkpoint)

#print("Saved model Loaded.")

evaluation_games = 10
evaluation_wins = 0

# Turn exploration mode off
card_agent.model.eval()
card_agent.epsilon = 0.0

print("\nStarting Evaluation\n")

for i in range(evaluation_games):
    with open(os.devnull, "w") as f:
        with contextlib.redirect_stdout(f):
            (
                result,
                steps,
                reward,
                experiences,
                usage_experiences,
                max_seen_threats
            ) = run_game(card_agent, usage_agent)

    if result == "win":
        evaluation_wins += 1

    if (i + 1) % 100 == 0:
        print(f"Game {i + 1} of {evaluation_games} complete...")

print("\n====== DQN EVALUATION ======")
print(f"Games: {evaluation_games}")
print(f"Wins: {evaluation_wins}")
print(f"Win rate: {evaluation_wins/ evaluation_games:.2%}")

print("usage experiences: ", len(usage_experiences))
print("First usage experience:", usage_experiences[0])

#card_agent.epsilon = old_epsilon


    