# coding: utf-8
# pylint: disable=too-many-arguments, too-many-locals, invalid-name, fixme, E0012, R0912, C0302
"""Scikit-Learn Wrapper interface for XGBoost."""
from __future__ import absolute_import

import warnings
import json
import numpy as np
from .core import Booster, DMatrix, XGBoostError
from .training import train

# Do not use class names on scikit-learn directly.
# Re-define the classes on .compat to guarantee the behavior without scikit-learn
from .compat import (SKLEARN_INSTALLED, XGBModelBase,
                     XGBClassifierBase, XGBRegressorBase, XGBLabelEncoder)


def _objective_decorator(func):
    """Decorate an objective function

    Converts an objective function using the typical sklearn metrics
    signature so that it is usable with ``xgboost.training.train``

    Parameters
    ----------
    func: callable
        Expects a callable with signature ``func(y_true, y_pred)``:

        y_true: array_like of shape [n_samples]
            The target values
        y_pred: array_like of shape [n_samples]
            The predicted values

    Returns
    -------
    new_func: callable
        The new objective function as expected by ``xgboost.training.train``.
        The signature is ``new_func(preds, dmatrix)``:

        preds: array_like, shape [n_samples]
            The predicted values
        dmatrix: ``DMatrix``
            The training set from which the labels will be extracted using
            ``dmatrix.get_label()``
    """
    def inner(preds, dmatrix):
        """internal function"""
        labels = dmatrix.get_label()
        return func(labels, preds)
    return inner


