import os

from util import Util
from .operation import Operation
from environment import Environment


class Crop(Operation):
    """ Handles the cropping of images.
    """

    components = {'cropper': {'class': 'Cropper',
                              'callback': None}}

    def __init__(self, ProcessHandler, book):
        self.Processhandler = ProcessHandler
        self.book = book
        try:
            super(Crop, self).__init__(Crop.components)
            self.init_components(self.book)
        except:
            pid = self.make_pid_string('__init__')
            self.ProcessHandler.join((pid, Util.exception_info()))            

    def cropper_pipeline(self, start=None, end=None, **kwargs):
        if None in (start, end):
            start, end = 0, self.book.page_count
        for leaf in range(start, end):
            self.book.logger.debug('Cropping leaf ' + str(leaf))
            #callback = self.components['cropper']['callback']
            try:
                self.Cropper.run(leaf, **kwargs)
            except:
                self.ProcessHandler.join((self.book.identifier + 
                                          '_Crop_cropper_pipeline',
                                          Util.exception_info(),
                                          self.book.logger))
            else:
                exec_time = self.Cropper.get_last_exec_time()
                self.complete_process(leaf, exec_time)