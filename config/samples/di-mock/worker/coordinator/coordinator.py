import os
import argparse
import json
import time

import traceback
import requests
from typing import Dict, Callable, List
from threading import Thread
from easydict import EasyDict
from queue import Queue
import random

from interaction.master import Master
from interaction.master.task import TaskStatus
from .coordinator_interaction import CoordinatorInteraction
from .base_parallel_commander import create_parallel_commander

from data import ReplayBuffer
from utils import LockContext, LockContextType, get_task_uid


cfg = {
    'interaction': {
        'api_version': '/v1alpha1',
        'collector_limits': 1,
        'learner_limits': 1,
        'collector': {
            '0': ['collector0', 'localhost', 13339],
            # '1': ['collector1', 'localhost', '8001'],
        },
        'learner': {
            '0': ['learner0', 'localhost', 12333]
            # '0': ['learner0', 'localhost', 12334]
        },
    },
    'commander': {
        'parallel_commander_type': 'solo',
        'import_names': ['worker.coordinator.solo_parallel_commander'],
        'collector_task_space': 0,
        'learner_task_space': 0,
        'collector_cfg': {
            'env_kwargs': {
                'eval_stop_ptg': 0.6,
            }
        },
        'learner_cfg': {
            'dataloader': {
                'batch_size': 128,
            }
        },
        'replay_buffer_cfg': {},
        'policy': {},
        'max_iterations': 10000,
        'eval_interval': 5,
    },
    'collector_task_timeout': 5,
    'learner_task_timeout': 5,
}

cfg = EasyDict(cfg)


class TaskState(object):

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self.start_time = time.time()