class XGBModel(XGBModelBase):
    # pylint: disable=too-many-arguments, too-many-instance-attributes, invalid-name
    """Implementation of the Scikit-Learn API for XGBoost.

    Parameters
    ----------
    max_depth : int
        Maximum tree depth for base learners.
    learning_rate : float
        Boosting learning rate (xgb's "eta")
    n_estimators : int
        Number of trees to fit.
    verbosity : int
        The degree of verbosity. Valid values are 0 (silent) - 3 (debug).
    silent : boolean
        Whether to print messages while running boosting. Deprecated. Use verbosity instead.
    objective : string or callable
        Specify the learning task and the corresponding learning objective or
        a custom objective function to be used (see note below).
    booster: string
        Specify which booster to use: gbtree, gblinear or dart.
    nthread : int
        Number of parallel threads used to run xgboost.  (Deprecated, please use ``n_jobs``)
    n_jobs : int
        Number of parallel threads used to run xgboost.  (replaces ``nthread``)
    gamma : float
        Minimum loss reduction required to make a further partition on a leaf node of the tree.
    min_child_weight : int
        Minimum sum of instance weight(hessian) needed in a child.
    max_delta_step : int
        Maximum delta step we allow each tree's weight estimation to be.
    subsample : float
        Subsample ratio of the training instance.
    colsample_bytree : float
        Subsample ratio of columns when constructing each tree.
    colsample_bylevel : float
        Subsample ratio of columns for each level.
    colsample_bynode : float
        Subsample ratio of columns for each split.
    reg_alpha : float (xgb's alpha)
        L1 regularization term on weights
    reg_lambda : float (xgb's lambda)
        L2 regularization term on weights
    scale_pos_weight : float
        Balancing of positive and negative weights.
    base_score:
        The initial prediction score of all instances, global bias.
    seed : int
        Random number seed.  (Deprecated, please use random_state)
    random_state : int
        Random number seed.  (replaces seed)
    missing : float, optional
        Value in the data which needs to be present as a missing value. If
        None, defaults to np.nan.
    importance_type: string, default "gain"
        The feature importance type for the feature_importances_ property: either "gain",
        "weight", "cover", "total_gain" or "total_cover".
    \\*\\*kwargs : dict, optional
        Keyword arguments for XGBoost Booster object.  Full documentation of parameters can
        be found here: https://github.com/dmlc/xgboost/blob/master/doc/parameter.rst.
        Attempting to set a parameter via the constructor args and \\*\\*kwargs dict simultaneously
        will result in a TypeError.

        .. note:: \\*\\*kwargs unsupported by scikit-learn

            \\*\\*kwargs is unsupported by scikit-learn.  We do not guarantee that parameters
            passed via this argument will interact properly with scikit-learn.

    Note
    ----
    A custom objective function can be provided for the ``objective``
    parameter. In this case, it should have the signature
    ``objective(y_true, y_pred) -> grad, hess``:

    y_true: array_like of shape [n_samples]
        The target values
    y_pred: array_like of shape [n_samples]
        The predicted values

    grad: array_like of shape [n_samples]
        The value of the gradient for each sample point.
    hess: array_like of shape [n_samples]
        The value of the second derivative for each sample point
    """

    def __init__(self, max_depth=3, learning_rate=0.1, n_estimators=100,
                 verbosity=1, silent=None, objective="reg:squarederror",
                 booster='gbtree', n_jobs=1, nthread=None, gamma=0,
                 min_child_weight=1, max_delta_step=0, subsample=1,
                 colsample_bytree=1, colsample_bylevel=1, colsample_bynode=1,
                 reg_alpha=0, reg_lambda=1, scale_pos_weight=1, base_score=0.5,
                 random_state=0, seed=None, missing=None,
                 importance_type="gain", **kwargs):
        if not SKLEARN_INSTALLED:
            raise XGBoostError('sklearn needs to be installed in order to use this module')
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.n_estimators = n_estimators
        self.verbosity = verbosity
        self.silent = silent
        self.objective = objective
        self.booster = booster
        self.gamma = gamma
        self.min_child_weight = min_child_weight
        self.max_delta_step = max_delta_step
        self.subsample = subsample
        self.colsample_bytree = colsample_bytree
        self.colsample_bylevel = colsample_bylevel
        self.colsample_bynode = colsample_bynode
        self.reg_alpha = reg_alpha
        self.reg_lambda = reg_lambda
        self.scale_pos_weight = scale_pos_weight
        self.base_score = base_score
        self.missing = missing if missing is not None else np.nan
        self.kwargs = kwargs
        self._Booster = None
        self.seed = seed
        self.random_state = random_state
        self.nthread = nthread
        self.n_jobs = n_jobs
        self.importance_type = importance_type

    def __setstate__(self, state):
        # backward compatibility code
        # load booster from raw if it is raw
        # the booster now support pickle
        bst = state["_Booster"]
        if bst is not None and not isinstance(bst, Booster):
            state["_Booster"] = Booster(model_file=bst)
        self.__dict__.update(state)

    def get_booster(self):
        """Get the underlying xgboost Booster of this model.

        This will raise an exception when fit was not called

        Returns
        -------
        booster : a xgboost booster of underlying model
        """
        if self._Booster is None:
            raise XGBoostError('need to call fit or load_model beforehand')
        return self._Booster

    def set_params(self, **params):
        """Set the parameters of this estimator.
        Modification of the sklearn method to allow unknown kwargs. This allows using
        the full range of xgboost parameters that are not defined as member variables
        in sklearn grid search.
        Returns
        -------
        self
        """
        if not params:
            # Simple optimization to gain speed (inspect is slow)
            return self

        for key, value in params.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                self.kwargs[key] = value

        return self

    def get_params(self, deep=False):
        """Get parameters."""
        params = super(XGBModel, self).get_params(deep=deep)
        if isinstance(self.kwargs, dict):  # if kwargs is a dict, update params accordingly
            params.update(self.kwargs)
        if params['missing'] is np.nan:
            params['missing'] = None  # sklearn doesn't handle nan. see #4725
        if not params.get('eval_metric', True):
            del params['eval_metric']  # don't give as None param to Booster
        return params

    def get_xgb_params(self):
        """Get xgboost type parameters."""
        xgb_params = self.get_params()
        random_state = xgb_params.pop('random_state')
        if 'seed' in xgb_params and xgb_params['seed'] is not None:
            warnings.warn('The seed parameter is deprecated as of version .6.'
                          'Please use random_state instead.'
                          'seed is deprecated.', DeprecationWarning)
        else:
            xgb_params['seed'] = random_state
        n_jobs = xgb_params.pop('n_jobs')
        if 'nthread' in xgb_params and xgb_params['nthread'] is not None:
            warnings.warn('The nthread parameter is deprecated as of version .6.'
                          'Please use n_jobs instead.'
                          'nthread is deprecated.', DeprecationWarning)
        else:
            xgb_params['nthread'] = n_jobs

        if 'silent' in xgb_params and xgb_params['silent'] is not None:
            warnings.warn('The silent parameter is deprecated.'
                          'Please use verbosity instead.'
                          'silent is depreated', DeprecationWarning)
            # TODO(canonizer): set verbosity explicitly if silent is removed from xgboost,
            # but remains in this API
        else:
            # silent=None shouldn't be passed to xgboost
            xgb_params.pop('silent', None)

        if xgb_params['nthread'] <= 0:
            xgb_params.pop('nthread', None)
        return xgb_params

    def get_num_boosting_rounds(self):
        """Gets the number of xgboost boosting rounds."""
        return self.n_estimators

    def save_model(self, fname):
        """
        Save the model to a file.

        The model is saved in an XGBoost internal binary format which is
        universal among the various XGBoost interfaces. Auxiliary attributes of
        the Python Booster object (such as feature names) will not be loaded.
        Label encodings (text labels to numeric labels) will be also lost.
        **If you are using only the Python interface, we recommend pickling the
        model object for best results.**

        Parameters
        ----------
        fname : string
            Output file name
        """
        self.get_booster().save_model(fname)

    def load_model(self, fname):
        """
        Load the model from a file.

        The model is loaded from an XGBoost internal binary format which is
        universal among the various XGBoost interfaces. Auxiliary attributes of
        the Python Booster object (such as feature names) will not be loaded.
        Label encodings (text labels to numeric labels) will be also lost.
        **If you are using only the Python interface, we recommend pickling the
        model object for best results.**

        Parameters
        ----------
        fname : string or a memory buffer
            Input file name or memory buffer(see also save_raw)
        """
        if self._Booster is None:
            self._Booster = Booster({'nthread': self.n_jobs})
        self._Booster.load_model(fname)

    def fit(self, X, y, sample_weight=None, eval_set=None, eval_metric=None,
            early_stopping_rounds=None, verbose=True, xgb_model=None,
            sample_weight_eval_set=None, callbacks=None):
        # pylint: disable=missing-docstring,invalid-name,attribute-defined-outside-init
        """
        Fit the gradient boosting model

        Parameters
        ----------
        X : array_like
            Feature matrix
        y : array_like
            Labels
        sample_weight : array_like
            instance weights
        eval_set : list, optional
            A list of (X, y) tuple pairs to use as a validation set for
            early-stopping
        sample_weight_eval_set : list, optional
            A list of the form [L_1, L_2, ..., L_n], where each L_i is a list of
            instance weights on the i-th validation set.
        eval_metric : str, callable, optional
            If a str, should be a built-in evaluation metric to use. See
            doc/parameter.rst. If callable, a custom evaluation metric. The call
            signature is func(y_predicted, y_true) where y_true will be a
            DMatrix object such that you may need to call the get_label
            method. It must return a str, value pair where the str is a name
            for the evaluation and value is the value of the evaluation
            function. This objective is always minimized.
        early_stopping_rounds : int
            Activates early stopping. Validation error needs to decrease at
            least every <early_stopping_rounds> round(s) to continue training.
            Requires at least one item in evals.  If there's more than one,
            will use the last. Returns the model from the last iteration
            (not the best one). If early stopping occurs, the model will
            have three additional fields: bst.best_score, bst.best_iteration
            and bst.best_ntree_limit.
            (Use bst.best_ntree_limit to get the correct value if num_parallel_tree
            and/or num_class appears in the parameters)
        verbose : bool
            If `verbose` and an evaluation set is used, writes the evaluation
            metric measured on the validation set to stderr.
        xgb_model : str
            file name of stored xgb model or 'Booster' instance Xgb model to be
            loaded before training (allows training continuation).
        callbacks : list of callback functions
            List of callback functions that are applied at end of each iteration.
            It is possible to use predefined callbacks by using :ref:`callback_api`.
            Example:

            .. code-block:: python

                [xgb.callback.reset_learning_rate(custom_rates)]
        """
        if sample_weight is not None:
            trainDmatrix = DMatrix(X, label=y, weight=sample_weight,
                                   missing=self.missing, nthread=self.n_jobs)
        else:
            trainDmatrix = DMatrix(X, label=y, missing=self.missing, nthread=self.n_jobs)

        evals_result = {}

        if eval_set is not None:
            if sample_weight_eval_set is None:
                sample_weight_eval_set = [None] * len(eval_set)
            evals = list(
                DMatrix(eval_set[i][0], label=eval_set[i][1], missing=self.missing,
                        weight=sample_weight_eval_set[i], nthread=self.n_jobs)
                for i in range(len(eval_set)))
            evals = list(zip(evals, ["validation_{}".format(i) for i in
                                     range(len(evals))]))
        else:
            evals = ()

        params = self.get_xgb_params()

        if callable(self.objective):
            obj = _objective_decorator(self.objective)
            params["objective"] = "reg:squarederror"
        else:
            obj = None

        feval = eval_metric if callable(eval_metric) else None
        if eval_metric is not None:
            if callable(eval_metric):
                eval_metric = None
            else:
                params.update({'eval_metric': eval_metric})

        self._Booster = train(params, trainDmatrix,
                              self.get_num_boosting_rounds(), evals=evals,
                              early_stopping_rounds=early_stopping_rounds,
                              evals_result=evals_result, obj=obj, feval=feval,
                              verbose_eval=verbose, xgb_model=xgb_model,
                              callbacks=callbacks)

        if evals_result:
            for val in evals_result.items():
                evals_result_key = list(val[1].keys())[0]
                evals_result[val[0]][evals_result_key] = val[1][evals_result_key]
            self.evals_result_ = evals_result

        if early_stopping_rounds is not None:
            self.best_score = self._Booster.best_score
            self.best_iteration = self._Booster.best_iteration
            self.best_ntree_limit = self._Booster.best_ntree_limit
        return self

    def predict(self, data, output_margin=False, ntree_limit=None, validate_features=True):
        """
        Predict with `data`.

        .. note:: This function is not thread safe.

          For each booster object, predict can only be called from one thread.
          If you want to run prediction using multiple thread, call ``xgb.copy()`` to make copies
          of model object and then call ``predict()``.

        .. note:: Using ``predict()`` with DART booster

          If the booster object is DART type, ``predict()`` will perform dropouts, i.e. only
          some of the trees will be evaluated. This will produce incorrect results if ``data`` is
          not the training data. To obtain correct results on test sets, set ``ntree_limit`` to
          a nonzero value, e.g.

          .. code-block:: python

            preds = bst.predict(dtest, ntree_limit=num_round)

        Parameters
        ----------
        data : numpy.array/scipy.sparse
            Data to predict with
        output_margin : bool
            Whether to output the raw untransformed margin value.
        ntree_limit : int
            Limit number of trees in the prediction; defaults to best_ntree_limit if defined
            (i.e. it has been trained with early stopping), otherwise 0 (use all trees).
        validate_features : bool
            When this is True, validate that the Booster's and data's feature_names are identical.
            Otherwise, it is assumed that the feature_names are the same.
        Returns
        -------
        prediction : numpy array
        """
        # pylint: disable=missing-docstring,invalid-name
        test_dmatrix = DMatrix(data, missing=self.missing, nthread=self.n_jobs)
        # get ntree_limit to use - if none specified, default to
        # best_ntree_limit if defined, otherwise 0.
        if ntree_limit is None:
            ntree_limit = getattr(self, "best_ntree_limit", 0)
        return self.get_booster().predict(test_dmatrix,
                                          output_margin=output_margin,
                                          ntree_limit=ntree_limit,
                                          validate_features=validate_features)

    def apply(self, X, ntree_limit=0):
        """Return the predicted leaf every tree for each sample.

        Parameters
        ----------
        X : array_like, shape=[n_samples, n_features]
            Input features matrix.

        ntree_limit : int
            Limit number of trees in the prediction; defaults to 0 (use all trees).

        Returns
        -------
        X_leaves : array_like, shape=[n_samples, n_trees]
            For each datapoint x in X and for each tree, return the index of the
            leaf x ends up in. Leaves are numbered within
            ``[0; 2**(self.max_depth+1))``, possibly with gaps in the numbering.
        """
        test_dmatrix = DMatrix(X, missing=self.missing, nthread=self.n_jobs)
        return self.get_booster().predict(test_dmatrix,
                                          pred_leaf=True,
                                          ntree_limit=ntree_limit)

    def evals_result(self):
        """Return the evaluation results.

        If **eval_set** is passed to the `fit` function, you can call
        ``evals_result()`` to get evaluation results for all passed **eval_sets**.
        When **eval_metric** is also passed to the `fit` function, the
        **evals_result** will contain the **eval_metrics** passed to the `fit` function.

        Returns
        -------
        evals_result : dictionary

        Example
        -------

        .. code-block:: python

            param_dist = {'objective':'binary:logistic', 'n_estimators':2}

            clf = xgb.XGBModel(**param_dist)

            clf.fit(X_train, y_train,
                    eval_set=[(X_train, y_train), (X_test, y_test)],
                    eval_metric='logloss',
                    verbose=True)

            evals_result = clf.evals_result()

        The variable **evals_result** will contain:

        .. code-block:: python

            {'validation_0': {'logloss': ['0.604835', '0.531479']},
            'validation_1': {'logloss': ['0.41965', '0.17686']}}
        """
        if self.evals_result_:
            evals_result = self.evals_result_
        else:
            raise XGBoostError('No results.')

        return evals_result

    @property
    def feature_importances_(self):
        """
        Feature importances property

        .. note:: Feature importance is defined only for tree boosters

            Feature importance is only defined when the decision tree model is chosen as base
            learner (`booster=gbtree`). It is not defined for other base learner types, such
            as linear learners (`booster=gblinear`).

        Returns
        -------
        feature_importances_ : array of shape ``[n_features]``

        """
        if getattr(self, 'booster', None) is not None and self.booster not in {'gbtree', 'dart'}:
            raise AttributeError('Feature importance is not defined for Booster type {}'
                                 .format(self.booster))
        b = self.get_booster()
        score = b.get_score(importance_type=self.importance_type)
        all_features = [score.get(f, 0.) for f in b.feature_names]
        all_features = np.array(all_features, dtype=np.float32)
        return all_features / all_features.sum()

    @property
    def coef_(self):
        """
        Coefficients property

        .. note:: Coefficients are defined only for linear learners

            Coefficients are only defined when the linear model is chosen as base
            learner (`booster=gblinear`). It is not defined for other base learner types, such
            as tree learners (`booster=gbtree`).

        Returns
        -------
        coef_ : array of shape ``[n_features]`` or ``[n_classes, n_features]``
        """
        if getattr(self, 'booster', None) is not None and self.booster != 'gblinear':
            raise AttributeError('Coefficients are not defined for Booster type {}'
                                 .format(self.booster))
        b = self.get_booster()
        coef = np.array(json.loads(b.get_dump(dump_format='json')[0])['weight'])
        # Logic for multiclass classification
        n_classes = getattr(self, 'n_classes_', None)
        if n_classes is not None:
            if n_classes > 2:
                assert len(coef.shape) == 1
                assert coef.shape[0] % n_classes == 0
                coef = coef.reshape((n_classes, -1))
        return coef

    @property
    def intercept_(self):
        """
        Intercept (bias) property

        .. note:: Intercept is defined only for linear learners

            Intercept (bias) is only defined when the linear model is chosen as base
            learner (`booster=gblinear`). It is not defined for other base learner types, such
            as tree learners (`booster=gbtree`).

        Returns
        -------
        intercept_ : array of shape ``(1,)`` or ``[n_classes]``
        """
        if getattr(self, 'booster', None) is not None and self.booster != 'gblinear':
            raise AttributeError('Intercept (bias) is not defined for Booster type {}'
                                 .format(self.booster))
        b = self.get_booster()
        return np.array(json.loads(b.get_dump(dump_format='json')[0])['bias'])


