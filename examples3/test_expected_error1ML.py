#!/usr/bin/env python
#
# Author: Mike McKerns (mmckerns @uqfoundation)
# Copyright (c) 2020-2021 The Uncertainty Quantification Foundation.
# License: 3-clause BSD.  The full license text is available at:
#  - https://github.com/uqfoundation/mystic/blob/master/LICENSE
'''
calculate lower and upper bound on expected Error on |truth - surrogate|

Test function is y = F(x), where:
  y0 = x0 + x1 * | x2 * x3**2 - (x4 / x1)**2 |**.5
  y1 = x0 - x1 * | x2 * x3**2 + (x4 / x1)**2 |**.5
  y2 = x0 - | x1 * x2 * x3 - x4 |

toy = lambda x: F(x)[0]
truth = lambda x: toy(x + .01) - .01
surrogate is trained on data sampled from truth
error = lambda x: (truth(x) - surrogate(x))**2

Calculate lower and upper bound on E|error(x)|, where:
  x in [(0,1), (1,10), (0,10), (0,10), (0,10)]
  wx in [(0,1), (1,1), (1,1), (1,1), (1,1)]
  npts = [2, 1, 1, 1, 1] (i.e. two Dirac masses on x[0], one elsewhere)
  sum(wx[i]_j) for j in [0,npts], for each i
  mean(x[0]) = 5e-1 +/- 1e-3
  var(x[0]) = 5e-3 +/- 1e-4

Solves for two scenarios of x that produce lower bound on E|error(x)|,
given the bounds, normalization, and moment constraints. Repeats
calculation for upper bound on E|error(x)|.

Creates 'log' of optimizations and 'truth' database of stored evaluations.
'''
from ouq_models import *


if __name__ == '__main__':

    #from toys import cost5x3 as toy; nx = 5; ny = 3
    #from toys import function5x3 as toy; nx = 5; ny = 3
    #from toys import cost5x1 as toy; nx = 5; ny = 1
    #from toys import function5x1 as toy; nx = 5; ny = 1
    #from toys import cost5 as toy; nx = 5; ny = None
    from toys import function5 as toy; nx = 5; ny = None

    # update optimization parameters
    from misc import param, npts, wlb, wub, is_cons, scons
    from ouq import ExpectedValue
    from mystic.bounds import MeasureBounds
    from mystic.monitors import VerboseLoggingMonitor, Monitor, VerboseMonitor
    from mystic.termination import VTRChangeOverGeneration as VTRCOG
    from mystic.termination import Or, VTR, ChangeOverGeneration as COG
    param['opts']['termination'] = COG(1e-10, 100) #NOTE: short stop?
    param['npop'] = 80 #NOTE: increase if poor convergence
    param['stepmon'] = VerboseLoggingMonitor(1, 20, filename='log.txt', label='lower')

    # build bounds
    bnd = MeasureBounds((0,1,0,0,0)[:nx],(1,10,10,10,10)[:nx], n=npts[:nx], wlb=wlb[:nx], wub=wub[:nx])

    # build a model representing 'truth', and generate some data
    #print("building truth F'(x|a')...")
    true = dict(mu=.01, sigma=0., zmu=-.01, zsigma=0.)
    truth = NoisyModel('truth', model=toy, nx=nx, ny=ny, **true)
    #print('sampling truth...')
    data = truth.sample([(0,1),(1,10)]+[(0,10)]*(nx-2), pts=-16)
    Ns = 25 #XXX: number of samples, when model has randomness

    # build a surrogate model by training on the data
    args = dict(hidden_layer_sizes=(100,75,50,25),  max_iter=1000, n_iter_no_change=5, solver='lbfgs', learning_rate_init=0.001)
    from sklearn.neural_network import MLPRegressor
    from sklearn.preprocessing import StandardScaler
    from ml import Estimator, MLData, improve_score
    kwds = dict(estimator=MLPRegressor(**args), transform=StandardScaler())
    # iteratively improve estimator
    mlp = Estimator(**kwds) #FIXME: traintest so train != test ?
    best = improve_score(mlp, MLData(data.coords, data.coords, data.values, data.values), tries=10, verbose=True)
    mlkw = dict(estimator=best.estimator, transform=best.transform)

    #print('building estimator G(x) from truth data...')
    surrogate = LearnedModel('surrogate', nx=nx, ny=ny, data=truth, **mlkw)
    #print('building UQ model of model error...')
    error = ErrorModel('error', model=truth, surrogate=surrogate)

    rnd = Ns if error.rnd else None
    #print('building UQ objective of expected model error...')
    b = ExpectedValue(error, bnd, constraint=scons, cvalid=is_cons, samples=rnd)
    #print('solving for lower bound on expected model error...')
    solver = b.lower_bound(axis=None, **param)
    if type(solver) is not tuple:
        solver = (solver,)
    for s in solver:
        print("lower bound:\n%s @ %s" % (s.bestEnergy, s.bestSolution))

    #print('solving for upper bound on expected model error...')
    param['opts']['termination'] = COG(1e-10, 200) #NOTE: short stop?
    param['npop'] = 160 #NOTE: increase if poor convergence
    param['stepmon'] = VerboseLoggingMonitor(1, 20, filename='log.txt', label='upper')
    solver = b.upper_bound(axis=None, id=1, **param)
    if type(solver) is not tuple:
        solver = (solver,)
    for s in solver:
        print("upper bound:\n%s @ %s" % (-s.bestEnergy, s.bestSolution))
