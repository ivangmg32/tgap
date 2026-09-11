
class TemporalGraphModel:
    ''' This class should be implemented for each specfic
    Temporal Graph forecasting model to be used with this explainer.
    In fact, this can be used for creating a wrapper of any existing
    implementation of any library  '''   
    def predict (temporalGraph):
        ''' Given a time-series graphs, it predicts the next graph.
            This should be overwritten by the instances'''
        return None