class XGBClassifier(XGBModel, XGBClassifierBase):
    # pylint: disable=missing-docstring,too-many-arguments,invalid-name,too-many-instance-attributes
    __doc__ = "Implementation of the scikit-learn API for XGBoost classification.\n\n" \
        + '\n'.join(XGBModel.__doc__.split('\n')[2:])

    def __init__(self, max_depth=3, learning_rate=0.1, n_estimators=100,
                 verbosity=1, silent=None,
                 objective="binary:logistic", booster='gbtree',
                 n_jobs=1, nthread=None, gamma=0, min_child_weight=1, max_delta_step=0,
                 subsample=1, colsample_bytree=1, colsample_bylevel=1,
                 colsample_bynode=1, reg_alpha=0, reg_lambda=1, scale_pos_weight=1,
                 base_score=0.5, random_state=0, seed=None, missing=None, **kwargs):
        super(XGBClassifier, self).__init__(
            max_depth=max_depth, learning_rate=learning_rate, n_estimators=n_estimators,
            verbosity=verbosity, silent=silent, objective=objective, booster=booster,
            n_jobs=n_jobs, nthread=nthread, gamma=gamma,
            min_child_weight=min_child_weight, max_delta_step=max_delta_step,
            subsample=subsample, colsample_bytree=colsample_bytree,
            colsample_bylevel=colsample_bylevel, colsample_bynode=colsample_bynode,
            reg_alpha=reg_alpha, reg_lambda=reg_lambda, scale_pos_weight=scale_pos_weight,
            base_score=base_score, random_state=random_state, seed=seed, missing=missing,
            **kwargs)

    def fit(self, X, y, sample_weight=None, eval_set=None, eval_metric=None,
            early_stopping_rounds=None, verbose=True, xgb_model=None,
            sample_weight_eval_set=None, callbacks=None):
        # pylint: disable = attribute-defined-outside-init,arguments-differ
        """
        Fit gradient boosting classifier

        Parameters
        ----------
        X : array_like
            Feature matrix
        y : array_like
            Labels
        sample_weight : array_like
            Weight for each instance
        eval_set : list, optional
            A list of (X, y) pairs to use as a validation set for
            early-stopping
        sample_weight_eval_set : list, optional
            A list of the form [L_1, L_2, ..., L_n], where each L_i is a list of
            instance weights on the i-th validation set.
        eval_metric : str, callable, optional
            If a str, should be a built-in evaluation metric to use. See
            doc/parameter.rst. If callable, a custom evaluation metric. The call
            signature is func(y_predicted, y_true) where y_true will be a
            DMatrix object such that you may need to call the get_label
            method. It must return a str, value pair where the str is a name
            for the evaluation and value is the value of the evaluation
            function. This objective is always minimized.
        early_stopping_rounds : int, optional
            Activates early stopping. Validation error needs to decrease at
            least every <early_stopping_rounds> round(s) to continue training.
            Requires at least one item in evals. If there's more than one,
            will use the last. If early stopping occurs, the model will have
            three additional fields: bst.best_score, bst.best_iteration and
            bst.best_ntree_limit (bst.best_ntree_limit is the ntree_limit parameter
            default value in predict method if not any other value is specified).
            (Use bst.best_ntree_limit to get the correct value if num_parallel_tree
            and/or num_class appears in the parameters)
        verbose : bool
            If `verbose` and an evaluation set is used, writes the evaluation
            metric measured on the validation set to stderr.
        xgb_model : str
            file name of stored xgb model or 'Booster' instance Xgb model to be
            loaded before training (allows training continuation).
        callbacks : list of callback functions
            List of callback functions that are applied at end of each iteration.
            It is possible to use predefined callbacks by using :ref:`callback_api`.
            Example:

            .. code-block:: python

                [xgb.callback.reset_learning_rate(custom_rates)]
        """
        evals_result = {}
        self.classes_ = np.unique(y)
        self.n_classes_ = len(self.classes_)

        xgb_options = self.get_xgb_params()

        if callable(self.objective):
            obj = _objective_decorator(self.objective)
            # Use default value. Is it really not used ?
            xgb_options["objective"] = "binary:logistic"
        else:
            obj = None

        if self.n_classes_ > 2:
            # Switch to using a multiclass objective in the underlying XGB instance
            xgb_options["objective"] = "multi:softprob"
            xgb_options['num_class'] = self.n_classes_

        feval = eval_metric if callable(eval_metric) else None
        if eval_metric is not None:
            if callable(eval_metric):
                eval_metric = None
            else:
                xgb_options.update({"eval_metric": eval_metric})

        self._le = XGBLabelEncoder().fit(y)
        training_labels = self._le.transform(y)

        if eval_set is not None:
            if sample_weight_eval_set is None:
                sample_weight_eval_set = [None] * len(eval_set)
            evals = list(
                DMatrix(eval_set[i][0], label=self._le.transform(eval_set[i][1]),
                        missing=self.missing, weight=sample_weight_eval_set[i],
                        nthread=self.n_jobs)
                for i in range(len(eval_set))
            )
            nevals = len(evals)
            eval_names = ["validation_{}".format(i) for i in range(nevals)]
            evals = list(zip(evals, eval_names))
        else:
            evals = ()

        self._features_count = X.shape[1]

        if sample_weight is not None:
            train_dmatrix = DMatrix(X, label=training_labels, weight=sample_weight,
                                    missing=self.missing, nthread=self.n_jobs)
        else:
            train_dmatrix = DMatrix(X, label=training_labels,
                                    missing=self.missing, nthread=self.n_jobs)

        self._Booster = train(xgb_options, train_dmatrix, self.get_num_boosting_rounds(),
                              evals=evals, early_stopping_rounds=early_stopping_rounds,
                              evals_result=evals_result, obj=obj, feval=feval,
                              verbose_eval=verbose, xgb_model=xgb_model,
                              callbacks=callbacks)

        self.objective = xgb_options["objective"]
        if evals_result:
            for val in evals_result.items():
                evals_result_key = list(val[1].keys())[0]
                evals_result[val[0]][evals_result_key] = val[1][evals_result_key]
            self.evals_result_ = evals_result

        if early_stopping_rounds is not None:
            self.best_score = self._Booster.best_score
            self.best_iteration = self._Booster.best_iteration
            self.best_ntree_limit = self._Booster.best_ntree_limit

        return self

    def predict(self, data, output_margin=False, ntree_limit=None, validate_features=True):
        """
        Predict with `data`.

        .. note:: This function is not thread safe.

          For each booster object, predict can only be called from one thread.
          If you want to run prediction using multiple thread, call ``xgb.copy()`` to make copies
          of model object and then call ``predict()``.

        .. note:: Using ``predict()`` with DART booster

          If the booster object is DART type, ``predict()`` will perform dropouts, i.e. only
          some of the trees will be evaluated. This will produce incorrect results if ``data`` is
          not the training data. To obtain correct results on test sets, set ``ntree_limit`` to
          a nonzero value, e.g.

          .. code-block:: python

            preds = bst.predict(dtest, ntree_limit=num_round)

        Parameters
        ----------
        data : DMatrix
            The dmatrix storing the input.
        output_margin : bool
            Whether to output the raw untransformed margin value.
        ntree_limit : int
            Limit number of trees in the prediction; defaults to best_ntree_limit if defined
            (i.e. it has been trained with early stopping), otherwise 0 (use all trees).
        validate_features : bool
            When this is True, validate that the Booster's and data's feature_names are identical.
            Otherwise, it is assumed that the feature_names are the same.
        Returns
        -------
        prediction : numpy array
        """
        test_dmatrix = DMatrix(data, missing=self.missing, nthread=self.n_jobs)
        if ntree_limit is None:
            ntree_limit = getattr(self, "best_ntree_limit", 0)
        class_probs = self.get_booster().predict(test_dmatrix,
                                                 output_margin=output_margin,
                                                 ntree_limit=ntree_limit,
                                                 validate_features=validate_features)
        if output_margin:
            # If output_margin is active, simply return the scores
            return class_probs

        if len(class_probs.shape) > 1:
            column_indexes = np.argmax(class_probs, axis=1)
        else:
            column_indexes = np.repeat(0, class_probs.shape[0])
            column_indexes[class_probs > 0.5] = 1
        return self._le.inverse_transform(column_indexes)

    def predict_proba(self, data, ntree_limit=None, validate_features=True):
        """
        Predict the probability of each `data` example being of a given class.

        .. note:: This function is not thread safe

            For each booster object, predict can only be called from one thread.
            If you want to run prediction using multiple thread, call ``xgb.copy()`` to make copies
            of model object and then call predict

        Parameters
        ----------
        data : DMatrix
            The dmatrix storing the input.
        ntree_limit : int
            Limit number of trees in the prediction; defaults to best_ntree_limit if defined
            (i.e. it has been trained with early stopping), otherwise 0 (use all trees).
        validate_features : bool
            When this is True, validate that the Booster's and data's feature_names are identical.
            Otherwise, it is assumed that the feature_names are the same.

        Returns
        -------
        prediction : numpy array
            a numpy array with the probability of each data example being of a given class.
        """
        test_dmatrix = DMatrix(data, missing=self.missing, nthread=self.n_jobs)
        if ntree_limit is None:
            ntree_limit = getattr(self, "best_ntree_limit", 0)
        class_probs = self.get_booster().predict(test_dmatrix,
                                                 ntree_limit=ntree_limit,
                                                 validate_features=validate_features)
        if self.objective == "multi:softprob":
            return class_probs
        classone_probs = class_probs
        classzero_probs = 1.0 - classone_probs
        return np.vstack((classzero_probs, classone_probs)).transpose()

    def evals_result(self):
        """Return the evaluation results.

        If **eval_set** is passed to the `fit` function, you can call
        ``evals_result()`` to get evaluation results for all passed **eval_sets**.
        When **eval_metric** is also passed to the `fit` function, the
        **evals_result** will contain the **eval_metrics** passed to the `fit` function.

        Returns
        -------
        evals_result : dictionary

        Example
        -------

        .. code-block:: python

            param_dist = {'objective':'binary:logistic', 'n_estimators':2}

            clf = xgb.XGBClassifier(**param_dist)

            clf.fit(X_train, y_train,
                    eval_set=[(X_train, y_train), (X_test, y_test)],
                    eval_metric='logloss',
                    verbose=True)

            evals_result = clf.evals_result()

        The variable **evals_result** will contain

        .. code-block:: python

            {'validation_0': {'logloss': ['0.604835', '0.531479']},
            'validation_1': {'logloss': ['0.41965', '0.17686']}}
        """
        if self.evals_result_:
            evals_result = self.evals_result_
        else:
            raise XGBoostError('No results.')

        return evals_result