class MockCoordinator(object):

    def __init__(self, host, port, di_server) -> None:
        self.__host = host
        self.__port = port

        cfg.interaction.host = host
        cfg.interaction.port = port

        self.__nerver_server = di_server

        self._coordinator_uid = get_task_uid()
        self._cfg = cfg
        self._collector_task_timeout = cfg.collector_task_timeout
        self._learner_task_timeout = cfg.learner_task_timeout

        self._callback = {
            'deal_with_collector_send_data': self.deal_with_collector_send_data,
            'deal_with_collector_finish_task': self.deal_with_collector_finish_task,
            'deal_with_learner_get_data': self.deal_with_learner_get_data,
            'deal_with_learner_send_info': self.deal_with_learner_send_info,
            'deal_with_learner_finish_task': self.deal_with_learner_finish_task,
            # 
            'deal_with_increase_collector': self.deal_with_increase_collector,
            'deal_with_decrease_collector': self.deal_with_decrease_collector,
            'deal_with_increase_learner': self.deal_with_increase_learner,
            'deal_with_decrease_learner': self.deal_with_decrease_learner,
        }
        # self._logger, _ = build_logger(path='./log', name='coordinator')
        self._logger = None
        self._interaction = CoordinatorInteraction(cfg.interaction, self.__nerver_server, self._callback, self._logger)
        self._learner_task_queue = Queue()
        self._collector_task_queue = Queue()
        self._commander = create_parallel_commander(cfg.commander)
        self._commander_lock = LockContext(LockContextType.THREAD_LOCK)

        # ############## Thread #####################
        self._assign_collector_thread = Thread(target=self._assign_collector_task, args=())
        self._assign_learner_thread = Thread(target=self._assign_learner_task, args=())
        self._produce_collector_thread = Thread(target=self._produce_collector_task, args=())
        self._produce_learner_thread = Thread(target=self._produce_learner_task, args=())

        self._replay_buffer = {}
        self._task_state = {}  # str -> TaskState
        self._historical_task = []
        # TODO remove used data
        # TODO load/save state_dict

        self._end_flag = True
        self._system_shutdown_flag = False

    def _assign_collector_task(self) -> None:
        r"""
        Overview:
            The function to be called in the assign_collector_task thread.
            Will get an collector task from ``collector_task_queue`` and assign the task.
        """
        while not self._end_flag:
            time.sleep(0.01)
            # get valid task, abandon timeout task
            if self._collector_task_queue.empty():
                continue
            else:
                collector_task, put_time = self._collector_task_queue.get()
                start_retry_time = time.time()
                max_retry_time = 0.3 * self._collector_task_timeout
                while True:
                    # timeout or assigned to collector
                    get_time = time.time()
                    if get_time - put_time >= self._collector_task_timeout:
                        self.info(
                            'collector task({}) timeout: [{}, {}, {}/{}]'.format(
                                collector_task['task_id'], get_time, put_time, get_time - put_time, self._collector_task_timeout
                            )
                        )
                        with self._commander_lock:
                            self._commander.notify_fail_collector_task(collector_task)
                        break
                    buffer_id = collector_task['buffer_id']
                    if buffer_id in self._replay_buffer:
                        if self._interaction.send_collector_task(collector_task):
                            self._record_task(collector_task)
                            self.info("collector_task({}) is successful to be assigned".format(collector_task['task_id']))
                            break
                        else:
                            self.info("collector_task({}) is failed to be assigned".format(collector_task['task_id']))
                    else:
                        self.info(
                            "collector_task({}) can't find proper buffer_id({})".format(collector_task['task_id'], buffer_id)
                        )
                    if time.time() - start_retry_time >= max_retry_time:
                        # reput into queue
                        self._collector_task_queue.put([collector_task, put_time])
                        start_retry_time = time.time()
                        self.info("collector task({}) reput into queue".format(collector_task['task_id']))
                        break
                    time.sleep(3)

    def _assign_learner_task(self) -> None:
        r"""
        Overview:
            The function to be called in the assign_learner_task thread.
            Will take a learner task from learner_task_queue and assign the task.
        """
        while not self._end_flag:
            time.sleep(0.01)
            if self._learner_task_queue.empty():
                continue
            else:
                learner_task, put_time = self._learner_task_queue.get()
                start_retry_time = time.time()
                max_retry_time = 0.1 * self._learner_task_timeout
                while True:
                    # timeout or assigned to learner
                    get_time = time.time()
                    if get_time - put_time >= self._learner_task_timeout:
                        self.info(
                            'learner task({}) timeout: [{}, {}, {}/{}]'.format(
                                learner_task['task_id'], get_time, put_time, get_time - put_time,
                                self._learner_task_timeout
                            )
                        )
                        with self._commander_lock:
                            self._commander.notify_fail_learner_task(learner_task)
                        break
                    if self._interaction.send_learner_task(learner_task):
                        self._record_task(learner_task)
                        # create replay_buffer
                        buffer_id = learner_task['buffer_id']
                        if buffer_id not in self._replay_buffer:
                            replay_buffer_cfg = learner_task.pop('replay_buffer_cfg', {})
                            self._replay_buffer[buffer_id] = ReplayBuffer(replay_buffer_cfg)
                            self._replay_buffer[buffer_id].run()
                            self.info("replay_buffer({}) is created".format(buffer_id))
                        self.info("learner_task({}) is successful to be assigned".format(learner_task['task_id']))
                        break
                    if time.time() - start_retry_time >= max_retry_time:
                        # reput into queue
                        self._learner_task_queue.put([learner_task, put_time])
                        start_retry_time = time.time()
                        self.info("learner task({}) reput into queue".format(learner_task['task_id']))
                        break
                    time.sleep(3)

    def _produce_collector_task(self) -> None:
        r"""
        Overview:
            The function to be called in the ``produce_collector_task`` thread.
            Will ask commander to produce a collector task, then put it into ``collector_task_queue``.
        """
        while not self._end_flag:
            time.sleep(0.01)
            with self._commander_lock:
                collector_task = self._commander.get_collector_task()
                if collector_task is None:
                    continue
            self.info("collector task({}) put into queue".format(collector_task['task_id']))
            self._collector_task_queue.put([collector_task, time.time()])

    def _produce_learner_task(self) -> None:
        r"""
        Overview:
            The function to be called in the produce_learner_task thread.
            Will produce a learner task and put it into the learner_task_queue.
        """
        while not self._end_flag:
            time.sleep(0.01)
            with self._commander_lock:
                learner_task = self._commander.get_learner_task()
                if learner_task is None:
                    continue
            self.info("learner task({}) put into queue".format(learner_task['task_id']))
            self._learner_task_queue.put([learner_task, time.time()])

    def state_dict(self) -> dict:
        return {}

    def load_state_dict(self, state_dict: dict) -> None:
        pass

    def start(self) -> None:
        self._end_flag = False
        self._interaction.start()
        self._produce_collector_thread.start()
        self._assign_collector_thread.start()
        self._produce_learner_thread.start()
        self._assign_learner_thread.start()

    def close(self) -> None:
        if self._end_flag:
            return
        self._end_flag = True
        time.sleep(1)
        self._produce_collector_thread.join()
        self._assign_collector_thread.join()
        self._produce_learner_thread.join()
        self._assign_learner_thread.join()
        self._interaction.close()
        # close replay buffer
        replay_buffer_keys = list(self._replay_buffer.keys())
        for k in replay_buffer_keys:
            v = self._replay_buffer.pop(k)
            v.close()
        self.info('coordinator is closed')

    def __del__(self) -> None:
        self.close()

    def deal_with_collector_send_data(self, task_id: str, buffer_id: str, data_id: str, data: dict) -> None:
        if task_id not in self._task_state:
            self.error('collector task({}) not in self._task_state when send data, throw it'.format(task_id))
            return
        if buffer_id not in self._replay_buffer:
            self.error("collector task({}) data({}) doesn't have proper buffer_id({})".format(task_id, data_id, buffer_id))
            return
        self._replay_buffer[buffer_id].push_data(data)
        self.info('collector task({}) send data({})'.format(task_id, data_id))

    def deal_with_collector_finish_task(self, task_id: str, finished_task: dict) -> None:
        if task_id not in self._task_state:
            self.error('collector task({}) not in self._task_state when finish, throw it'.format(task_id))
            return
        # finish_task
        with self._commander_lock:
            self._system_shutdown_flag = self._commander.finish_collector_task(task_id, finished_task)
        self._task_state.pop(task_id)
        self._historical_task.append(task_id)
        self.info('collector task({}) is finished'.format(task_id))
        if self._system_shutdown_flag:
            self.info('coordinator will be closed')

    def deal_with_increase_collector(self):
        with self._commander_lock:
            self._commander.increase_collector_task_space()

    def deal_with_decrease_collector(self):
        with self._commander_lock:
            self._commander.decrease_collector_task_space()

    def deal_with_increase_learner(self):
        with self._commander_lock:
            self._commander.increase_learner_task_space()

    def deal_with_decrease_learner(self):
        with self._commander_lock:
            self._commander.decrease_learner_task_space()

    def deal_with_learner_get_data(self, task_id: str, buffer_id: str, batch_size: int) -> List[dict]:
        if task_id not in self._task_state:
            self.error("learner task({}) get data doesn't have proper task_id".format(task_id))
            raise RuntimeError(
                "invalid learner task_id({}) for get data, valid learner_id is {}".format(
                    task_id, self._task_state.keys()
                )
            )
        if buffer_id not in self._replay_buffer:
            self.error("learner task({}) get data doesn't have proper buffer_id({})".format(task_id, buffer_id))
            return
        self.info("learner task({}) get data".format(task_id))
        return self._replay_buffer[buffer_id].sample(batch_size)

    def deal_with_learner_send_info(self, task_id: str, buffer_id: str, info: dict) -> None:
        if task_id not in self._task_state:
            self.error("learner task({}) send info doesn't have proper task_id".format(task_id))
            raise RuntimeError(
                "invalid learner task_id({}) for send info, valid learner_id is {}".format(
                    task_id, self._task_state.keys()
                )
            )
        if buffer_id not in self._replay_buffer:
            self.error("learner task({}) send info doesn't have proper buffer_id({})".format(task_id, buffer_id))
            return
        # self._replay_buffer[buffer_id].update(info['priority_info'])
        with self._commander_lock:
            self._commander.get_learner_info(task_id, info)
        self.info("learner task({}) send info".format(task_id))

    def deal_with_learner_finish_task(self, task_id: str, finished_task: dict) -> None:
        if task_id not in self._task_state:
            self.error("learner task({}) finish task doesn't have proper task_id".format(task_id))
            raise RuntimeError(
                "invalid learner task_id({}) for finish task, valid learner_id is {}".format(
                    task_id, self._task_state.keys()
                )
            )
        with self._commander_lock:
            buffer_id = self._commander.finish_learner_task(task_id, finished_task)
        self._task_state.pop(task_id)
        self._historical_task.append(task_id)
        self.info("learner task({}) finish".format(task_id))
        # delete replay buffer
        if buffer_id is not None:
            replay_buffer = self._replay_buffer.pop(buffer_id)
            replay_buffer.close()
            self.info('replay_buffer({}) is closed'.format(buffer_id))

    def info(self, s: str) -> None:
        # self._logger.info('[Coordinator({})]: {}'.format(self._coordinator_uid, s))
        print('[Coordinator({})]: {}'.format(self._coordinator_uid, s))
        pass

    def error(self, s: str) -> None:
        # self._logger.error('[Coordinator({})]: {}'.format(self._coordinator_uid, s))
        pass

    def _record_task(self, task: dict):
        self._task_state[task['task_id']] = TaskState(task['task_id'])

    @property
    def system_shutdown_flag(self) -> bool:
        return self._system_shutdown_flag