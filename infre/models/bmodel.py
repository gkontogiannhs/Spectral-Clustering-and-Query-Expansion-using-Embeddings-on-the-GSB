from numpy import mean, array, zeros
from math import log2

from os.path import join, exists
from os import makedirs, getcwd
from pickle import dump, load
from bz2 import BZ2File
from pandas import DataFrame

from infre.tools import apriori
from infre.metrics import cosine_similarity
from abc import ABC, abstractclassmethod
from infre.metrics import precision_recall


class BaseIRModel(ABC):
    def __init__(self, collection):

        # model name
        self.model = self._model()

        # collection object to handle documents and inverted index
        self.collection = collection

        # array used as matrix to hold the query vector 
        # representation generated by each query
        self._q2vec = []

        # array used as a 3D tensor to hold all the 
        # ermset per document frequency generated for each query
        self._docs2vec = []

        # each index position corresponds to the mean precision of each query
        self.precision = []

        # each index position corresponds to the mean recall of each query
        self.recall = []

        # model weights 
        self._m_weights = []


    def _model(self): return __class__.__name__


    @abstractclassmethod
    def _model_func(self, termsets):
        pass

    @abstractclassmethod
    def _vectorizer(self, tsf_ij, idf, *args):
        pass

    
    def fit(self, queries, mf=10):

        # inverted index of collection documents
        inv_index = self.collection.inverted_index

        # for each query
        for i, query in enumerate(queries, start=1):

            # apply apriori to find frequent termsets
            freq_termsets = apriori(query, inv_index, min_freq=mf)
            
            # print(f"Query {i}/{len(queries)}: len = {len(query)}, frequent = {len(freq_termsets)}")

            # vectorized query generated by apriori
            idf_vec = self.query2vec(freq_termsets) # (1 X len(termsets)) vector
            
            # vectorized documents generated by apriori query
            tsf_ij = self.termsets2vec(freq_termsets) # (len(termsets) X N) matrix
            
            # append matrix representation of termset frequency per document
            self._docs2vec.append(tsf_ij)

            # append vector query generated by apriori
            self._q2vec.append(idf_vec)

            # model staff
            self._m_weights.append(self._model_func(freq_termsets))

            # print(f'{(time() - start):.2f} secs.\n') TODO: loadbar
        return self
    

    def evaluate(self, relevant):
        
        num_of_q = len(self._q2vec)

        # for each query and (dtm, relevant) pair
        for i, (qv, dv, rel) in enumerate(zip(self._q2vec, self._docs2vec, relevant)):
            
            # all the money function
            # document - termset matrix - model balance weight
            dtsm = self._vectorizer(dv, qv, self._m_weights[i])
            
            # cosine similarity between query and every document
            qd_sims = self.qd_similarities(qv, dtsm)
            
            # rank them in desc order
            retrieved_docs = self.rank_documents(qd_sims)

            # precision | recall of ranking
            pre, rec = precision_recall(retrieved_docs.keys(), rel)

            # print(f"=> Query {i+1}/{num_of_q}, precision = {pre:.3f}, recall = {rec:.3f}")

            self.precision.append(round(pre, 3))
            self.recall.append(round(rec, 3))

        return array(self.precision), array(self.recall)
    

    def query2vec(self, termsets):

        # number of docs
        N = self.collection.num_docs
        
        # len(value) => in how many documents each termset appears
        return array([round(log2(1 + (N / len(value))), 3) for value in termsets.values()])
    

    # termset frequency
    def termsets2vec(self, termsets):
        #    d1  d2  d3  . . .  di
        # S1 f11 f12 f13 . . . f1i
        # S2     f22            .
        # S3         f33        .s
        # .               .     .
        # .                  .  .
        # Sj fj1 fj2 fj3 . . . fij

        # number of documents/columns
        N = self.collection.num_docs

        # get inv index
        inv_index = self.collection.inverted_index

        # initialize zero matrix with the appropriate dims
        tsf_ij = zeros((len(termsets), N))

        # for each termset
        for i, (termset, docs) in enumerate(termsets.items()):
            # e.x. termset = fronzenset{'t1', 't2', 't3'}
            terms = list(termset) # ['t1', 't2', 't3']
            temp = {}
            # for each term in the termset
            for term in terms:
                post_list = inv_index[term]['posting_list']
                # for term's id, tf pair
                for id, tf in post_list: 
                    # if belongs to the intersection of the termset
                    if id in docs:
                        # create a dict to hold frequencies for each term of termset
                        # by taking the min f, we get the termset frequency
                        if id in temp: temp[id] += [tf]
                        else: temp[id] = [tf]

            # assign raw termset frequencies
            for id, tfs in temp.items():
                tsf_ij[i, id-1] = round((1 + log2(min(tfs))), 3)
        
        return tsf_ij


    # get cos similarity for each document-query pair
    def qd_similarities(self, query, dtsm):
        return {id: cosine_similarity(query, dv) for id, dv in enumerate(dtsm.T, start=1)}


    # method to rank the documents a.k.a sort by desc similarity
    def rank_documents(self, qd_sims):
        return {id: sim for id, sim in sorted(qd_sims.items(), key=lambda item: item[1], reverse=True)}
    

    # stores to excel file the precision recall performance of the model
    def save_results(self, *args):

        # pre, rec = args if args else self.precision, self.recall
        if args:
            pre, rec = args
        else:
            pre, rec = self.precision, self.recall
     
        df = DataFrame(list(zip(pre, rec)), columns=["precision", "recall"])
      
        path = join(getcwd(), 'saved_models', self.model, 'results')

        if not exists(path): makedirs(path)

        df.to_excel(join(path, f'{self.model.lower()}.xlsx'))

        return self