class XGBRFClassifier(XGBClassifier):
    # pylint: disable=missing-docstring
    __doc__ = "Experimental implementation of the scikit-learn API "\
              + "for XGBoost random forest classification.\n\n"\
              + '\n'.join(XGBModel.__doc__.split('\n')[2:])

    def __init__(self, max_depth=3, learning_rate=1, n_estimators=100,
                 verbosity=1, silent=None,
                 objective="binary:logistic", n_jobs=1, nthread=None, gamma=0,
                 min_child_weight=1, max_delta_step=0, subsample=0.8, colsample_bytree=1,
                 colsample_bylevel=1, colsample_bynode=0.8, reg_alpha=0, reg_lambda=1,
                 scale_pos_weight=1, base_score=0.5, random_state=0, seed=None,
                 missing=None, **kwargs):
        super(XGBRFClassifier, self).__init__(
            max_depth=max_depth, learning_rate=learning_rate, n_estimators=n_estimators,
            verbosity=verbosity, silent=silent, objective=objective, booster='gbtree',
            n_jobs=n_jobs, nthread=nthread, gamma=gamma,
            min_child_weight=min_child_weight, max_delta_step=max_delta_step,
            subsample=subsample, colsample_bytree=colsample_bytree,
            colsample_bylevel=colsample_bylevel, colsample_bynode=colsample_bynode,
            reg_alpha=reg_alpha, reg_lambda=reg_lambda, scale_pos_weight=scale_pos_weight,
            base_score=base_score, random_state=random_state, seed=seed, missing=missing,
            **kwargs)

    def get_xgb_params(self):
        params = super(XGBRFClassifier, self).get_xgb_params()
        params['num_parallel_tree'] = self.n_estimators
        return params

    def get_num_boosting_rounds(self):
        return 1


