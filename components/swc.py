from environment import Environment
from util import Util
from component import Component


class SWC(Component):
    """
    Sliding Window Clustering
    -------------------------

    Takes a set of points in ascending x/y order and outputs a list of
    clusters. The algorithm works by recursively sliding a 'window' across 
    the set of points, gathering them into clusters. The window starts 
    centered around the first point and ... 


    in_file: the file containing the set of points. Each vertice is to be 
             separated by a space and each point by a newline, ie, "X Y\n"

    out_file: the file where the cluster dimensions will be written. the
              dimensions will be of the format "L T R B\n", where L is the 
              left edge, T the top, R the right, and B the bottom.

    window_width: the width of the window used in clustering.
                
    window_height: the height of the window used in clustering.

    skew_angle: the angle at which to rotate the points by before clustering.

    center_x: the x value of the point of rotation
    
    center_y: the y value of the point of rotation

    """

    args = ['in_file','out_file',
            'window_width','window_height',
            'skew_angle','center_x','center_y']

    #executable = Environment.current_path + '/bin/clusterAnalysis/slidingWindow/./slidingWindow'
    executable = '/home/reklak/development/gits/bookmaker/bin/clusterAnalysis/slidingWindow/./slidingWindow'
    #cmd =  executable + '^ {in_file} {out_file} {window_width} {window_height} {skew_angle} {center_x} {center_y}',


    def __init__(self):
        super(SWC, self).__init__(SWC.args)


    
