
import random
from math import sin,pi
import numpy as np
import time

class Gait:
    """Motor target generator, using predefined gait_switcher.
    
    The motor signal follows the parametrised sine
        A * sin(2*pi*f*x + p) + B
    with the parameters A, f, p, B
    
    ``params``
        *dict* holding the parameters:
         keys:   amplitude, frequency, phase, offset
         values: 4-tuples holding the parameter values. The order is
                 front-left, front-right, rear-left, rear-right
    
    """
    def __init__(self, params, name=None):
        self.params = params
        if name is None: name = 'Unknown gait'
        self.name = name
    def __iter__(self):
        return self.iter(0, 20)
    def iter(self, time_start_ms, step):
        """Return the motor target sequence in the interval [*time_start_ms*, *time_end_ms*]."""
        params = zip(self.params['amplitude'], self.params['frequency'], self.params['phase'], self.params['offset'])
        current_time_ms = time_start_ms
        while True:
            current_time_ms += step
            yield [A * sin(2.0 * pi * (freq * current_time_ms / 1e3 - phase)) + offset for A, freq, phase, offset in params]
    def __str__(self):
        return self.name

class PuppyActor:
    """Template class for an actor, used in *WebotsPuppyMixin*.
    
    The actor is called after every control period, when a new sequence
    of motor targets is required. It is expected to return an iterator
    which in every step produces a 4-tuple, representing the targets
    of the motors.
    The order is front-left, front-right, rear-left, rear-right.
    
    ``epoch``
        The sensor measurements in the previous control period. They
        are returned as dict, with the sensor name as key and a
        numpy array of observations as value.
        
        Note that the motor targets are one-step ahead in the sense that
        they are applied but have not yet been executed.
        
        Further, note that the *dict* may be empty (this is guaranteed
        at least once in the simulator initialization).
    
    ``time_start_ms``
        The (simulated) time from which on the motor target will be
        applied.
    
    ``time_end_ms``
        The (simulated) time up to which the motor target must at least
        be defined.
    
    ``step_size_ms``
        The motor period, i.e. the number of milliseconds pass until
        the next motor target is applied.
    
    If the targets are represented by a list, it must at least have
        (*time_end_ms* - *time_start_ms*) / *step_size_ms*
    items and it has to be returned as iterator, as in
        >>> iter(myList)
    
    """
    def __call__(self, epoch, time_start_ms, time_end_ms, step_size_ms):
        raise NotImplementedError()

class RandomGaitControl(PuppyActor):
    """From a list of available gait_switcher, randomly select one."""
    def __init__(self, gait_switcher):
        self.gaits = gait_switcher[:]
    def __call__(self, epoch, time_start_ms, time_end_ms, step_size):
        gait = random.choice(self.gaits)
        print gait
        return gait.iter(time_start_ms, step_size)

class ConstantGaitControl(PuppyActor):
    """Given a gait, always apply it."""
    def __init__(self, gait):
        self.gait = gait
    def __call__(self, epoch, time_start_ms, time_end_ms, step_size):
        return self.gait.iter(time_start_ms, step_size)

class SequentialGaitControl(PuppyActor):
    """Execute a predefined sequence of gait_switcher.
    
    Note that it's assumed that *gait_iter* does not terminate
    permaturely.
    """
    def __init__(self, gait_iter):
        self.gait_iter = gait_iter
    def __call__(self, epoch, time_start_ms, time_end_ms, step_size):
        gait = self.gait_iter.next()
        return gait.iter(time_start_ms, step_size)

class PuppyCollector(PuppyActor):
    """Collect sensor readouts and store them in a file.
    
    The data is stored in the *HDF5* format. For each simulation run,
    there's a group, identified by a running number. Within each group,
    the sensor data is stored in exclusive datasets, placed under the
    sensor's name.
    
    ``expfile``
        Path to the file into which the experimental data should be
        stored.
    
    ``headers``
        Additional headers, stored with the current experiment.
        A *dict* is expected. Default is None (no headers).
    
    """
    def __init__(self, actor, expfile, headers=None):
        # set actor
        self.actor = actor
        
        # create experiment storage
        import h5py
        self.fh = h5py.File(expfile,'a')
        name = str(len(self.fh.keys()))
        self.grp = self.fh.create_group(name)
        amngr = h5py.AttributeManager(self.grp)
        amngr.create('time', time.time())
        if headers is not None:
            for k in headers: amngr.create(k, headers[k])
        
        print "Using storage", name
    
    def __del__(self):
        self.fh.close()
    
    # if RevertTumbling is used:
    #  last epoch will not be written since it is not necessarily complete;
    #  grace time deals with this (> one epoch)
    def __call__(self, epoch, time_start_ms, time_end_ms, step_size):
        # write epoch to dataset
        for k in epoch:
            if k not in self.grp:
                N, = epoch[k].shape
                self.grp.create_dataset(k, shape=(N,), data=epoch[k], chunks=True, maxshape=(None,))
            else:
                N, = self.grp[k].shape
                K, = epoch[k].shape
                self.grp[k].resize(size=(N+K,))
                self.grp[k][N:] = epoch[k]
        self.fh.flush()
        return self.actor(epoch, time_start_ms, time_end_ms, step_size)

class PuppyCollectorTables(PuppyActor):
    """Collect sensor readouts and store them in a file.
    
    .. note::
        Uses PyTables instead of h5py
    
    The data is stored in the *HDF5* format. For each simulation run,
    there's a group, identified by a running number. Within each group,
    the sensor data is stored in exclusive datasets, placed under the
    sensor's name.
    
    ``expfile``
        Path to the file into which the experimental data should be
        stored.
    
    ``headers``
        Additional headers, stored with the current experiment.
        A *dict* is expected. Default is None (no headers).
    
    """
    def __init__(self, actor, expfile, headers=None):
        # set actor
        self.actor = actor
        
        # create experiment storage
        import tables
        self.fh = tables.File(expfile,'a')
        name = 'exp' + str(len(self.fh.root._v_groups))
        self.grp = self.fh.create_group(self.fh.root, name)
        
        self.grp._f_setattr('time', time.time())
        if headers is not None:
            for k in headers: self.grp._f_setattr(k, headers[k])
        
        print "Using storage", name
    
    def __del__(self):
        self.fh.close()
    
    # if RevertTumbling is used:
    #  last epoch will not be written since it is not necessarily complete;
    #  grace time deals with this (> one epoch)
    def __call__(self, epoch, time_start_ms, time_end_ms, step_size):
        # write epoch to dataset
        for k in epoch:
            if k not in self.grp:
                N, = epoch[k].shape
                self.fh.create_earray(self.grp, k, chunkshape=(N,), obj=epoch[k])
            else:
                self.grp._v_children[k].append(epoch[k])
        self.fh.flush()
        return self.actor(epoch, time_start_ms, time_end_ms, step_size)
