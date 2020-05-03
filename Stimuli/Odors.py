from Stimulus import *


class Odors(Stimulus):
    """ This class handles the presentation of Odors"""

    def prepare(self):
        self.probes = np.array([d['probe'] for d in self.conditions])
        conditions = self.conditions
        for icond, cond in enumerate(conditions):
            values = list(cond.values())
            names = list(cond.keys())
            for ivalue, value in enumerate(values):
                if type(value) is list:
                    value = tuple(value)
                cond.update({names[ivalue]: value})
            conditions[icond] = cond
        self.logger.log_conditions('OdorCond', conditions)

    def init(self):
        delivery_idx = self.curr_cond['delivery_idx']
        odor_idx = self.curr_cond['odor_idx']
        odor_dur = self.curr_cond['duration']
        odor_dutycycle = self.curr_cond['dutycycle']
        self.beh.give_odor(delivery_idx, odor_idx, odor_dur, odor_dutycycle)
        self.isrunning = True
        self.timer.start()

    def stop(self):
        self.isrunning = False