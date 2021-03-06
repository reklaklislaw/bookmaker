#import yappi
import os, sys, time
import re
from copy import copy
from collections import OrderedDict
from datetime import date
import multiprocessing
from threading import Thread
from queue import Queue, Empty
import logging

from util import Util
from environment import Environment, Scandata
from core.featuredetection import FeatureDetection
from core.derive import PDF
from core.derive import Djvu
from core.derive import EPUB
from core.derive import PlainText
from core.crop import Crop
from core.ocr import OCR
from core.capture import ImageCapture
from gui.common import CommonActions as ca
from poll import PollsFactory


class ProcessHandling(object):
    """ Used to kick off and monitor CPU-bound threads.

        There are two ways to use this class, by calling 'add_process' or 
        'drain_queue'.

        'add_process' takes a function, a unique identifier for the process,
        args and kwargs. A thread will be created with your function as the 
        target and the arguments supplied and then return. Note that 
        'add_process' does not block.

        'drain_queue' on the other hand takes a list of process items (queue)
        and a mode, of which there are two, 'sync', and 'async'. A queue is a
        dictionary of dictionaries in the following form:

            queue[pid] = {'func': function_to_be_called,
                          'args': [list_of_args], 
                          'kwargs': {dict_of_kwargs}}
                          

        In 'sync' mode, 'drain_queue' will walk through each item in the queue
        and call its function with the supplied arguments, therefore blocking
        between each item, while in 'async' mode each item will be sent to 
        'add_process' and processed on one or more separate threads 
        simultaneously. Note that 'drain_queue' blocks in either mode; in 'sync'
        mode this is implied, while in 'async' mode 'drain_queue' checks for all
        spawned threads to indicate they are finished before exiting.
    """
    _thread_count_ignore = ('drain_queue',
                           'handle_thread_exceptions',
                           'distribute',
                           'run_pipeline')

    def __init__(self, max_threads=None, min_threads=None):        
        try:
            self.cores = multiprocessing.cpu_count()
        except NotImplemented:
            self.cores = 1
        if max_threads:
            self.max_threads = max_threads
        else:
            self.max_threads = self.cores
        if min_threads:
            self.min_threads = min_threads
        else:
            self.min_threads = self.max_threads
        self.processes = 0
        self._active_threads = {}
        self._inactive_threads = OrderedDict()
        self._item_queue = OrderedDict()
        self._waiting = set()
        self._exception_queue = Queue()
        self.Polls = PollsFactory(self)
        self._handled_exceptions = []
        self.OperationObjects = {}
        
    def _are_active_processes(self):
        if (self.processes == 0 and
            not [thread.func for pid, thread in self._active_threads.items()
                 if thread.func in ProcessHandling._thread_count_ignore]):
            return False
        else:
            return True

    def _already_processing(self, pid):
        if pid in self._active_threads:
            return True
        else:
            return False

    def is_waiting(self, pid):
        identifier = pid.split('.')[0]
        if identifier not in self.OperationObjects:
            return True
        for _pid in self._waiting:
            if pid in _pid:
                return True
        for _pid in self._item_queue:
            if pid in _pid:
                return True
        return False

    def _wait_till_idle(self, pids):
        finished = set()
        while True:
            if not self.Polls._should_poll:
                break            
            active_pids = set()
            for pid, thread in self._active_threads.items():
                active_pids.add(pid)
            for pid in pids:
                identifier = pid.split('.')[0]
                self.raise_child_exception(identifier)
                if pid not in active_pids and pid not in self._item_queue:
                    finished.add(pid)
            if len(finished) == len(pids):
                break
            else:
                time.sleep(1)

    def _wait(self, func, pid, args, kwargs):
        if not pid in self._item_queue:
            self._item_queue[pid] = (func, args, kwargs)

    def _submit_waiting(self):
        queue = []
        for pid, item in self._item_queue.items():
            func, args, kwargs = item
            if self.add_process(func, pid, args, kwargs):
                queue.append(pid)
                time.sleep(1)
            else:
                break
        queue.reverse()
        for pid in queue:
            del self._item_queue[pid]

    def _clear_inactive(self):
        inactive = {}
        for pid, thread in self._active_threads.items():
            if not thread.is_alive():
                thread.end_time = Util.microseconds()
                exec_time = round((thread.end_time - thread.start_time)/60, 2)
                thread.logger.info('Thread ' + str(pid) + 
                                   ' finished in ' + str(exec_time) + 
                                   ' minutes')
                inactive[pid] = thread
        for pid, thread in inactive.items():
            if thread.func not in ProcessHandling._thread_count_ignore:
                identifier, cls = pid.split('.')[:2]
                self.OperationObjects[identifier][cls].thread_count -= 1
                self.processes -= 1
            self._inactive_threads[pid] = thread
            del self._active_threads[pid]

    def abort(self, identifier=None, exception=RuntimeError('Aborted.')):
        if not identifier:
            self._item_queue = OrderedDict()
            self._waiting = set()
        destroy = []
        for pid, thread in self._active_threads.items():
            if not identifier:
                destroy.append(pid)
            else:
                if pid.startswith(identifier):
                    destroy.append(pid)
        for pid in destroy:
            self._destroy_thread(pid)
            identifier = pid.split('.')[0]
            if identifier in self.OperationObjects:
                for op, cls in self.OperationObjects[identifier].items():
                    cls.abort()
                    self._handled_exceptions.append((pid, exception))

    def _destroy_thread(self, pid):
        if pid in self._active_threads:
            thread = self._active_threads[pid]
            thread.logger.info('Destroying Thread ' + str(pid))
            if thread.func not in ProcessHandling._thread_count_ignore:
                self.processes -= 1
            del self._active_threads[pid]

    def _clear_exceptions(self, pid):
        remove = []
        for num, item in enumerate(self._handled_exceptions):
            _pid, exception = item
            if _pid == pid:
                remove.append(num)
        if remove:
            for num in remove:
                del self._handled_exceptions[num]

    def had_error(self, identifier, cls=None, mth=None):
        if cls: 
            _pid = '.'.join(('^', identifier, cls + '.[0-9]*'))
            if mth: 
                _pid = '.'.join((_pid, mth))
        else:
            _pid = '^' + identifier
        for item in self._handled_exceptions:
            pid, exception = item
            if re.match(_pid, pid):
                return True
        else:
            for cls in self.OperationObjects[identifier].values():
                if cls.aborted:
                    return True
        return False

    def raise_child_exception(self, identifier):
        for item in self._handled_exceptions:
            pid, exception = item
            if re.match('^' + identifier, pid):
                raise exception

    def join(self, args):
        self._exception_queue.put(args)
        self._exception_queue.join()

    def _parse_args(self, args, kwargs):
        if not isinstance(args, list):
            args = list([args,]) if args is not None else []
        if kwargs is None:
            kwargs = {}
        return args, kwargs

    def _parse_queue_data(self, data):
        d = []
        if 'func' not in data:
            raise LookupError('Failed to find \'func\' argument; nothing to do.')
        else:
            d.append(data['func'])
        for i in ('args', 'kwargs'):
            if i in data:
                d.append(data[i])
            else:
                d.append(None)
        return d

    def new_queue(self):
        class ProcessQueue(object):
            def __init__(self, ProcessHandler):
                self.ProcessHandler = ProcessHandler
                self.queue = OrderedDict()
            def add(self, book, cls=None, mth=None, args=None, kwargs=None):
                if not cls or not mth:
                    raise ValueError
                else:
                    if isinstance(mth, str):
                        pid = '.'.join((book.identifier, cls, mth))
                        f = self.ProcessHandler._get_operation_method(cls, mth, book)
                    else:
                        pid = '.'.join((book.identifier, cls, mth.__name__))
                        f = mth
                    self.queue[pid] = {'func': f,
                                       'args': args,
                                       'kwargs': kwargs}                    
            def drain(self, mode, thread=False):
                if not thread:
                    self.ProcessHandler.drain_queue(self.queue, mode)
                else:
                    fnc = self.ProcessHandler.drain_queue
                    pid = '.'.join((self.__str__(), fnc.__name__))
                    args = [self.queue, ]
                    kwargs = {'mode': 'sync'}
                    self.ProcessHandler.add_process(fnc, pid, args, kwargs)
        return ProcessQueue(self)

    def drain_queue(self, queue, mode, qpid=None, qlogger=None):
        self.Polls.start_polls()
        if qlogger and qpid:
            qstart = Util.microseconds()
        pids = []
        if mode == 'sync':
            for _pid in queue.keys():
                self._waiting.add(_pid)
        for pid, data in queue.items():
            pids.append(pid)
            func, args, kwargs = self._parse_queue_data(data)
            args, kwargs = self._parse_args(args, kwargs)
            identifier = pid.split('.')[0]
            logger = logging.getLogger(identifier)
            if mode == 'sync':        
                while not self.threads_available_for(pid):
                    time.sleep(1.0)
                    if not self.Polls._should_poll:
                        break
                else:
                    self._waiting.remove(pid)
                try:
                    start = Util.microseconds()
                    func(*args, **kwargs)
                    end = Util.microseconds()
                    exec_time = round((end-start)/60, 2)
                    logger.info('pid ' + pid + ' finished in ' + 
                                str(exec_time) + ' minutes')
                    self.raise_child_exception(identifier)
                except (Exception, BaseException):
                    exception, tb = Util.exception_info()
                    logger.error('pid ' + str(pid) + 
                                 ' encountered an error:\n' + str(tb))
                    if 'User aborted operations' in tb:
                        raise
            elif mode == 'async':
                self.add_process(func, pid, args, kwargs)                
        if mode == 'async':
            self._wait_till_idle(pids)                        
        if qlogger and qpid:
            qend = Util.microseconds()
            qexec_time = str(round((qend - qstart)/60, 2))
            qlogger.info('Drained queue ' + qpid + ' in ' + 
                         qexec_time + ' minutes')
        
    def threads_available_for(self, pid):
        if pid.startswith('<'):
            return True
        identifier, cls = pid.split('.')[:2]
        for _pid in self._active_threads:
            if _pid.startswith('<'):
                continue
            i, c = _pid.split('.')[:2]
            if i!=identifier and c!=cls:
                return False
        if self.cores - self.processes in range(1, self.max_threads+1):
            return True
        else:
            return False
                     
    def add_process(self, func, pid, args=None, kwargs=None):
        if self._already_processing(pid):
            return False
        self._clear_exceptions(pid)
        if not self.threads_available_for(pid):
            self._wait(func, pid, args, kwargs)
            return False
        else:
            self.Polls.start_polls()
            args, kwargs = self._parse_args(args, kwargs)
            new_thread = Thread(target=func, name=pid, 
                                args=args, kwargs=kwargs)
            new_thread.func = func.__name__
            new_thread.daemon = True
            identifier = pid.split('.')[0]
            new_thread.logger = logging.getLogger(identifier)
            new_thread.start_time = Util.microseconds()
            new_thread.start()
            self._active_threads[pid] = new_thread
            if new_thread.func not in ProcessHandling._thread_count_ignore:
                self.processes += 1
            new_thread.logger.info('New Thread Started --> ' +
                                   'Pid: ' + str(pid))                                   
            return True

    def add_operation_instance(self, instance, book):
        if not book.identifier in self.OperationObjects:
            self.OperationObjects[book.identifier] = {}
            cls = instance.__class__.__name__
            self.OperationObjects[book.identifier][cls] = instance

    def _get_operation_method(self, cls, method, book):
        if cls not in globals():
            raise LookupError('Could not find module \'' + cls + '\'')
        if not book.identifier in self.OperationObjects:
            self.OperationObjects[book.identifier] = {}
        if cls in self.OperationObjects[book.identifier]:
            instance = self.OperationObjects[book.identifier][cls]
        else:
            instance = globals()[cls](self, book)
            self.OperationObjects[book.identifier][cls] = instance
        instance.init_bookkeeping()
        function = getattr(self.OperationObjects[book.identifier][cls], method)
        return function

    def get_time_elapsed(self, start_time):
        current_time = time.time()
        elapsed_secs = int(current_time - start_time)
        elapsed_mins = int(elapsed_secs/60)
        elapsed_secs -= elapsed_mins * 60
        return elapsed_mins, elapsed_secs

    def get_time_remaining(self, total, completed, avg_exec_time, thread_count):
        fraction = float(completed) / (float(total))
        remaining_page_count = total - completed
        estimated_secs = int((int(avg_exec_time * remaining_page_count))/thread_count)
        estimated_mins = int(estimated_secs/60)
        estimated_secs -= estimated_mins * 60
        return estimated_mins, estimated_secs

    def get_op_state(self, book, identifier, cls, total):
        state = {'finished': False}
        op_obj = self.OperationObjects[identifier][cls]
        thread_count = self.OperationObjects[identifier][cls].thread_count
        if op_obj.completed['__finished__']:
            elapsed_mins, elapsed_secs = \
                self.get_time_elapsed(book.start_time)
            state['finished'] = True
            state['completed'] = total
            state['fraction'] = 1.0
            state['estimated_mins'] = 0.0
            state['estimated_secs'] = 0.0
            state['elapsed_mins'] = elapsed_mins
            state['elapsed_secs'] = elapsed_secs
        elif thread_count > 0:
            completed = 0
            op_num = len(op_obj.completed) - 1
            avg_exec_time = 0
            for op, leaf_t, in op_obj.completed.items():
                if op != '__finished__':
                    c = len(leaf_t)
                    completed += c
                    if c > 0:
                        avg_exec_time += op_obj.get_avg_exec_time(op)
            fraction = float(completed)/(float(total)*op_num)
            estimated_mins, estimated_secs = \
                self.get_time_remaining(total, completed/op_num,
                                        avg_exec_time,
                                        thread_count)
            elapsed_mins, elapsed_secs = \
                self.get_time_elapsed(book.start_time)            
            state['completed'] = completed
            state['fraction'] = fraction
            state['estimated_mins'] = estimated_mins
            state['estimated_secs'] = estimated_secs
            state['elapsed_mins'] = elapsed_mins
            state['elapsed_secs'] = elapsed_secs
        else:
            state['completed'] = 0
            state['fraction'] = 0.0
            state['estimated_mins'] = '--'
            state['estimated_secs'] = '--'
            state['elapsed_mins'] = '--'
            state['elapsed_secs'] = '--'
        return state
