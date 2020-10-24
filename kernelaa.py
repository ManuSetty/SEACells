"""
Implementation of fast archetypal analysis (kernelized)
http://citeseerx.ist.psu.edu/viewdoc/download?doi=10.1.1.710.1085&rep=rep1&type=pdf#page=8

To do: initialize B from greedily-selected columns from RRQR (seems unnecessary)
How to determine convergence?
"""
import numpy as np
from tqdm.notebook import tqdm
from sklearn.metrics import pairwise_distances as cdist
from scipy.stats import multinomial

class ArchetypalAnalysis:
    """
    Fast kernel archetypal analysis.
    Finds archetypes and weights given precomputed kernel matrix.

    Attributes:
        k: number of components
        max_iter: maximum number of iterations for Frank-Wolfe update
        verbose: verbosity
    """

    def __init__(self, k:int, max_iter:int=50, verbose:bool=True):
        self.k = k
        self.max_iter = max_iter
        self.verbose = verbose

    def _updateA(self, K, A, B):
        """
        Given archetype matrix B and kernel matrix K, compute assignment matrix A

        Inputs:
            K: n*n kernel matrix (sparse)
            B: n*k matrix (dense)

        Returns:
            A: k*n matrix (dense)
        """
        n, k = B.shape

        # initialize matrix A (don't reinitialize?)
        A = np.zeros((k, n))
        A[0,:] = 1.

        t = 0 # current iteration (determine multiplicative update)

        # precompute some gradient terms
        t2 = (K @ B).T
        t1 = t2 @ B

        # update rows of A for given number of iterations
        while t < self.max_iter:

            # compute gradient (must convert matrix to ndarray)
            G = 2. * np.array(t1 @ A - t2)

            # get argmins
            amins = np.argmin(G, axis=0)

            # loop free implementation
            e = np.zeros((k,n))
            e[amins, np.arange(n)] = 1.

            A += 2. / (t + 2.) * (e - A)
            t += 1

        return A

    def _updateB(self, K, A, B):
        """Given assignment matrix A and kernel matrix K, compute archetype matrix B

        Inputs:
            K: n*n kernel matrix (sparse)
            A: k*n matrix (dense)

        Returns:
            B: n*k matrix (dense)
        """
        k, n = A.shape

        # initialize matrix B (don't re-initialize?)
        B = np.zeros((n,k))
        B[0, :] = 1.

        # keep track of error
        t = 0

        # precompute some terms
        t1 = A @ A.T
        t2 = K @ A.T

        # update rows of B for a given number of iterations
        while t < self.max_iter:

            # compute gradient (need to convert np.matrix to np.array)
            G = 2. * np.array(K @ B @ t1 - t2)

            # get all argmins
            amins = np.argmin(G, axis=0)

            e = np.zeros((n,k))
            e[amins, np.arange(k)] = 1.

            B += 2. / (t+2.) * (e - B)

            t += 1

        return B

    def _initialize_archetypes(self, K):
        """Fast greedy adaptive CSSP

        From https://arxiv.org/pdf/1312.6838.pdf

        Inputs:
            K (n*n) kernel matrix
        """
        n = K.shape[0]
        k = self.k
        X=K

        # precompute A.T * A
        #ATA = K.T @ K
        ATA = K

        if self.verbose:
            print("Initializing archetypes")

        f = np.array((ATA.multiply(ATA)).sum(axis=0)).ravel()
        #f = np.array((ATA * ATA).sum(axis=0)).ravel()
        g = np.array(ATA.diagonal()).ravel()

        d = np.zeros((k, n))
        omega = np.zeros((k, n))

        # keep track of selected indices
        centers = np.zeros(k, dtype=int)

        # sampling
        for j in tqdm(range(k)):

            score = f/g
            p = np.argmax(score)

            # print residuals
            residual = np.sum(f)

            delta_term1 = ATA[:,p].toarray().squeeze()
            #print(delta_term1)
            delta_term2 = np.multiply(omega[:,p].reshape(-1,1), omega).sum(axis=0).squeeze()
            delta = delta_term1 - delta_term2

            # some weird rounding errors
            delta[p] = np.max([0, delta[p]])

            o = delta / np.max([np.sqrt(delta[p]), 1e-6])
            omega_square_norm = np.linalg.norm(o)**2
            omega_hadamard = np.multiply(o, o)
            term1 = omega_square_norm * omega_hadamard

            # update f (term2)
            pl = np.zeros(n)
            for r in range(j):
                omega_r = omega[r,:]
                pl += np.dot(omega_r, o) * omega_r

            ATAo = (ATA @ o.reshape(-1,1)).ravel()
            term2 = np.multiply(o, ATAo - pl)

            # update f
            f += -2. * term2 + term1

            # update g
            g += omega_hadamard

            # store omega and delta
            d[j,:] = delta
            omega[j,:] = o

            # add index
            centers[j] = int(p)

        # create matrix B

        # #centers = np.random.choice(range(n), k, replace=False)
        # centers = np.zeros(k, dtype=int)

        # # select initial point randomly
        # new_point = np.random.choice(range(n), 1)
        # centers[0] = new_point

        # # initialize min distances
        # distances = cdist(X, X[new_point, :], metric="euclidean")

        # # assign rest of points
        # for ix in tqdm(range(1, k)):
        #     new_point = np.argmax(distances.ravel())
        #     centers[ix] = new_point
        #     #print(new_point)

        #     # get distance from all poitns to new points
        #     new_point_distances = cdist(X, X[new_point, :], metric="euclidean")

        #     # update min distances
        #     combined_distances = np.hstack([distances, new_point_distances])

        #     distances = np.min(combined_distances, axis=1, keepdims=True)

        #     # make sure that the distance of already added points is zero to prevent duplicates
        #     distances[centers,0] = 0

        B = np.zeros((n, k))
        B[centers, np.arange(k)] = 1.
        B = np.zeros((n, k))
        B[centers, np.arange(k)] = 1.

        return B

    def _residuals(self, K, A, B):
        """Use trace trick to compute residual squared error

        Actual formula for the error is
            E = ||X - XBA||^2
            = tr(X.T @ X 
                - 2 X.T * X * B * A 
                + A.T * B.T * X.T * X * B * A)

        (Trace distributes over sums and invariant to permutation)

        Inputs:
            K: n*n kernel matrix (sparse)
            A: k*n assignments matrix (dense)
            B: n*k archetype matrix (dense)

        Returns:
            E (float)
        """

        # term1 = np.trace(K)
        term1 = K.shape[0]
        term2 = np.trace(np.array(A @ K @ B))
        term3 = np.trace(np.array(A @ K @ A.T) @ (B.T @ B))

        return term1 - 2. * term2 + term3

    def _fit(self, K, n_iter:int, B0=None):
        """Compute archetypes and loadings given kernel matrix K

        Input:
            K: positive semidefinite kernel matrix (n*n)
            n_iter: number of iterations

        Updates model to add B and A
        """
        # initialize B (update this to allow initialization from RRQR)
        n = K.shape[0]
        k = self.k

        # B = np.eye(n, k)

        if B0 is not None:
            B = B0
        else:
            B = self._initialize_archetypes(K)

        A = np.eye(k, n)
        A[0,:] = 1.

        for it in range(n_iter):
            A = self._updateA(K, A, B)
            B = self._updateB(K, A, B)

            # compute error
            error = self._residuals(K, A, B)

            print("Iteration %d of %d. Error: %.8f" % (it, n_iter, error))

        self.A_ = A
        self.B_ = B
        self.Z_ = B.T @ K

    def fit(self, K, n_iter:int=8, B0=None):
        """Wrapper to fit model given kernel matrix and max number of iterations
        
        Inputs:
            K: kernel matrix
            n_iter (int): number of optimization iterations
            B0: initialization for B

        Returns:
            self
        """
        self._fit(K, n_iter, B0)
        return self

    def fit_transform(self, K, n_iter:int=10):
        """Fit model and return archetype assignments
        """
        self._fit(K, n_iter)
        return self.A_

    def get_archetypes(self):
        """Return k x n matrix of archetypes"""
        return self.Z_

    def get_centers(self):
        """Return closest point to each archetype"""
        return np.argmax(self.B_, axis=0)

    def set_assignments(self, assgts):
        """Given integer-encoded assignments, set archetype matrix A"""
        n_archetypes = len(set(assgts))
        self.n = len(assgts)
        self.k = n_archetypes

        self.A_ = np.zeros((self.k, self.n))
        self.A_[np.array(assgts), np.arange(self.n)] = 1.

    def loo_cluster(self, data, ps=None):
        """Compute LOO log likelihood for cluster

        data: counts for each cell
        ps: pseudocount
        """
        ncells, dim = data.shape
        lib_sizes = data.sum(axis=1)
        if ps is None:
            ps = 1e-8
            data_plus_ps = data + ps
        else:
            data_plus_ps = data + ps
        total_counts = data.sum(axis=0)
        
        cluster_logprob = 0.
        for i in range(ncells):
            p = total_counts - data[i,:]
            p = p / np.sum(p)
            p += ps #1./1500 #ps.ravel()
            p = p / np.sum(p)
            logprob = multinomial.logpmf(data[i,:], lib_sizes[i], p)
            cluster_logprob += logprob
        return cluster_logprob

    def loo_likelihood(self, data, ps=1e-8):
        """Compute log likelihood with leave-one-out"""

        # iterate over clusters
        assgts = self.get_assignments()
        total_logprob = 0.
        #ps = data.sum(axis=0, keepdims=True)
        #ps = ps / np.sum(ps)
        for cluster_idx in tqdm(range(self.k)):
            sel = (assgts == cluster_idx)
            cluster_data = data[sel,:]
            total_logprob += self.loo_cluster(cluster_data, ps=ps)
        return total_logprob


    def get_assignments(self):
        """Return archetype assignments for each point (n,)
        """
        return np.argmax(self.A_, axis=0)

    def get_sizes(self):
        """Get the size of each metacell"""
        # use hard assgts
        assgts = self.get_assignments()
        A = np.zeros_like(self.A_)
        A[assgts, np.arange(self.A_.shape[1])] = 1.
        return A.sum(axis=1)

    def get_coordinates(self, X):
        """Return cluster centers
        """
        # use hard assignments
        assgts = self.get_assignments()
        A = np.zeros_like(self.A_)
        A[assgts, np.arange(self.A_.shape[1])] = 1.
        return np.array(A @ X) #/ self.A_.sum(axis=1, keepdims=True)

