"""
TWPCA cross-validation and hyperparameter search routines
"""
import numpy as np
import tensorflow as tf
import itertools
from tqdm import tqdm, trange
from .model import TWPCA
from .regularizers import curvature
from .utils import stable_rank

__all__ = ['cross_validate', 'hyperparam_search']

def cross_validate(model, data, nfits, censor_prob=0.1, seed=None, **fit_kw):
    """Runs cross-validation on TWPCA model.
    """

    # check inputs
    if censor_prob >= 1 or censor_prob < 0:
        print(censor_prob)
        raise ValueError('Censor probability must be greater than zero and less than one.')
    if seed is not None:
        np.random.seed(seed)

    # store results in list
    results = []

    for fit in range(nfits):

        # randomly subsample tensor
        testmask = np.random.rand(*data.shape) < censor_prob

        # nan out the test indices
        traindata = data.copy().astype(np.float32)
        traindata[testmask] = np.nan

        # fit the model to the training set
        tf.reset_default_graph()
        sess = tf.Session()
        model.fit(traindata, sess=sess, **fit_kw)

        # compute mean error on test set
        resid = data - model.predict()
        test_error = np.mean(resid[testmask]**2)

        results.append({
             'params': model.params,
             'train_error': model._sess.run(model.recon_cost),
             'test_error': test_error,
             'obj_history': model.obj_history
            }
        )

        # clean-up tensorflow
        sess.close()

    return results

def hyperparam_search(data, n_components, warp_scales, time_scales,
                      nfits=1, warp_reg=None, time_reg=None,
                      fit_kw=dict(lr=(1e-1, 1e-2), niter=(250, 500), progressbar=False),
                      **model_kw):
    """Performs cross-validation over number of components, warp regularization scale, and
    temporal regularization scale.

    Args:
        data: array-like, trials x time x neurons dataset
        n_components: sequence of ints, number of components in each model
        warp_scales: sequence of floats, scale of warp regularization in each model
        time_scales: sequence of floats, scale of time factor regularization in each model

    Usage:
        Hyperparameters are provided as sequences, which are combined sequentially to form
        each model. For example, the following code fits three models. The first model has 1
        component, a warp regularization scale of 1e-3, and a time regularization scale
        of 1e-2. The second model has 2 components, a stronger penalty scale on the warps
        (1e-2), and a stronger penalty scale on the temporal factors (1e-1). And so forth.
        ```
        n_components = [1, 2, 3]
        warp_scales = [1e-3, 1e-2, 1e-2]
        time_scales = [1e-2, 1e-1, 1e-1]
        hyperparam_search(data, n_components, warp_scales, time_scales, ...)
        ```

    Keywork Args:
        warp_reg: function, takes scalar and outputs a regularization term (in tensorflow) for
                    the warps. By default, `warp_reg = twpca.regularizers.curvature(s, power=1)`.
        time_reg: function, takes scalar and outputs a regularization term (in tensorflow) for
                    the time factors. By default,
                    `time_reg = twpca.regularizers.curvature(s, power=2, axis=0)`.
        nfits: int, number of crossvalidation runs per model.
        fit_kw: dict, keyword arguments passed to model.fit
        **model_kw: additional keywords are passed to twpca.TWPCA(...)

    Returns:
        results: dict, contains parameters and statistics of fitted models
    """

    # defaults for warp and time regularization
    if warp_reg is None:
        warp_reg = lambda s: curvature(scale=s, power=1)
    if time_reg is None:
        time_reg = lambda s: curvature(scale=s, power=2, axis=0)

    # initialize results dict
    results = {
        'n_components': [],
        'warp_scale': [],
        'time_scale': [],
        'crossval_data': [],
        'mean_test': [],
        'mean_train': [],
    }

    # run cross-validation for all specified hyperparameters
    for nc, ws, ts in zip(tqdm(n_components), warp_scales, time_scales):

        model = TWPCA(nc, warp_regularizer=warp_reg(ws), time_regularizer=time_reg(ts), **model_kw)
        _result = cross_validate(model, data, nfits, **fit_kw)

        results['n_components'].append(nc)
        results['warp_scale'].append(ws)
        results['time_scale'].append(ts)
        results['crossval_data'].append(_result)
        results['mean_test'].append(np.mean([r['test_error'] for r in _result]))
        results['mean_train'].append(np.mean([r['train_error'] for r in _result]))

    for k in results.keys():
        results[k] = np.array(results[k])

    return results
