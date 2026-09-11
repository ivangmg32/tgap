class GraphModel:
    ''' This class should be implemented for each specfic
    Graph forecasting model (e.g GNN) to be used with this explainer.
    In fact, this can be used for creating a wrapper of any existing
    implementation of any library  '''   
    def predict (graph):
        ''' Given a graph, it provides the output in float number.
            This should be overwritten by the instances'''
        return None