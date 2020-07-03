from utils.Timer import *
from StateMachine import *
from datetime import datetime, timedelta


class State(StateClass):
    def __init__(self, parent=None):
        self.timer = Timer()
        if parent:
            self.__dict__.update(parent.__dict__)

    def setup(self, logger, BehaviorClass, StimulusClass, session_params, conditions):
        self.logger = logger
        # Initialize params & Behavior/Stimulus objects
        self.beh = BehaviorClass(self.logger, session_params)
        self.stim = StimulusClass(self.logger, session_params, conditions, self.beh)
        self.params = session_params
        self.logger.log_session(session_params, '2AFC')
        self.logger.log_conditions(conditions, self.stim.get_condition_tables())

        exitState = Exit(self)
        self.StateMachine = StateMachine(Prepare(self), exitState)

        # Initialize states
        global states
        states = {
            'PreTrial'     : PreTrial(self),
            'Trial'        : Trial(self),
            'PostTrial'    : PostTrial(self),
            'InterTrial'   : InterTrial(self),
            'Reward'       : Reward(self),
            'Punish'       : Punish(self),
            'Sleep'        : Sleep(self),
            'OffTime'      : OffTime(self),
            'Exit'         : exitState}

    def entry(self):  # updates stateMachine from Database entry - override for timing critical transitions
        self.StateMachine.status = self.logger.get_setup_info('status')
        self.logger.update_state(self.__class__.__name__)

    def run(self):
        self.StateMachine.run()

    def is_sleep_time(self):
        now = datetime.now()
        t = datetime.strptime(self.params['start_time'], "%H:%M:%S")
        start = now.replace(hour=0, minute=0, second=0) + timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)
        t = datetime.strptime(self.params['stop_time'], "%H:%M:%S")
        stop = now.replace(hour=0, minute=0, second=0) + timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)
        if stop < start:
            stop = stop + timedelta(days=1)
        time_restriction = now < start or now > stop
        return time_restriction


class Prepare(State):
    def run(self):
        self.stim.setup() # prepare stimulus

    def next(self):
        if self.is_sleep_time():
            return states['Sleep']
        else:
            return states['PreTrial']


class PreTrial(State):
    def entry(self):
        self.stim.prepare()
        self.beh.prepare(self.stim.curr_cond)
        self.timer.start()
        self.logger.update_state(self.__class__.__name__)

    def run(self): pass

    def next(self):
        if self.beh.is_ready(self.stim.curr_cond['init_duration']):
            return states['Trial']
        elif self.is_sleep_time():
            return states['Sleep']
        else:
            self.StateMachine.status = self.logger.get_setup_info('status')
            return states['PreTrial']


class Trial(State):
    def __init__(self, parent):
        self.__dict__.update(parent.__dict__)
        self.probe = 0
        self.trial_start = 0
        super().__init__()

    def entry(self):
        self.is_ready = True
        self.resp_ready = False
        self.logger.update_state(self.__class__.__name__)
        self.stim.init()
        self.timer.start()  # trial start counter
        self.trial_start = self.logger.init_trial(self.stim.curr_cond['cond_hash'])

    def run(self):
        self.stim.present()  # Start Stimulus
        self.probe = self.beh.is_licking(self.trial_start)
        if self.timer.elapsed_time() >= self.stim.curr_cond['delay_duration'] and not self.resp_ready: # delay completed
            self.resp_ready = True
        else:
            self.is_ready = self.beh.is_ready(self.timer.elapsed_time() + self.stim.curr_cond['init_duration'])  # update times

    def next(self):
        if not self.is_ready and not self.resp_ready:                           # did not wait
            return states['Punish']
        elif self.probe > 0 and self.resp_ready and self.probe != self.stim.curr_cond['probe']: # response to incorrect probe
            return states['Punish']
        elif self.probe > 0 and self.resp_ready and self.probe == self.stim.curr_cond['probe']: # response to correct probe
            return states['Reward']
        elif self.timer.elapsed_time() > self.stim.curr_cond['trial_duration']:      # timed out
            return states['PostTrial']
        else:
            return states['Trial']

    def exit(self):
        self.logger.log_trial()
        self.logger.ping()


class PostTrial(State):
    def run(self):
        self.stim.stop()  # stop stimulus when timeout

    def next(self):
        return states['InterTrial']


class InterTrial(State):
    def run(self):
        if self.beh.is_licking():
            self.timer.start()

    def next(self):
        if self.is_sleep_time():
            return states['Sleep']
        elif self.beh.is_hydrated():
            return states['OffTime']
        elif self.timer.elapsed_time() >= self.stim.curr_cond['intertrial_duration']:
            return states['PreTrial']
        else:
            return states['InterTrial']


class Reward(State):
    def run(self):
        self.beh.reward(self.stim.curr_cond['reward_amount'])
        self.stim.stop()
        print('Rewarding')

    def next(self):
        return states['InterTrial']


class Punish(State):
    def entry(self):
        self.beh.punish()
        self.stim.stop()
        self.stim.unshow([0, 0, 0])
        self.timer.start()
        self.logger.update_state(self.__class__.__name__)
        print('Punishing')

    def run(self): pass

    def next(self):
        if self.timer.elapsed_time() >= self.stim.curr_cond['timeout_duration']:
            return states['InterTrial']
        else:
            return states['Punish']

    def exit(self):
        self.stim.unshow()


class Sleep(State):
    def entry(self):
        self.logger.update_state(self.__class__.__name__)
        self.logger.update_setup_status('sleeping')
        self.stim.unshow([0, 0, 0])

    def run(self):
        self.logger.ping()
        time.sleep(5)

    def next(self):
        if self.logger.get_setup_info('status') == 'stop':  # if wake up then update session
            return states['Exit']
        elif self.is_sleep_time() and self.logger.get_setup_info('status') == 'sleeping':
            return states['Sleep']
        elif self.logger.get_setup_info('status') == 'sleeping':  # if wake up then update session
            self.logger.update_setup_status('running')
            return states['Exit']
        else:
            return states['PreTrial']


class OffTime(State):
    def entry(self):
        self.logger.update_state(self.__class__.__name__)
        self.logger.update_setup_status('offtime')
        self.stim.unshow([0, 0, 0])

    def run(self):
        self.logger.ping()
        time.sleep(5)

    def next(self):
        if self.logger.get_setup_info('status') == 'stop':  # if wake up then update session
            return states['Exit']
        elif self.is_sleep_time():
            return states['Sleep']
        else:
            return states['OffTime']


class Exit(State):
    def run(self):
        self.beh.cleanup()
        self.stim.close()