class XGBRegressor(XGBModel, XGBRegressorBase):
    # pylint: disable=missing-docstring
    __doc__ = "Implementation of the scikit-learn API for XGBoost regression.\n\n"\
        + '\n'.join(XGBModel.__doc__.split('\n')[2:])


class XGBRFRegressor(XGBRegressor):
    # pylint: disable=missing-docstring
    __doc__ = "Experimental implementation of the scikit-learn API "\
              + "for XGBoost random forest regression.\n\n"\
              + '\n'.join(XGBModel.__doc__.split('\n')[2:])

    def __init__(self, max_depth=3, learning_rate=1, n_estimators=100,
                 verbosity=1, silent=None,
                 objective="reg:squarederror", n_jobs=1, nthread=None, gamma=0,
                 min_child_weight=1, max_delta_step=0, subsample=0.8, colsample_bytree=1,
                 colsample_bylevel=1, colsample_bynode=0.8, reg_alpha=0, reg_lambda=1,
                 scale_pos_weight=1, base_score=0.5, random_state=0, seed=None,
                 missing=None, **kwargs):
        super(XGBRFRegressor, self).__init__(
            max_depth=max_depth, learning_rate=learning_rate, n_estimators=n_estimators,
            verbosity=verbosity, silent=silent, objective=objective, booster='gbtree',
            n_jobs=n_jobs, nthread=nthread, gamma=gamma,
            min_child_weight=min_child_weight, max_delta_step=max_delta_step,
            subsample=subsample, colsample_bytree=colsample_bytree,
            colsample_bylevel=colsample_bylevel, colsample_bynode=colsample_bynode,
            reg_alpha=reg_alpha, reg_lambda=reg_lambda, scale_pos_weight=scale_pos_weight,
            base_score=base_score, random_state=random_state, seed=seed, missing=missing,
            **kwargs)

    def get_xgb_params(self):
        params = super(XGBRFRegressor, self).get_xgb_params()
        params['num_parallel_tree'] = self.n_estimators
        return params

    def get_num_boosting_rounds(self):
        return 1


