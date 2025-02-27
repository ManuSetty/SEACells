import numpy as np
import pandas as pd
from tqdm import tqdm


def determine_metacell_open_peaks(atac_meta_ad, peak_set=None, low_dim_embedding='X_svd', pval_cutoff=1e-2,
                                  read_len=147, n_neighbors=3, n_jobs=1):
    """
    TODO: Docstring
    """
    from sklearn.neighbors import NearestNeighbors
    from scipy.stats import poisson, multinomial

    # Effective genome length for background computaiton
    eff_genome_length = atac_meta_ad.shape[1] * 5000

    # Set up container
    if peak_set is None:
        peak_set = atac_meta_ad.var_names
    open_peaks = pd.DataFrame(
        0, index=atac_meta_ad.obs_names, columns=peak_set)

    # Metacell neighbors
    nbrs = NearestNeighbors(n_neighbors=n_neighbors)
    nbrs.fit(atac_meta_ad.obsm[low_dim_embedding])
    meta_nbrs = pd.DataFrame(atac_meta_ad.obs_names.values[nbrs.kneighbors(atac_meta_ad.obsm[low_dim_embedding])[1]],
                             index=atac_meta_ad.obs_names)

    for m in tqdm(open_peaks.index):
        # Boost using local neighbors
        frag_counts = np.ravel(
            atac_meta_ad[meta_nbrs.loc[m, :].values, :][:, peak_set].X.sum(axis=0))
        frag_distr = frag_counts / np.sum(frag_counts).astype(np.float64)

        # Multinomial distribution
        while not 0 < np.sum(frag_distr) < 1 - 1e-5:
            frag_distr = np.absolute(frag_distr - np.finfo(np.float32).epsneg)
        # Sample from multinomial distribution
        frag_counts = multinomial.rvs(np.percentile(
            atac_meta_ad.obs['n_counts'], 100), frag_distr)

        # Compute background poisson distribution
        total_frags = frag_counts.sum()
        glambda = (read_len * total_frags) / eff_genome_length

        # Significant peaks
        cutoff = pval_cutoff / np.sum(frag_counts > 0)
        open_peaks.loc[m, frag_counts >= poisson.ppf(1 - cutoff, glambda)] = 1

    # Update ATAC Metadata object
    atac_meta_ad.layers['OpenPeaks'] = open_peaks.values


def get_gene_accessibility(atac_meta_ad, gene_peak_cors, gene_set=None, pval_cutoff=1e-1, cor_cutoff=0.1):
    """
    TODO: Docstring
    """

    if 'OpenPeaks' not in atac_meta_ad.layers.keys():
        raise Exception(
            "Run determine_metacell_open_peaks to compute gene accessibility")
    open_peaks = pd.DataFrame(atac_meta_ad.layers['OpenPeaks'],
                              index=atac_meta_ad.obs_names, columns=atac_meta_ad.var_names)

    if gene_set is None:
        gene_set = gene_peak_cors.index

    # Container
    gene_accessiblity = pd.DataFrame(-1,
                                     index=atac_meta_ad.obs_names, columns=gene_set)
    for gene in tqdm(gene_set):
        df = gene_peak_cors[gene]

        # Skip if there no correlated peaks
        if type(df) is int:
            continue
        gene_peaks = df.index[(df['pval'] < pval_cutoff)
                              & (df['cor'] > cor_cutoff)]

        # Identify fraction open
        s = open_peaks.loc[:, gene_peaks].sum(axis=1)
        gene_accessiblity.loc[s.index, gene] = s.values / len(gene_peaks)

    atac_meta_ad.obsm['GeneAccessibility'] = gene_accessiblity
