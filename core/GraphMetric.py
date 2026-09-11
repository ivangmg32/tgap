
class Metric:
    ''' For measuring the impact on the model output on a TG,
    programmers and the framework will use this wrapper.'''
    def measure(graph):
        '''This method return a numerical value of measure
        a given graph. This should be overriden by the
        implementations.'''
        return 0.0