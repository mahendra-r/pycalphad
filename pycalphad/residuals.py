"""
The residuals module contains routines for calculating residuals of
experimental data for regression of thermodynamic models.
"""
from pycalphad import Model
from pycalphad.core.energy_surf import energy_surf
from pycalphad.core.lower_convex_hull import lower_convex_hull
from pycalphad.core.equilibrium import EquilibriumError
from pycalphad.core.utils import generate_dof, make_callable
import pycalphad.variables as v
import lmfit
from scipy.optimize import leastsq
import numpy as np
from pycalphad.log import logger
import itertools
import functools

def fit_model(guess, data, dbf, comps, phases, **kwargs):
    """
    Fit model parameters to input data based on an initial guess for parameters.

    Parameters
    ----------
    guess : dict
        Parameter names to fit with initial guesses.
    data : list of DataFrames
        Input data to fit.
    dbf : Database
        Thermodynamic database containing the relevant parameters.
    comps : list
        Names of components to consider in the calculation.
    phases : list
        Names of phases to consider in the calculation.

    Returns
    -------
    (Dictionary of fit key:values), (lmfit minimize result)

    Examples
    --------
    None yet.
    """
    if 'maxfev' not in kwargs:
        kwargs['maxfev'] = 100
    fit_params = lmfit.Parameters()
    for guess_name, guess_value in guess.items():
        fit_params.add(guess_name, value=guess_value)
    param_names = fit_params.valuesdict().keys()
    fit_models = {name: Model(dbf, comps, name) for name in phases}
    fit_variables = dict()
    for name, mod in fit_models.items():
        fit_variables[name], _ = generate_dof(dbf.phases[name], mod.components)
    callables = {name: make_callable(mod.ast, itertools.chain(param_names, [v.T],
                                                              fit_variables[name])) \
                    for name, mod in fit_models.items()}

    #out = leastsq(residual_equilibrium, param_values,
    #              args=(data, dbf, comps, fit_models, callables),
    #              full_output=True, **kwargs)
    out = lmfit.minimize(residual_equilibrium, fit_params,
                         args=(data, dbf, comps, fit_models, callables))
    #fit = residual_equilibrium(data, dbf, comps, fit_models, callables)
    #ssq = np.linalg.norm(residual_equilibrium(out[0], data, dbf, comps,
    #                                          fit_models, callables))
    #return dict(zip(param_names, out[0])), out[1:]
    return fit_params.valuesdict(), out

def residual_equilibrium(fit_params, input_data, dbf, comps, mods, callables):
    "Return an array with the residual for each experimentally defined equilibrium in 'input_data'."
    parvalues = fit_params.valuesdict().values()
    global_comps = [x.upper() for x in sorted(comps) if x != 'VA']
    col_names = ['X({})'.format(cxx) for cxx in global_comps]
    # Remove composition set indicators, i.e., convert FCC_A1#1 to FCC_A1
    phases = [x.upper().split('#')[0] for x in set(input_data['Phase'].values)]
    # some phases may appear multiple times due to composition set indicators
    phases = list(set(phases))
    # Prefill parameter values before passing to energy calculator
    iter_callables = {name: functools.partial(func, *parvalues) \
                        for name, func in callables.items()}
    eqres = np.zeros(len(input_data))
    temps = sorted(set(input_data['T'].values))

    calculated_data = energy_surf(dbf, comps, phases, T=temps, model=mods,
                                  callables=iter_callables, pdens=5000)
    calc_data_by_temp = dict(list(calculated_data.groupby('T')))
    idx = 0
    for temp, temp_df in input_data.groupby('T'):
        surface_data = calc_data_by_temp[temp]
        surface_data_by_phase = dict(list(surface_data.groupby('Phase')))
        for eqid, eq_df in temp_df.groupby('ID'):
            conditions = {v.X(comp): eq_df.iloc[0]['X({})'.format(comp)] \
                          for comp in global_comps[:-1]}
            phase_compositions, phase_fracs, pots = \
                    lower_convex_hull(surface_data, comps, conditions)
            if phase_compositions is None:
                raise EquilibriumError(('Unable to calculate equilibrium '
                                        'for T={0}, {1}').format(temp, conditions))
            phase_compositions = phase_compositions[0]
            phase_fracs = phase_fracs[0]
            pots = pots[0]
            for rowid, eqx in eq_df.iterrows():
                phase = eqx['Phase'].upper().split('#')[0]
                coords = surface_data_by_phase[phase][col_names].values
                target_x = eqx[col_names]
                difference = coords - target_x[np.newaxis, :]
                row_norms = np.linalg.norm(difference, ord=1, axis=1)
                nearest_idx = np.argmin(row_norms)
                phase_energy = surface_data_by_phase[phase].iloc[nearest_idx].loc['GM']
                driving_force = phase_energy - np.dot(pots, target_x)
                eqres[idx] = driving_force / (8.3145*temp)
                idx += 1
    return eqres

def residual_thermochemical(parvalues, input_data, dbf, comps, mods, callables):
    "Return an array with the residuals for thermochemical data in 'input_data'."
    global_comps = [x.upper() for x in sorted(comps) if x != 'VA']
    col_names = ['X({})'.format(cxx) for cxx in global_comps]
    # Remove composition set indicators, i.e., convert FCC_A1#1 to FCC_A1
    phases = [x.upper().split('#')[0] for x in set(input_data['Phase'].values)]
    # some phases may appear multiple times due to composition set indicators
    phases = sorted(set(phases))
    # Prefill parameter values before passing to energy calculator
    iter_callables = {name: functools.partial(func, *parvalues) \
                        for name, func in callables.items()}
    eqres = np.zeros(len(input_data))
    temps = sorted(set(input_data['T'].values))

    calculated_data = energy_surf(dbf, comps, phases, T=temps, model=mods,
                                  pdens=2000, output=outval,
                                  callables=iter_callables)
    calc_data_by_temp = dict(list(calculated_data.groupby('T')))
    idx = 0
    for temp, temp_df in input_data.groupby('T'):
        surface_data = calc_data_by_temp[temp]
        surface_data_by_phase = dict(list(surface_data.groupby('Phase')))
        for eqid, eq_df in temp_df.groupby('ID'):
            conditions = {v.X(comp): eq_df.iloc[0]['X({})'.format(comp)] \
                          for comp in global_comps[:-1]}
            phase_compositions, phase_fracs, pots = \
                    lower_convex_hull(surface_data, comps, conditions)
            if phase_compositions is None:
                raise EquilibriumError(('Unable to calculate equilibrium '
                                        'for T={0}, {1}').format(temp, conditions))
            for rowid, eqx in eq_df.iterrows():
                phase = eqx['Phase'].upper().split('#')[0]
                coords = surface_data_by_phase[phase][col_names].values
                target_x = eqx[col_names]
                difference = coords - target_x[np.newaxis, :]
                row_norms = np.linalg.norm(difference, ord=1, axis=1)
                nearest_idx = np.argmin(row_norms)
                phase_energy = surface_data_by_phase[phase].iloc[nearest_idx].loc['GM']
                driving_force = phase_energy - np.dot(pots, target_x)
                eqres[idx] = driving_force / (8.3145*temp)
                idx += 1
    return eqres
