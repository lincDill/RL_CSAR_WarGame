import random
from collections import deque

import torch
import torch.nn as nn
import torch.optim as optim

class DQN(nn.Module):
    def __init__(
        self,
        state_size,
        action_size,
    ):
        super().__init__()

        self.network = nn.Sequential(
            nn.Linear(state_size, 128),
            nn.ReLU(),

            nn.Linear(128, 128),
            nn.ReLU(),

            nn.Linear(128, action_size)
        )

    def forward(self, x):
        return self.network(x)

class DQNAgent:
    def __init__(
            self, 
            state_size,
            action_size,
            learning_rate=0.0001,
            gamma=0.99,
            epsilon=1.0,
            epsilon_min=0.05,
            epsilon_decay=0.9995
    ):
        self.state_size = state_size
        self.action_size = action_size

        self.gamma = gamma

        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay

        self.model = DQN(state_size, action_size)

        self.target_model = DQN(state_size, action_size)
        self.target_model.load_state_dict(self.model.state_dict())

        self.target_model.eval()

        self.optimizer = optim.Adam(
            self.model.parameters(),
            lr=learning_rate
        )

        self.loss_function = nn.SmoothL1Loss()

        self.memory = deque(maxlen=50000)

        self.training_steps = 0
        self.target_update_frequency = 100

    def choose_action(self, state, legal_actions):
        # Explore: choose a random legal action
        if random.random() < self.epsilon:
            return random.choice(legal_actions)

        # Exploit: use the NN
        state_tensor = torch.tensor(state, dtype=torch.float32).unsqueeze(0)

        with torch.no_grad():
            q_values = self.model(state_tensor)[0]

        # Mask illegal actions
        masked_q_values = torch.full_like(q_values, float("-inf"))

        for action in legal_actions:
            masked_q_values[action] = q_values[action]

        return torch.argmax(masked_q_values).item()

    def remember(
            self,
            state,
            action, 
            reward,
            next_state,
            next_action__mask,
            done
    ):
        self.memory.append(
            (
                state,
                action,
                reward,
                next_state,
                next_action__mask,
                done
            )
        )

    def train_step(self, batch_size=64):
        # Don't train until there are enough experiences
        if len(self.memory) < batch_size:
            return None

        # Randomly select experiences from memory
        batch = random.sample(self.memory, batch_size)

        states = torch.tensor(
            [experience[0] for experience in batch],
            dtype=torch.float32
        )

        actions = torch.tensor(
            [experience[1] for experience in batch],
            dtype=torch.long
        )

        rewards = torch.tensor(
            [experience[2] for experience in batch],
            dtype=torch.float32
        )

        next_states = torch.tensor(
            [experience[3] for experience in batch],
            dtype=torch.float32
        )

        next_action_masks = torch.tensor(
            [experience[4] for experience in batch],
            dtype=torch.bool
        )

        dones = torch.tensor(
            [experience[5] for experience in batch],
            dtype=torch.float32
        )

        # Q-values for current states
        q_values = self.model(states)
        # DEBUGGING: Print Q ranges
        #print("Q range:", q_values.min().item(), "to", q_values.max().item())

        # Only keep the Q-value for the action that was taken
        current_q_values = q_values.gather(1,actions.unsqueeze(1)).squeeze(1)

        # Calculate estimated future value
        with torch.no_grad():
            next_all_q_values = (
                self.target_model(next_states)
            )

            masked_next_q_values = (
                next_all_q_values.masked_fill(
                    ~next_action_masks, -1e9
                )
            )

            next_q_values = (masked_next_q_values.max(dim=1).values)

            # Some non-terminal states may have no legal actions
            has_legal_action = next_action_masks.any(dim=1)

            next_q_values = torch.where(
                has_legal_action,
                next_q_values,
                torch.zeros_like(next_q_values)
            )

            target_q_values = (
                rewards + self.gamma * next_q_values * (1 - dones)
            )

        # Compare prediction to target
        loss = self.loss_function(current_q_values, target_q_values)

        # Update NN weigths
        self.optimizer.zero_grad()

        loss.backward()

        self.optimizer.step()

        self.training_steps += 1
        if(
            self.training_steps
            % self.target_update_frequency == 0
        ):
            self.target_model.load_state_dict(self.model.state_dict())

        return loss.item()

    def decay_epsilon(self):
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay
            self.epsilon = max(self.epsilon, self.epsilon_min)
            
if __name__ == "__main__":
    agent = DQNAgent(
        state_size=147,
        action_size=10
    )

    # ==== TEST Memory ==== #
    fake_state = [0.0] * 147
    fake_next_state = [0.0] * 147

    for i in range(100):
        agent.remember(fake_state, random.randrange(10), random.uniform(-1,1), fake_next_state, False)

    print("Memory size: ", len(agent.memory))

    loss = agent.train_step()
    
    print("Training Loss:", loss)