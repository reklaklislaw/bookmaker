import os

from .component import Component

class Djvused(Component):

    """
    Multi Purpose DjVu Document Editor

    """

    args = ['options', 'script', 'djvu_file']
    executable = 'djvused'

    def __init__(self, book):
        super(Djvused, self).__init__()
        self.book = book
        dirs = {'derived': self.book.root_dir + '/' + \
                    self.book.identifier + '_derived'}
        self.book.add_dirs(dirs)
        
    def run(self, leaf, djvu_file=None, options=None, 
            script=None, callback=None, **kwargs):
        leafnum = "%04d" % leaf
        if not djvu_file:
            djvu_file = (self.book.dirs['derived'] + '/' +
                         self.book.identifier + '_' + leafnum + '.djvu')
        if not os.path.exists(djvu_file):
            raise IOError('Cannot find ' + djvu_file)
        
        kwargs.update({'djvu_file': djvu_file,
                       'options': options,
                       'script': script})
        
        output = self.execute(kwargs, return_output=True)
        if callback:
            self.execute_callback(callback, leaf, output, **kwargs)
        else:
            return output
