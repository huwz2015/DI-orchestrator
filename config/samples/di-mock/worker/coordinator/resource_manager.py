import random


class NaiveResourceManager(object):
    r"""
    Overview:
        the naive resource manager
    Interface:
        __init__, assign_collector, assign_learner, update
    """

    def __init__(self) -> None:
        r"""
        Overview:
            init the resouce manager
        """
        self._worker_type = ['collector', 'learner']
        self._resource_info = {k: {} for k in self._worker_type}

    def assign_collector(self, collector_task: dict) -> dict:
        r"""
        Overview:
            assign the collector_task randomly and return the resouce info
        Arguments:
            - collector_task (:obj:`dict`): the collector task to assign
        """
        available_collector_list = list(self._resource_info['collector'].keys())
        if len(available_collector_list) > 0:
            selected_collector = random.sample(available_collector_list, 1)[0]
            info = self._resource_info['collector'].pop(selected_collector)
            return {'collector_id': selected_collector, 'resource_info': info}
        else:
            return None

    def assign_learner(self, learner_task: dict) -> dict:
        r"""
        Overview:
            assign the learner_task randomly and return the resouce info
        Arguments:
            - learner_task (:obj:`dict`): the learner task to assign
        """
        available_learner_list = list(self._resource_info['learner'].keys())
        if len(available_learner_list) > 0:
            selected_learner = random.sample(available_learner_list, 1)[0]
            info = self._resource_info['learner'].pop(selected_learner)
            return {'learner_id': selected_learner, 'resource_info': info}
        else:
            return None

    def update(self, name: str, worker_id: str, resource_info: dict) -> None:
        r"""
        Overview:
            update the reource info
        """
        assert name in self._worker_type
        self._resource_info[name][worker_id] = resource_info

    def delete(self, name: str, worker_id: str) -> None:
        assert name in self._worker_type
        self._resource_info[name].pop(worker_id)

    def have_assigned(self, name:str, work_id: str):
        assert name in self._worker_type
        return work_id not in self._resource_info[name]