class XGBRanker(XGBModel):
    # pylint: disable=missing-docstring,too-many-arguments,invalid-name
    """Implementation of the Scikit-Learn API for XGBoost Ranking.

        Parameters
        ----------
        max_depth : int
            Maximum tree depth for base learners.
        learning_rate : float
            Boosting learning rate (xgb's "eta")
        n_estimators : int
            Number of boosted trees to fit.
        verbosity : int
            The degree of verbosity. Valid values are 0 (silent) - 3 (debug).
        silent : boolean
            Whether to print messages while running boosting. Deprecated. Use verbosity instead.
        objective : string
            Specify the learning task and the corresponding learning objective.
            The objective name must start with "rank:".
        booster: string
            Specify which booster to use: gbtree, gblinear or dart.
        nthread : int
            Number of parallel threads used to run xgboost.  (Deprecated, please use ``n_jobs``)
        n_jobs : int
            Number of parallel threads used to run xgboost.  (replaces ``nthread``)
        gamma : float
            Minimum loss reduction required to make a further partition on a leaf node of the tree.
        min_child_weight : int
            Minimum sum of instance weight(hessian) needed in a child.
        max_delta_step : int
            Maximum delta step we allow each tree's weight estimation to be.
        subsample : float
            Subsample ratio of the training instance.
        colsample_bytree : float
            Subsample ratio of columns when constructing each tree.
        colsample_bylevel : float
            Subsample ratio of columns for each level.
        colsample_bynode : float
            Subsample ratio of columns for each split.
        reg_alpha : float (xgb's alpha)
            L1 regularization term on weights
        reg_lambda : float (xgb's lambda)
            L2 regularization term on weights
        scale_pos_weight : float
            Balancing of positive and negative weights.
        base_score:
            The initial prediction score of all instances, global bias.
        seed : int
            Random number seed.  (Deprecated, please use random_state)
        random_state : int
            Random number seed.  (replaces seed)
        missing : float, optional
            Value in the data which needs to be present as a missing value. If
            None, defaults to np.nan.
        \\*\\*kwargs : dict, optional
            Keyword arguments for XGBoost Booster object.  Full documentation of parameters can
            be found here: https://github.com/dmlc/xgboost/blob/master/doc/parameter.rst.
            Attempting to set a parameter via the constructor args and \\*\\*kwargs dict
            simultaneously will result in a TypeError.

            .. note:: \\*\\*kwargs unsupported by scikit-learn

                \\*\\*kwargs is unsupported by scikit-learn.  We do not guarantee that parameters
                passed via this argument will interact properly with scikit-learn.

        Note
        ----
        A custom objective function is currently not supported by XGBRanker.

        Note
        ----
        Group information is required for ranking tasks.

        Before fitting the model, your data need to be sorted by group. When
        fitting the model, you need to provide an additional array that
        contains the size of each group.

        For example, if your original data look like:

        +-------+-----------+---------------+
        |   qid |   label   |   features    |
        +-------+-----------+---------------+
        |   1   |   0       |   x_1         |
        +-------+-----------+---------------+
        |   1   |   1       |   x_2         |
        +-------+-----------+---------------+
        |   1   |   0       |   x_3         |
        +-------+-----------+---------------+
        |   2   |   0       |   x_4         |
        +-------+-----------+---------------+
        |   2   |   1       |   x_5         |
        +-------+-----------+---------------+
        |   2   |   1       |   x_6         |
        +-------+-----------+---------------+
        |   2   |   1       |   x_7         |
        +-------+-----------+---------------+

        then your group array should be ``[3, 4]``.
        """

    def __init__(self, max_depth=3, learning_rate=0.1, n_estimators=100,
                 verbosity=1, silent=None, objective="rank:pairwise", booster='gbtree',
                 n_jobs=-1, nthread=None, gamma=0, min_child_weight=1, max_delta_step=0,
                 subsample=1, colsample_bytree=1, colsample_bylevel=1, colsample_bynode=1,
                 reg_alpha=0, reg_lambda=1, scale_pos_weight=1,
                 base_score=0.5, random_state=0, seed=None, missing=None, **kwargs):

        super(XGBRanker, self).__init__(
            max_depth=max_depth, learning_rate=learning_rate, n_estimators=n_estimators,
            verbosity=verbosity, silent=silent, objective=objective, booster=booster,
            n_jobs=n_jobs, nthread=nthread, gamma=gamma,
            min_child_weight=min_child_weight, max_delta_step=max_delta_step,
            subsample=subsample, colsample_bytree=colsample_bytree,
            colsample_bylevel=colsample_bylevel, colsample_bynode=colsample_bynode,
            reg_alpha=reg_alpha, reg_lambda=reg_lambda,
            scale_pos_weight=scale_pos_weight, base_score=base_score,
            random_state=random_state, seed=seed, missing=missing, **kwargs)
        if callable(self.objective):
            raise ValueError("custom objective function not supported by XGBRanker")
        if "rank:" not in self.objective:
            raise ValueError("please use XGBRanker for ranking task")

    def fit(self, X, y, group, sample_weight=None, eval_set=None, sample_weight_eval_set=None,
            eval_group=None, eval_metric=None, early_stopping_rounds=None,
            verbose=False, xgb_model=None, callbacks=None):
        # pylint: disable = attribute-defined-outside-init,arguments-differ
        """
        Fit the gradient boosting model

        Parameters
        ----------
        X : array_like
            Feature matrix
        y : array_like
            Labels
        group : array_like
            group size of training data
        sample_weight : array_like
            group weights

            .. note:: Weights are per-group for ranking tasks

                In ranking task, one weight is assigned to each group (not each data
                point). This is because we only care about the relative ordering of
                data points within each group, so it doesn't make sense to assign
                weights to individual data points.

        eval_set : list, optional
            A list of (X, y) tuple pairs to use as a validation set for
            early-stopping
        sample_weight_eval_set : list, optional
            A list of the form [L_1, L_2, ..., L_n], where each L_i is a list of
            group weights on the i-th validation set.

            .. note:: Weights are per-group for ranking tasks

                In ranking task, one weight is assigned to each group (not each data
                point). This is because we only care about the relative ordering of
                data points within each group, so it doesn't make sense to assign
                weights to individual data points.

        eval_group : list of arrays, optional
            A list that contains the group size corresponds to each
            (X, y) pair in eval_set
        eval_metric : str, callable, optional
            If a str, should be a built-in evaluation metric to use. See
            doc/parameter.rst. If callable, a custom evaluation metric. The call
            signature is func(y_predicted, y_true) where y_true will be a
            DMatrix object such that you may need to call the get_label
            method. It must return a str, value pair where the str is a name
            for the evaluation and value is the value of the evaluation
            function. This objective is always minimized.
        early_stopping_rounds : int
            Activates early stopping. Validation error needs to decrease at
            least every <early_stopping_rounds> round(s) to continue training.
            Requires at least one item in evals.  If there's more than one,
            will use the last. Returns the model from the last iteration
            (not the best one). If early stopping occurs, the model will
            have three additional fields: bst.best_score, bst.best_iteration
            and bst.best_ntree_limit.
            (Use bst.best_ntree_limit to get the correct value if num_parallel_tree
            and/or num_class appears in the parameters)
        verbose : bool
            If `verbose` and an evaluation set is used, writes the evaluation
            metric measured on the validation set to stderr.
        xgb_model : str
            file name of stored xgb model or 'Booster' instance Xgb model to be
            loaded before training (allows training continuation).
        callbacks : list of callback functions
            List of callback functions that are applied at end of each iteration.
            It is possible to use predefined callbacks by using :ref:`callback_api`.
            Example:

            .. code-block:: python

                [xgb.callback.reset_learning_rate(custom_rates)]
        """
        # check if group information is provided
        if group is None:
            raise ValueError("group is required for ranking task")

        if eval_set is not None:
            if eval_group is None:
                raise ValueError("eval_group is required if eval_set is not None")
            if len(eval_group) != len(eval_set):
                raise ValueError("length of eval_group should match that of eval_set")
            if any(group is None for group in eval_group):
                raise ValueError("group is required for all eval datasets for ranking task")

        def _dmat_init(group, **params):
            ret = DMatrix(**params)
            ret.set_group(group)
            return ret

        if sample_weight is not None:
            train_dmatrix = _dmat_init(group, data=X, label=y, weight=sample_weight,
                                       missing=self.missing, nthread=self.n_jobs)
        else:
            train_dmatrix = _dmat_init(group, data=X, label=y,
                                       missing=self.missing, nthread=self.n_jobs)

        evals_result = {}

        if eval_set is not None:
            if sample_weight_eval_set is None:
                sample_weight_eval_set = [None] * len(eval_set)
            evals = [_dmat_init(eval_group[i], data=eval_set[i][0], label=eval_set[i][1],
                                missing=self.missing, weight=sample_weight_eval_set[i],
                                nthread=self.n_jobs) for i in range(len(eval_set))]
            nevals = len(evals)
            eval_names = ["eval_{}".format(i) for i in range(nevals)]
            evals = list(zip(evals, eval_names))
        else:
            evals = ()

        params = self.get_xgb_params()

        feval = eval_metric if callable(eval_metric) else None
        if eval_metric is not None:
            if callable(eval_metric):
                eval_metric = None
            else:
                params.update({'eval_metric': eval_metric})

        self._Booster = train(params, train_dmatrix,
                              self.n_estimators,
                              early_stopping_rounds=early_stopping_rounds, evals=evals,
                              evals_result=evals_result, feval=feval,
                              verbose_eval=verbose, xgb_model=xgb_model,
                              callbacks=callbacks)

        self.objective = params["objective"]

        if evals_result:
            for val in evals_result.items():
                evals_result_key = list(val[1].keys())[0]
                evals_result[val[0]][evals_result_key] = val[1][evals_result_key]
            self.evals_result = evals_result

        if early_stopping_rounds is not None:
            self.best_score = self._Booster.best_score
            self.best_iteration = self._Booster.best_iteration
            self.best_ntree_limit = self._Booster.best_ntree_limit

        return self

    def predict(self, data, output_margin=False, ntree_limit=0, validate_features=True):

        test_dmatrix = DMatrix(data, missing=self.missing)
        if ntree_limit is None:
            ntree_limit = getattr(self, "best_ntree_limit", 0)

        return self.get_booster().predict(test_dmatrix,
                                          output_margin=output_margin,
                                          ntree_limit=ntree_limit,
                                          validate_features=validate_features)

    predict.__doc__ = XGBModel.predict.__doc__
