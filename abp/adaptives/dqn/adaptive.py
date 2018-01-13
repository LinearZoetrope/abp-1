from memory import Memory
from model import DQNModel
from experience import Experience

import tensorflow as tf
import numpy as np
import os
import logging


from abp.utils import clear_summary_path



class DQNAdaptive(object):
    """Adaptive which uses the  DQN algorithm"""

    def __init__(self, name, choices, network_config, reinforce_config):
        super(DQNAdaptive, self).__init__()
        self.name = name
        self.choices = choices
        self.network_config = network_config
        self.reinforce_config = reinforce_config

        self.replay_memory = Memory(self.reinforce_config.memory_size)
        self.learning = True

        self.steps = 0
        self.previous_state = None
        self.previous_action = None
        self.current_reward = 0
        self.total_reward = 0

        # self.target_model = DQNModel(size_features, self.network_config.input_shape, "target_model", trainable = False)
        self.eval_model = DQNModel(self.name, self.network_config)

        #TODO:
        # * Add more information/summaries related to reinforcement learning
        # * Option to diable summary?
        clear_summary_path(self.reinforce_config.summaries_path + "/" + self.name)

        self.summaries_writer = tf.summary.FileWriter(self.reinforce_config.summaries_path + "/" + self.name)

        self.episode = 0

    def __del__(self):
        self.summaries_writer.close()

    def should_explore(self):
        epsilon = np.max([0.1, self.reinforce_config.starting_epsilon * (self.reinforce_config.decay_rate ** (self.steps / self.reinforce_config.decay_steps))])

        epsilon_summary = tf.Summary()
        epsilon_summary.value.add(tag='epsilon', simple_value = epsilon)
        self.summaries_writer.add_summary(epsilon_summary, self.steps)

        return np.random.choice([True, False],  p = [epsilon, 1 - epsilon])

    def predict(self, state):
        self.steps += 1

        # add to experience
        if self.previous_state is not None:
            experience = Experience(self.previous_state, self.previous_action, self.current_reward, state)
            self.replay_memory.add(experience)

        if self.learning and self.should_explore():
            action = np.random.choice(len(self.choices))
            q_values = [None] * len(self.choices) #TODO should it be output shape or from choices?
            choice = self.choices[action]
        else:
            action, q_values = self.eval_model.predict(state)
            choice = self.choices[action]


        if self.learning and self.replay_memory.current_size > 30:
            self.update()

        self.current_reward = 0

        self.previous_state = state
        self.previous_action = action

        return choice, q_values

    def disable_learning(self):
        logging.info("Disabled Learning for %s agent" % self.name)
        self.learning = False
        self.episode = 0

    def end_episode(self, state):
        if not self.learning:
            return

        self.episode += 1

        psuedo_reward_summary = tf.Summary()
        psuedo_reward_summary.value.add(tag='%s agent reward' % self.name, simple_value = self.total_reward)
        self.summaries_writer.add_summary(psuedo_reward_summary, self.episode)


        experience = Experience(self.previous_state, self.previous_action, self.current_reward, state, True)
        self.replay_memory.add(experience)

        self.current_reward = 0
        self.total_reward = 0

        self.previous_state = None
        self.previous_action = None

        if self.replay_memory.current_size > 30:
            self.update()


    def reward(self, r):
        self.total_reward += r
        self.current_reward += r

    def update(self):
        batch_size = 32
        batch = self.replay_memory.sample(batch_size)

        batch_size = len(batch)

        # TODO: Convert to tensor operations instead of for loops

        states = [experience.state for experience in batch]

        next_states = [experience.next_state for experience in batch]

        is_terminal = [ 0 if experience.is_terminal else 1 for experience in batch]

        actions = [experience.action for experience in batch]

        reward = [experience.reward for experience in batch]

        q_next = self.eval_model.predict_batch(next_states)

        q_max = np.max(q_next, axis = 1)

        q_max = np.array([ a * b if a == 0 else b for a,b in zip(is_terminal, q_max)])

        q_values = self.eval_model.predict_batch(states)

        q_target = q_values.copy()

        batch_index = np.arange(batch_size, dtype=np.int32)

        q_target[batch_index, actions] = reward + self.reinforce_config.discount_factor * q_max

        self.eval_model.fit(states, q_target, self.steps)
